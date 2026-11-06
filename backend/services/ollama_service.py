"""
Ollama local AI service for MediStruct AI.

Provides:
  - check_health(): Verify Ollama server is reachable and qwen3.5:2b is available.
  - transcribe_image(): Send a base64-encoded page image for handwriting recognition.
  - extract_clinical_json(): Text-based structured JSON extraction with format enforcement.
  - extract_with_retry(): Controlled retry wrapper (up to OLLAMA_MAX_RETRIES) that feeds
    schema validation errors back to the model before failing safely.

Design guarantees:
  - Never sends data to any external cloud service.
  - On failure, returns a clear error; does NOT silently fall back to Gemini.
  - For handwriting recognition only, local Tesseract OCR is accepted as a fallback
    (caller is responsible for routing that fallback correctly).
  - Never fabricates clinical information or silently fills missing schema keys.
"""

import base64
import io
import json
import re
from typing import Any, Dict, List, Optional

import httpx
from PIL import Image

from backend.config import settings

# Required top-level keys that every clinical extraction response must contain.
REQUIRED_CLINICAL_KEYS: List[str] = [
    "patient",
    "symptoms",
    "diagnoses",
    "medications",
    "lab_results",
    "recommendations",
]


class OllamaService:
    """
    HTTP client wrapper for the local Ollama REST API.
    Uses httpx for synchronous requests.  All network errors are surfaced
    as RuntimeError with descriptive messages — never swallowed silently.
    """

    # ------------------------------------------------------------------ #
    #  Configuration helpers (read dynamically so .env changes are picked  #
    #  up without restart when effective_provider resolves from live file)  #
    # ------------------------------------------------------------------ #

    @property
    def base_url(self) -> str:
        return settings.effective_ollama_base_url

    @property
    def model(self) -> str:
        return settings.effective_ollama_model

    @property
    def timeout(self) -> float:
        return settings.OLLAMA_TIMEOUT_SECONDS

    @property
    def max_retries(self) -> int:
        return settings.OLLAMA_MAX_RETRIES

    # ------------------------------------------------------------------ #
    #  Server & Model Health                                               #
    # ------------------------------------------------------------------ #

    def check_health(self) -> Dict[str, Any]:
        """
        Probe the Ollama server.  Returns a dict with:
          - server_online: bool
          - model_available: bool
          - model_capabilities: list[str]
          - error: str | None
        Never raises; failures are encoded in the returned dict.
        """
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            resp.raise_for_status()
            models_data = resp.json().get("models", [])
            model_entry = next(
                (m for m in models_data if m["name"] == self.model), None
            )
            if model_entry is None:
                return {
                    "server_online": True,
                    "model_available": False,
                    "model_capabilities": [],
                    "error": f"Model '{self.model}' not found in Ollama. Run: ollama pull {self.model}",
                }
            return {
                "server_online": True,
                "model_available": True,
                "model_capabilities": model_entry.get("capabilities", []),
                "error": None,
            }
        except httpx.ConnectError:
            return {
                "server_online": False,
                "model_available": False,
                "model_capabilities": [],
                "error": (
                    f"Cannot connect to Ollama at {self.base_url}. "
                    "Start Ollama with: ollama serve"
                ),
            }
        except Exception as exc:
            return {
                "server_online": False,
                "model_available": False,
                "model_capabilities": [],
                "error": str(exc),
            }

    def is_configured(self) -> bool:
        """Return True only if Ollama server is reachable and the model is available."""
        health = self.check_health()
        return health["server_online"] and health["model_available"]

    # ------------------------------------------------------------------ #
    #  Image Vision: Handwriting Transcription                             #
    # ------------------------------------------------------------------ #

    def transcribe_image(
        self,
        image: Image.Image,
        prompt: str,
    ) -> Dict[str, Any]:
        """
        Transcribe a PIL page image using Ollama multimodal vision.

        Returns:
          text              – transcribed text (may contain [UNCLEAR] markers)
          unclear_count     – number of [UNCLEAR] tokens found
          has_unclear_markers – bool
          recognition_method – "ollama_vision"
          model_used        – active model name
          error             – None on success, description string on failure
          fallback_used     – False (caller decides fallback strategy on error)

        On any error, sets error= and returns empty text with fallback_used=True.
        Does NOT automatically fall back to Gemini.
        """
        try:
            # Encode PIL image to PNG base64
            buf = io.BytesIO()
            img_rgb = image.convert("RGB") if image.mode not in ("RGB", "L") else image
            img_rgb.save(buf, format="PNG")
            b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [b64_str],
                    }
                ],
                "stream": False,
                "options": {"temperature": 0.1},
            }

            resp = httpx.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()

            raw_text = resp.json()["message"]["content"].strip()

            # Treat [BLANK PAGE] sentinel
            if raw_text.upper() == "[BLANK PAGE]":
                raw_text = ""

            unclear_matches = re.findall(r"\[UNCLEAR\]", raw_text, flags=re.IGNORECASE)
            unclear_count = len(unclear_matches)

            return {
                "text": raw_text,
                "unclear_count": unclear_count,
                "has_unclear_markers": unclear_count > 0,
                "recognition_method": "ollama_vision",
                "model_used": self.model,
                "error": None,
                "fallback_used": False,
            }

        except Exception as exc:
            return {
                "text": "",
                "unclear_count": 0,
                "has_unclear_markers": False,
                "recognition_method": "ollama_vision",
                "model_used": self.model,
                "error": str(exc),
                "fallback_used": True,
            }

    # ------------------------------------------------------------------ #
    #  Text Extraction: Clinical JSON with Controlled Retries              #
    # ------------------------------------------------------------------ #

    def extract_clinical_json(
        self,
        source_text: str,
        system_prompt: str,
    ) -> Dict[str, Any]:
        """
        Single-attempt call to Ollama for structured clinical JSON extraction.
        Returns parsed dict on success.
        Raises RuntimeError on network failure or invalid JSON.
        """
        user_content = (
            "Extract all clinical entities from the following medical document text.\n"
            "Remember to include the exact 'page_number' for each entity "
            "as indicated in the '--- [PAGE X] ---' markers in the text.\n\n"
            "--- DOCUMENT TEXT BEGIN ---\n"
            f"{source_text}\n"
            "--- DOCUMENT TEXT END ---"
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "format": "json",
            "think": False,
            "options": {"temperature": 0.1},
        }

        try:
            resp = httpx.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except httpx.ConnectError:
            raise RuntimeError(
                f"Ollama server unreachable at {self.base_url}. "
                "Ensure Ollama is running: ollama serve"
            )
        except httpx.TimeoutException:
            raise RuntimeError(
                f"Ollama inference timed out after {self.timeout}s. "
                "The model may still be loading; retry in a moment."
            )
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Ollama API returned HTTP {exc.response.status_code}: "
                f"{exc.response.text[:300]}"
            )

        raw_content = resp.json()["message"]["content"]
        return _parse_json_response(raw_content)

    def extract_with_retry(
        self,
        source_text: str,
        system_prompt: str,
    ) -> Dict[str, Any]:
        """
        Controlled retry wrapper around extract_clinical_json.
        On schema validation failure (missing required keys or invalid JSON),
        sends the specific error back to the model and retries up to max_retries times.

        Never fabricates data or silently defaults missing clinical categories.
        Raises RuntimeError with a clear message after all retries are exhausted.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "Extract all clinical entities from the following medical document text.\n"
                    "Remember to include the exact 'page_number' for each entity "
                    "as indicated in the '--- [PAGE X] ---' markers in the text.\n\n"
                    "--- DOCUMENT TEXT BEGIN ---\n"
                    f"{source_text}\n"
                    "--- DOCUMENT TEXT END ---"
                ),
            },
        ]

        last_error: Optional[str] = None

        for attempt in range(1, self.max_retries + 2):  # +2: attempts = max_retries + 1 initial try
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "format": "json",
                "think": False,
                "options": {"temperature": 0.1},
            }

            try:
                resp = httpx.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
            except httpx.ConnectError:
                raise RuntimeError(
                    f"Ollama server unreachable at {self.base_url}. "
                    "Ensure Ollama is running: ollama serve"
                )
            except httpx.TimeoutException:
                raise RuntimeError(
                    f"Ollama inference timed out after {self.timeout}s. "
                    "The model may still be loading. Please retry in a moment."
                )
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(
                    f"Ollama API returned HTTP {exc.response.status_code}: "
                    f"{exc.response.text[:300]}"
                )

            raw_content = resp.json()["message"]["content"]

            # --- Validate JSON parsability ---
            try:
                parsed = _parse_json_response(raw_content)
            except ValueError as parse_err:
                last_error = str(parse_err)
                if attempt > self.max_retries:
                    break
                # Feed the parse error back as a correction request
                messages.append({"role": "assistant", "content": raw_content})
                messages.append({
                    "role": "user",
                    "content": (
                        f"Your response could not be parsed as valid JSON. "
                        f"Error: {last_error}\n"
                        "Please respond with ONLY valid JSON, no markdown, no prose."
                    ),
                })
                continue

            # --- Validate required schema keys ---
            missing_keys = [k for k in REQUIRED_CLINICAL_KEYS if k not in parsed]
            if missing_keys:
                last_error = f"Missing required clinical categories: {missing_keys}"
                if attempt > self.max_retries:
                    break
                messages.append({"role": "assistant", "content": raw_content})
                messages.append({
                    "role": "user",
                    "content": (
                        f"Your response is missing required JSON keys: {missing_keys}. "
                        "If no data exists for a category, use an empty list [] or null. "
                        "Do NOT omit any of these keys: "
                        "patient, symptoms, diagnoses, medications, lab_results, recommendations."
                    ),
                })
                continue

            # --- All validations passed ---
            return parsed

        raise RuntimeError(
            f"Ollama clinical structuring failed after {self.max_retries + 1} attempt(s). "
            f"Last error: {last_error}. "
            "Clinical records were NOT persisted. No fabricated data was stored."
        )


# ------------------------------------------------------------------ #
#  Shared JSON parsing utility (used by both Ollama and Gemini paths) #
# ------------------------------------------------------------------ #

def _parse_json_response(raw_text: str) -> Dict[str, Any]:
    """
    Robustly clean and parse JSON from model output,
    handling accidental markdown code-fence wrappers.
    Raises ValueError with descriptive message on failure.
    """
    clean = raw_text.strip()

    # Strip markdown fences: ```json ... ``` or ``` ... ```
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean)
        clean = clean.strip()

    try:
        return json.loads(clean)
    except json.JSONDecodeError as err:
        # Last attempt: find the outermost {...} block
        match = re.search(r"(\{.*\})", clean, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
        raise ValueError(
            f"Model returned invalid JSON: {err}. "
            f"Raw output (first 300 chars): {raw_text[:300]}"
        )
