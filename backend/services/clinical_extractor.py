import json
import re
from typing import Dict, Any, Optional, Tuple, List
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.document import Document
from backend.models.page_extraction import PageExtraction
from backend.models.schemas import (
    StructuredClinicalPayload,
    PatientBase,
    SymptomBase,
    DiagnosisBase,
    MedicationBase,
    LabResultBase,
    RecommendationBase,
)
from backend.services.ollama_service import OllamaService

# Attempt import of google-genai
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


CLINICAL_EXTRACTION_SYSTEM_PROMPT = """You are an expert clinical research information extraction assistant.
Your task is to extract structured healthcare data from unstructured medical documents into a standardized JSON format.

CRITICAL ACADEMIC & CLINICAL INTEGRITY RULES:
1. Extract ONLY information that is EXPLICITLY stated in the provided text.
2. NEVER guess, assume, or fabricate any medical details, patient names, diagnoses, medications, dosages, or laboratory findings.
3. If an attribute is missing or not documented, set its value to null. Do not use empty strings or placeholders.
4. Preserve exact page numbers based on the '--- [PAGE X] ---' markers in the text. Every clinical entity MUST include its source 'page_number' (an integer).
5. Output ONLY valid, parseable JSON conforming strictly to the requested JSON schema. Do not include markdown code fences, headers, or conversational prose.

JSON OUTPUT STRUCTURE:
{
  "patient": {
    "patient_identifier": string or null,
    "name": string or null,
    "age": integer or null,
    "gender": string or null,
    "demographic_notes": string or null
  },
  "symptoms": [
    {
      "symptom_name": string,
      "description": string or null,
      "duration": string or null,
      "severity": string or null,
      "page_number": integer
    }
  ],
  "diagnoses": [
    {
      "diagnosis_name": string,
      "description": string or null,
      "diagnosis_date": string or null,
      "status": string or null,
      "page_number": integer
    }
  ],
  "medications": [
    {
      "medication_name": string,
      "dosage": string or null,
      "frequency": string or null,
      "duration": string or null,
      "route": string or null,
      "page_number": integer
    }
  ],
  "lab_results": [
    {
      "test_name": string,
      "result_value": string,
      "numeric_value": float or null,
      "unit": string or null,
      "reference_range": string or null,
      "flag": string or null,
      "test_date": string or null,
      "page_number": integer
    }
  ],
  "recommendations": [
    {
      "recommendation_text": string,
      "follow_up_instructions": string or null,
      "page_number": integer
    }
  ]
}
"""


class ClinicalExtractor:
    """
    AI-powered clinical information extraction service.
    Supports two providers:
      - "ollama"  (default): Local Ollama inference via qwen3.5:2b. No external API calls.
      - "gemini": Google Gemini 3.8 Flash via google-genai SDK (optional, requires API key).

    Provider is controlled by LLM_PROVIDER in .env (default: ollama).
    Changing LLM_PROVIDER in .env is reflected dynamically; a backend restart
    provides the strongest guarantee that the new value is loaded.

    Safety guarantees (apply to ALL providers):
      - Human-verification gate is always enforced before extraction.
      - Original OCR text, human corrections, and page citations are preserved.
      - No clinical data is fabricated or silently defaulted.
      - Database transactions are atomic; partial results are never persisted.
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
        Returns True if the active provider is ready to serve requests.
        For 'ollama': Ollama server must be reachable and model must be available.
        For 'gemini': API key must be set and google-genai must be importable.
        """
        if self._provider == "ollama":
            return OllamaService().is_configured()
        # gemini
        return bool(genai is not None and len(self.api_key) > 5)

    @staticmethod
    def get_eligible_document_text(doc: Document, db: Session) -> Tuple[bool, str, Optional[str]]:
        """
        Evaluate document source text eligibility respecting the human verification protocol:
        1. If any handwritten/uncertain page is unverified -> block structuring.
        2. Always use human-corrected text over raw OCR text when available.
        3. Preserve page citations ('--- [PAGE X] ---').
        Returns: (is_eligible, text_content, error_or_reason)
        """
        # Fetch page extractions for this document ordered by page_number
        pages: List[PageExtraction] = (
            db.query(PageExtraction)
            .filter(PageExtraction.document_id == doc.id)
            .order_by(PageExtraction.page_number.asc())
            .all()
        )

        # Safety Gate: Check for unverified handwritten pages
        unverified_hw_pages = [
            p.page_number for p in pages
            if p.page_classification in ("handwritten", "uncertain") and p.verification_status != "verified"
        ]

        if unverified_hw_pages:
            pages_str = ", ".join(f"Page {n}" for n in unverified_hw_pages)
            return (
                False,
                "",
                f"Clinical safety protocol: Document contains unverified handwritten notes ({pages_str}). "
                f"Human verification is strictly required before clinical entity structuring."
            )

        # Also check document-level handwriting flag if no page extractions exist
        if not pages and doc.handwriting_detected:
            return (
                False,
                "",
                "Clinical safety protocol: Document is classified as handwritten but has no verified page extractions."
            )

        # Assemble text blocks using verified / corrected text
        if pages:
            text_blocks = []
            for p in pages:
                # Prioritize: human_corrected_text > final_text > ocr_text
                page_text = p.human_corrected_text or p.final_text or p.ocr_text or ""
                text_blocks.append(f"--- [PAGE {p.page_number}] ---\n{page_text.strip()}\n")
            combined_text = "\n".join(text_blocks).strip()
        else:
            combined_text = (doc.raw_text or "").strip()

        if not combined_text:
            return False, "", "Document contains no readable text content to extract clinical entities from."

        return True, combined_text, None

    def extract_clinical_data(
        self,
        document_id: str,
        source_text: str,
    ) -> StructuredClinicalPayload:
        """
        Route clinical extraction to the configured provider (Ollama or Gemini),
        validate the response against the Pydantic schema, and return a typed payload.

        Provider selection:
          - LLM_PROVIDER=ollama (default): Uses OllamaService with controlled retries.
          - LLM_PROVIDER=gemini: Uses the existing google-genai pipeline.

        If Ollama fails, a clear RuntimeError is raised.
        Gemini is NOT used as an automatic fallback when Ollama is the configured provider.
        """
        if not source_text or not source_text.strip():
            raise ValueError("Source text is empty. Cannot extract clinical data.")

        if self._provider == "ollama":
            return self._extract_via_ollama(document_id, source_text)
        else:
            return self._extract_via_gemini(document_id, source_text)

    # ------------------------------------------------------------------ #
    #  Ollama Extraction Path                                              #
    # ------------------------------------------------------------------ #

    def _extract_via_ollama(
        self, document_id: str, source_text: str
    ) -> StructuredClinicalPayload:
        """
        Clinical extraction using local Ollama (qwen3.5:2b).
        Uses controlled retries for schema validation.
        Raises RuntimeError clearly on failure — never falls back to Gemini.
        """
        ollama = OllamaService()
        if not ollama.is_configured():
            health = ollama.check_health()
            raise RuntimeError(
                f"Ollama provider is not ready: {health.get('error', 'unknown error')}. "
                "Start Ollama and ensure qwen3.5:2b is available, or switch "
                "LLM_PROVIDER=gemini in .env if Gemini is configured."
            )

        try:
            parsed_json = ollama.extract_with_retry(source_text, CLINICAL_EXTRACTION_SYSTEM_PROMPT)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Ollama clinical extraction failed: {str(exc)}")

        parsed_json["document_id"] = document_id

        try:
            return StructuredClinicalPayload.model_validate(parsed_json)
        except Exception as exc:
            raise RuntimeError(
                f"Ollama response failed Pydantic schema validation: {str(exc)}. "
                "No clinical records were persisted."
            )

    # ------------------------------------------------------------------ #
    #  Gemini Extraction Path (preserved exactly from prior implementation)#
    # ------------------------------------------------------------------ #

    def _extract_via_gemini(
        self, document_id: str, source_text: str
    ) -> StructuredClinicalPayload:
        """
        Clinical extraction using Google Gemini 3.8 Flash (optional provider).
        Preserved exactly from Phase 4 implementation.
        """
        if not bool(genai is not None and len(self.api_key) > 5):
            raise RuntimeError(
                "Gemini API is not configured. Please set GEMINI_API_KEY in your .env configuration."
            )

        try:
            client = genai.Client(api_key=self.api_key)

            user_prompt = (
                f"Extract all clinical entities from the following medical document text.\n"
                f"Remember to include the exact 'page_number' for each entity as indicated in the text markers.\n\n"
                f"--- DOCUMENT TEXT BEGIN ---\n"
                f"{source_text}\n"
                f"--- DOCUMENT TEXT END ---"
            )

            response = client.models.generate_content(
                model=self.model_name,
                contents=[user_prompt],
                config=types.GenerateContentConfig(
                    system_instruction=CLINICAL_EXTRACTION_SYSTEM_PROMPT,
                    temperature=0.1,  # Low temperature for factual extraction
                    response_mime_type="application/json",
                ),
            )

            raw_response_text = response.text or ""
            parsed_json = self._parse_json_response(raw_response_text)

            # Inject document_id into the payload
            parsed_json["document_id"] = document_id

            # Validate against Pydantic model
            payload = StructuredClinicalPayload.model_validate(parsed_json)
            return payload

        except Exception as exc:
            raise RuntimeError(f"Clinical AI extraction failed: {str(exc)}")

    @staticmethod
    def _parse_json_response(raw_text: str) -> Dict[str, Any]:
        """
        Robustly clean and parse JSON from model output, handling potential markdown wrappers.
        """
        clean_text = raw_text.strip()

        # Remove markdown code fence if present
        if clean_text.startswith("```"):
            clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
            clean_text = re.sub(r"\s*```$", "", clean_text)
            clean_text = clean_text.strip()

        try:
            return json.loads(clean_text)
        except json.JSONDecodeError as err:
            # Fallback: attempt to find matching outer braces { ... }
            match = re.search(r"(\{.*\})", clean_text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except Exception:
                    pass
            raise ValueError(f"Model returned invalid JSON response: {str(err)}. Raw output: {raw_text[:200]}")
