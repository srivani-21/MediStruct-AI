import io
import re
from typing import Dict, Any, Optional
from PIL import Image
from backend.config import settings
from backend.services.ollama_service import OllamaService

# Attempt import of google-genai
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


MEDICAL_TRANSCRIPTION_PROMPT = """You are a clinical transcription assistant.
Your task is to transcribe the handwritten medical text in this image exactly as written.

STRICT RULES:
1. Transcribe every word exactly as it appears. Do not interpret, summarise, or reorder.
2. If a word, number, or symbol is illegible or ambiguous, write [UNCLEAR] in that position.
3. NEVER guess or infer: medicine names, dosages, frequencies, patient identifiers, lab values, or dates. Mark them [UNCLEAR] if uncertain.
4. Preserve line breaks and document structure as closely as possible.
5. If the entire page is blank or contains no text, respond only with: [BLANK PAGE]
6. Do not add headers, explanations, or notes. Return only the transcribed text."""


class HandwritingService:
    """
    Multimodal vision service for clinical handwriting transcription.
    Supports two providers:
      - "ollama" (default): Local Ollama vision inference via qwen3.5:2b.
        Sends base64-encoded PNG image bytes to the local Ollama API.
        On failure: falls back to local Tesseract OCR text only.
        Never automatically sends data to Gemini.
      - "gemini": Google Gemini 3.8 Flash multimodal vision (optional, requires API key).
        On failure: falls back to local Tesseract OCR text only.

    Provider is controlled by LLM_PROVIDER in .env (default: ollama).
    Fallback policy:
      - Handwriting recognition failure → local Tesseract OCR (page remains unverified).
      - Tesseract is ONLY a recognition fallback, not a clinical extraction substitute.
    Enforces [UNCLEAR] annotations without inventing numerical confidence scores.
    """

    def __init__(self):
        pass

    @property
    def _provider(self) -> str:
        return settings.effective_provider

    # --- Gemini-specific helpers (preserved exactly) ---

    @property
    def api_key(self) -> str:
        return settings.effective_gemini_api_key

    @property
    def model_name(self) -> str:
        return settings.GEMINI_MODEL or "gemini-3.8-flash"

    def is_configured(self) -> bool:
        """
        Returns True if the active provider is ready to serve vision requests.
        For 'ollama': Ollama server must be reachable and model must be available.
        For 'gemini': API key must be set and google-genai must be importable.
        """
        if self._provider == "ollama":
            return OllamaService().is_configured()
        return bool(genai is not None and len(self.api_key) > 5)

    def recognize_page(
        self,
        image: Image.Image,
        tesseract_fallback_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Transcribe a single page image using the configured vision provider.

        Routing:
          - LLM_PROVIDER=ollama: Sends image to local Ollama (qwen3.5:2b).
          - LLM_PROVIDER=gemini: Sends image to Gemini 3.8 Flash.

        Fallback policy:
          - If the active provider fails or is not configured:
            falls back to local Tesseract OCR text (page stays unverified).
          - Ollama failure NEVER automatically sends data to Gemini.
          - Gemini failure NEVER automatically sends data to Ollama.

        The returned page always has verification_status=unverified,
        routing it to the Human Verification Studio regardless of provider.
        """
        if self._provider == "ollama":
            return self._recognize_via_ollama(image, tesseract_fallback_text)
        else:
            return self._recognize_via_gemini(image, tesseract_fallback_text)

    # ------------------------------------------------------------------ #
    #  Ollama Vision Path                                                  #
    # ------------------------------------------------------------------ #

    def _recognize_via_ollama(
        self,
        image: Image.Image,
        tesseract_fallback_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Handwriting recognition using local Ollama vision (qwen3.5:2b).
        On failure: falls back to Tesseract OCR text only.
        Never sends data to Gemini.
        """
        ollama = OllamaService()

        if not ollama.is_configured():
            fb_text = tesseract_fallback_text or ""
            health = ollama.check_health()
            return {
                "text": fb_text,
                "unclear_count": 0,
                "has_unclear_markers": False,
                "recognition_method": "tesseract_ocr",
                "model_used": "none",
                "error": f"Ollama not ready: {health.get('error', 'unknown')}. Used local Tesseract fallback.",
                "fallback_used": True,
            }

        result = ollama.transcribe_image(image, MEDICAL_TRANSCRIPTION_PROMPT)

        if result["fallback_used"] or result["error"]:
            # Ollama failed — fall back to local Tesseract, NOT Gemini
            fb_text = tesseract_fallback_text or ""
            return {
                "text": fb_text,
                "unclear_count": 0,
                "has_unclear_markers": False,
                "recognition_method": "ollama_vision_fallback_tesseract",
                "model_used": settings.effective_ollama_model,
                "error": result["error"],
                "fallback_used": True,
            }

        return result

    # ------------------------------------------------------------------ #
    #  Gemini Vision Path (preserved exactly from prior implementation)    #
    # ------------------------------------------------------------------ #

    def _recognize_via_gemini(
        self,
        image: Image.Image,
        tesseract_fallback_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Handwriting recognition using Google Gemini 3.8 Flash (optional provider).
        Preserved exactly from Phase 3 implementation.
        On failure: falls back to local Tesseract OCR text only.
        """
        if not bool(genai is not None and len(self.api_key) > 5):
            fb_text = tesseract_fallback_text or ""
            return {
                "text": fb_text,
                "unclear_count": 0,
                "has_unclear_markers": False,
                "recognition_method": "tesseract_ocr",
                "model_used": "none",
                "error": "Gemini API key is not configured in .env",
                "fallback_used": True,
            }

        try:
            # Convert PIL image to PNG bytes
            buffer = io.BytesIO()
            # Ensure RGB mode for clean PNG export
            if image.mode not in ("RGB", "L"):
                rgb_img = image.convert("RGB")
            else:
                rgb_img = image
            rgb_img.save(buffer, format="PNG")
            buffer.seek(0)
            png_bytes = buffer.read()

            # Initialize official GenAI client
            client = genai.Client(api_key=self.api_key)

            # Generate content using inline PNG bytes part and prompt
            part = types.Part.from_bytes(data=png_bytes, mime_type="image/png")
            response = client.models.generate_content(
                model=self.model_name,
                contents=[part, MEDICAL_TRANSCRIPTION_PROMPT],
            )

            raw_output = response.text or ""
            clean_text = raw_output.strip()

            if clean_text == "[BLANK PAGE]":
                clean_text = ""

            # Count observable [UNCLEAR] markers
            unclear_matches = re.findall(r"\[UNCLEAR\]", clean_text, flags=re.IGNORECASE)
            unclear_count = len(unclear_matches)

            return {
                "text": clean_text,
                "unclear_count": unclear_count,
                "has_unclear_markers": unclear_count > 0,
                "recognition_method": "gemini_vision",
                "model_used": self.model_name,
                "error": None,
                "fallback_used": False,
            }

        except Exception as exc:
            fb_text = tesseract_fallback_text or ""
            return {
                "text": fb_text,
                "unclear_count": 0,
                "has_unclear_markers": False,
                "recognition_method": "gemini_vision_fallback_tesseract",
                "model_used": self.model_name,
                "error": str(exc),
                "fallback_used": True,
            }
