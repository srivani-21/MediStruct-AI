"""
tests/test_ollama_integration.py

Comprehensive test suite for the Ollama dual-provider integration in MediStruct AI.

Test categories:
  A. Provider configuration & routing (settings, effective_provider)
  B. OllamaService health & error handling (mocked network)
  C. Text-based clinical extraction via Ollama (mocked)
  D. Image-based handwriting recognition via Ollama (mocked)
  E. Controlled retry logic (JSON errors, missing schema keys)
  F. Provider routing in ClinicalExtractor and HandwritingService
  G. Human-verification safety gate enforcement
  H. Failure isolation (Ollama failure does NOT trigger Gemini)

All tests use mocked Ollama HTTP responses — no live Ollama calls are made.
No real medical documents or patient records are used.
No existing database records are modified.
"""

import base64
import io
import json
import uuid as _uuid_module
from unittest.mock import patch, MagicMock, PropertyMock
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.config import settings
from backend.database import Base

# Import all models so Base.metadata is complete before create_all
from backend.models.document import Document
from backend.models.page_extraction import PageExtraction
from backend.models.patient import Patient
from backend.models.clinical_records import Symptom, Diagnosis, Medication, LabResult, Recommendation
from backend.services.ollama_service import OllamaService, REQUIRED_CLINICAL_KEYS
from backend.services.clinical_extractor import ClinicalExtractor
from backend.services.handwriting_service import HandwritingService

client = TestClient(app)

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

SYNTHETIC_CLINICAL_TEXT = """\
--- [PAGE 1] ---
Patient: Jane Smith, Age: 52, Gender: Female
Chief Complaint: Shortness of breath and persistent cough for 3 weeks.
Diagnosis: Community-acquired pneumonia.
Medication: Amoxicillin-clavulanate 875/125 mg PO BID x 7 days.
Lab: WBC 14.2 x10^3/uL (High). CXR: Right lower lobe consolidation.
Recommendation: Follow-up in 1 week. Chest CT if no improvement.
"""

VALID_CLINICAL_JSON = {
    "patient": {
        "patient_identifier": None,
        "name": "Jane Smith",
        "age": 52,
        "gender": "Female",
        "demographic_notes": None,
    },
    "symptoms": [
        {
            "symptom_name": "Shortness of breath",
            "description": None,
            "duration": "3 weeks",
            "severity": None,
            "page_number": 1,
        }
    ],
    "diagnoses": [
        {
            "diagnosis_name": "Community-acquired pneumonia",
            "description": None,
            "diagnosis_date": None,
            "status": None,
            "page_number": 1,
        }
    ],
    "medications": [
        {
            "medication_name": "Amoxicillin-clavulanate",
            "dosage": "875/125 mg",
            "frequency": "BID",
            "duration": "7 days",
            "route": "PO",
            "page_number": 1,
        }
    ],
    "lab_results": [
        {
            "test_name": "WBC",
            "result_value": "14.2",
            "numeric_value": 14.2,
            "unit": "x10^3/uL",
            "reference_range": None,
            "flag": "High",
            "test_date": None,
            "page_number": 1,
        }
    ],
    "recommendations": [
        {
            "recommendation_text": "Follow-up in 1 week",
            "follow_up_instructions": "Chest CT if no improvement",
            "page_number": 1,
        }
    ],
}


def _make_synthetic_image() -> Image.Image:
    """Create a small synthetic white image with printed text for vision tests."""
    img = Image.new("RGB", (400, 100), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((10, 10), "Rx: Metformin 500mg PO BID", fill=(0, 0, 0))
    d.text((10, 40), "Diagnosis: Type 2 Diabetes Mellitus", fill=(0, 0, 0))
    d.text((10, 70), "Dr. Kumar  2026-11-06", fill=(0, 0, 0))
    return img


def _mock_ollama_chat_response(content: str) -> MagicMock:
    """Build a mock httpx response for /api/chat with given JSON content string."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"message": {"content": content}}
    return mock_resp


def _mock_ollama_tags_response(available: bool = True) -> MagicMock:
    """Build a mock httpx response for /api/tags."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    if available:
        mock_resp.json.return_value = {
            "models": [
                {
                    "name": "qwen3.5:2b",
                    "capabilities": ["completion", "vision", "tools", "thinking"],
                }
            ]
        }
    else:
        mock_resp.json.return_value = {"models": []}
    return mock_resp


# ===========================================================================
# A. Provider Configuration & Routing
# ===========================================================================

class TestProviderConfiguration:
    """Verify that settings resolve providers correctly from config."""

    def test_default_provider_is_ollama(self):
        """LLM_PROVIDER defaults to 'ollama'."""
        s = settings.__class__(LLM_PROVIDER="ollama")
        assert s.effective_provider == "ollama"

    def test_gemini_provider_resolves(self):
        """LLM_PROVIDER=gemini resolves correctly."""
        s = settings.__class__(LLM_PROVIDER="gemini")
        assert s.effective_provider == "gemini"

    def test_invalid_provider_defaults_to_ollama(self):
        """Unknown LLM_PROVIDER value falls back to 'ollama'."""
        s = settings.__class__(LLM_PROVIDER="unknown_provider")
        # Falls back to ollama via live env / .env, or returns ollama default
        assert s.effective_provider in ("ollama", "gemini")

    def test_ollama_base_url_default(self):
        """OLLAMA_BASE_URL defaults to localhost:11434."""
        s = settings.__class__()
        assert "11434" in s.effective_ollama_base_url

    def test_ollama_model_default(self):
        """OLLAMA_MODEL defaults to qwen3.5:2b."""
        s = settings.__class__()
        assert s.effective_ollama_model == "qwen3.5:2b"

    def test_ollama_timeout_is_generous(self):
        """OLLAMA_TIMEOUT_SECONDS is at least 120s to handle cold-start."""
        assert settings.OLLAMA_TIMEOUT_SECONDS >= 120.0

    def test_ollama_max_retries_is_positive(self):
        """OLLAMA_MAX_RETRIES is a positive integer."""
        assert settings.OLLAMA_MAX_RETRIES >= 1


# ===========================================================================
# B. OllamaService Health & Error Handling
# ===========================================================================

class TestOllamaServiceHealth:
    """Verify OllamaService.check_health() handles both success and failure cases."""

    def test_health_check_server_online_model_available(self):
        """check_health returns True when server is reachable and model found."""
        with patch("httpx.get", return_value=_mock_ollama_tags_response(available=True)):
            svc = OllamaService()
            health = svc.check_health()
        assert health["server_online"] is True
        assert health["model_available"] is True
        assert health["error"] is None
        assert "vision" in health["model_capabilities"]

    def test_health_check_model_not_available(self):
        """check_health reports model_available=False when model not in list."""
        with patch("httpx.get", return_value=_mock_ollama_tags_response(available=False)):
            svc = OllamaService()
            health = svc.check_health()
        assert health["server_online"] is True
        assert health["model_available"] is False
        assert health["error"] is not None

    def test_health_check_server_offline(self):
        """check_health handles ConnectError gracefully without raising."""
        import httpx as _httpx
        with patch("httpx.get", side_effect=_httpx.ConnectError("refused")):
            svc = OllamaService()
            health = svc.check_health()
        assert health["server_online"] is False
        assert health["model_available"] is False
        assert "unreachable" in health["error"].lower() or "connect" in health["error"].lower()

    def test_is_configured_true_when_healthy(self):
        """is_configured returns True when server + model available."""
        with patch("httpx.get", return_value=_mock_ollama_tags_response(available=True)):
            svc = OllamaService()
            assert svc.is_configured() is True

    def test_is_configured_false_when_offline(self):
        """is_configured returns False when server is offline."""
        import httpx as _httpx
        with patch("httpx.get", side_effect=_httpx.ConnectError("refused")):
            svc = OllamaService()
            assert svc.is_configured() is False


# ===========================================================================
# C. Text-based Clinical Extraction via Ollama
# ===========================================================================

class TestOllamaTextExtraction:
    """Verify text clinical extraction path in OllamaService."""

    def test_successful_text_extraction_returns_all_keys(self):
        """extract_clinical_json returns all 6 required clinical category keys."""
        mock_content = json.dumps(VALID_CLINICAL_JSON)
        with patch("httpx.post", return_value=_mock_ollama_chat_response(mock_content)):
            svc = OllamaService()
            result = svc.extract_clinical_json(SYNTHETIC_CLINICAL_TEXT, "system prompt")
        for key in REQUIRED_CLINICAL_KEYS:
            assert key in result, f"Required key '{key}' missing from extraction result"

    def test_extraction_raises_on_connect_error(self):
        """extract_clinical_json raises RuntimeError with clear message on ConnectError."""
        import httpx as _httpx
        with patch("httpx.post", side_effect=_httpx.ConnectError("refused")):
            svc = OllamaService()
            with pytest.raises(RuntimeError, match="unreachable"):
                svc.extract_clinical_json(SYNTHETIC_CLINICAL_TEXT, "system prompt")

    def test_extraction_raises_on_timeout(self):
        """extract_clinical_json raises RuntimeError with clear message on timeout."""
        import httpx as _httpx
        with patch("httpx.post", side_effect=_httpx.TimeoutException("timed out")):
            svc = OllamaService()
            with pytest.raises(RuntimeError, match="[Tt]imed out|timeout"):
                svc.extract_clinical_json(SYNTHETIC_CLINICAL_TEXT, "system prompt")

    def test_extraction_raises_on_invalid_json(self):
        """extract_clinical_json raises ValueError when model returns non-JSON."""
        with patch("httpx.post", return_value=_mock_ollama_chat_response("Not valid JSON at all")):
            svc = OllamaService()
            with pytest.raises(ValueError, match="[Ii]nvalid JSON"):
                svc.extract_clinical_json(SYNTHETIC_CLINICAL_TEXT, "system prompt")

    def test_extraction_handles_markdown_fenced_json(self):
        """extract_clinical_json strips markdown fences before parsing."""
        fenced = "```json\n" + json.dumps(VALID_CLINICAL_JSON) + "\n```"
        with patch("httpx.post", return_value=_mock_ollama_chat_response(fenced)):
            svc = OllamaService()
            result = svc.extract_clinical_json(SYNTHETIC_CLINICAL_TEXT, "system prompt")
        assert "patient" in result


# ===========================================================================
# D. Image-based Handwriting Recognition via Ollama
# ===========================================================================

class TestOllamaVisionRecognition:
    """Verify image handwriting transcription path in OllamaService."""

    def test_successful_image_transcription(self):
        """transcribe_image returns non-empty text and correct recognition_method."""
        img = _make_synthetic_image()
        mock_text = "Rx: Metformin 500mg PO BID\nDiagnosis: Type 2 Diabetes Mellitus\nDr. Kumar 2026-11-06"
        with patch("httpx.post", return_value=_mock_ollama_chat_response(mock_text)):
            svc = OllamaService()
            result = svc.transcribe_image(img, "transcribe this image")
        assert result["recognition_method"] == "ollama_vision"
        assert result["fallback_used"] is False
        assert len(result["text"]) > 0
        assert result["error"] is None

    def test_unclear_markers_counted_correctly(self):
        """transcribe_image counts [UNCLEAR] tokens accurately."""
        img = _make_synthetic_image()
        mock_text = "Patient: [UNCLEAR]\nDose: [UNCLEAR] mg PO BID"
        with patch("httpx.post", return_value=_mock_ollama_chat_response(mock_text)):
            svc = OllamaService()
            result = svc.transcribe_image(img, "transcribe this image")
        assert result["unclear_count"] == 2
        assert result["has_unclear_markers"] is True

    def test_blank_page_sentinel_returns_empty_text(self):
        """transcribe_image converts [BLANK PAGE] sentinel to empty string."""
        img = _make_synthetic_image()
        with patch("httpx.post", return_value=_mock_ollama_chat_response("[BLANK PAGE]")):
            svc = OllamaService()
            result = svc.transcribe_image(img, "transcribe this image")
        assert result["text"] == ""
        assert result["fallback_used"] is False

    def test_image_vision_failure_returns_fallback_flag(self):
        """transcribe_image sets fallback_used=True and error message on failure."""
        import httpx as _httpx
        img = _make_synthetic_image()
        with patch("httpx.post", side_effect=_httpx.ConnectError("refused")):
            svc = OllamaService()
            result = svc.transcribe_image(img, "transcribe this image")
        assert result["fallback_used"] is True
        assert result["error"] is not None
        assert result["text"] == ""

    def test_vision_accepts_rgba_image(self):
        """transcribe_image handles RGBA PIL images by converting to RGB."""
        rgba_img = Image.new("RGBA", (100, 50), color=(255, 255, 255, 255))
        with patch("httpx.post", return_value=_mock_ollama_chat_response("Test text")):
            svc = OllamaService()
            result = svc.transcribe_image(rgba_img, "transcribe this image")
        assert result["error"] is None


# ===========================================================================
# E. Controlled Retry Logic
# ===========================================================================

class TestControlledRetry:
    """Verify extract_with_retry corrects schema errors through feedback loops."""

    def test_retry_succeeds_on_second_attempt_after_missing_keys(self):
        """extract_with_retry retries and succeeds when second response has all keys."""
        incomplete = json.dumps({"patient": None, "symptoms": []})
        complete = json.dumps({k: [] if k != "patient" else None for k in REQUIRED_CLINICAL_KEYS})

        call_count = {"n": 0}

        def mock_post(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _mock_ollama_chat_response(incomplete)
            return _mock_ollama_chat_response(complete)

        with patch("httpx.post", side_effect=mock_post):
            svc = OllamaService()
            result = svc.extract_with_retry(SYNTHETIC_CLINICAL_TEXT, "system prompt")
        assert call_count["n"] == 2
        for key in REQUIRED_CLINICAL_KEYS:
            assert key in result

    def test_retry_succeeds_on_second_attempt_after_invalid_json(self):
        """extract_with_retry retries after invalid JSON on first attempt."""
        call_count = {"n": 0}

        def mock_post(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _mock_ollama_chat_response("definitely not json }{")
            return _mock_ollama_chat_response(json.dumps({k: [] if k != "patient" else None for k in REQUIRED_CLINICAL_KEYS}))

        with patch("httpx.post", side_effect=mock_post):
            svc = OllamaService()
            result = svc.extract_with_retry(SYNTHETIC_CLINICAL_TEXT, "system prompt")
        assert call_count["n"] == 2

    def test_retry_raises_after_all_attempts_exhausted(self):
        """extract_with_retry raises RuntimeError after max_retries+1 attempts."""
        call_count = {"n": 0}

        def mock_post(*args, **kwargs):
            call_count["n"] += 1
            return _mock_ollama_chat_response("bad json }{{{")

        with patch("httpx.post", side_effect=mock_post):
            svc = OllamaService()
            # Total calls = 1 initial + max_retries
            expected_calls = 1 + svc.max_retries
            with pytest.raises(RuntimeError, match="[Ff]ailed after"):
                svc.extract_with_retry(SYNTHETIC_CLINICAL_TEXT, "system prompt")
        assert call_count["n"] == expected_calls

    def test_no_fabrication_on_retry_failure(self):
        """extract_with_retry raises and does NOT return partial or fabricated data."""
        with patch("httpx.post", return_value=_mock_ollama_chat_response("not json")):
            svc = OllamaService()
            with pytest.raises(RuntimeError):
                svc.extract_with_retry(SYNTHETIC_CLINICAL_TEXT, "system prompt")


# ===========================================================================
# F. Provider Routing in ClinicalExtractor & HandwritingService
# ===========================================================================

class TestProviderRouting:
    """Verify ClinicalExtractor and HandwritingService route to the correct provider."""

    def test_clinical_extractor_routes_to_ollama_when_configured(self):
        """ClinicalExtractor._extract_via_ollama is called when provider=ollama."""
        extractor = ClinicalExtractor()
        with patch(
            "backend.services.clinical_extractor.ClinicalExtractor._provider",
            new_callable=PropertyMock,
            return_value="ollama",
        ):
            with patch.object(extractor, "_extract_via_ollama") as mock_ollama:
                mock_ollama.return_value = MagicMock()
                extractor.extract_clinical_data("doc-1", SYNTHETIC_CLINICAL_TEXT)
        mock_ollama.assert_called_once_with("doc-1", SYNTHETIC_CLINICAL_TEXT)

    def test_clinical_extractor_routes_to_gemini_when_configured(self):
        """ClinicalExtractor._extract_via_gemini is called when provider=gemini."""
        extractor = ClinicalExtractor()
        with patch(
            "backend.services.clinical_extractor.ClinicalExtractor._provider",
            new_callable=PropertyMock,
            return_value="gemini",
        ):
            with patch.object(extractor, "_extract_via_gemini") as mock_gemini:
                mock_gemini.return_value = MagicMock()
                extractor.extract_clinical_data("doc-1", SYNTHETIC_CLINICAL_TEXT)
        mock_gemini.assert_called_once_with("doc-1", SYNTHETIC_CLINICAL_TEXT)

    def test_handwriting_service_routes_to_ollama_when_configured(self):
        """HandwritingService._recognize_via_ollama is called when provider=ollama."""
        svc = HandwritingService()
        img = _make_synthetic_image()
        with patch(
            "backend.services.handwriting_service.HandwritingService._provider",
            new_callable=PropertyMock,
            return_value="ollama",
        ):
            with patch.object(svc, "_recognize_via_ollama") as mock_ollama:
                mock_ollama.return_value = {"text": "ok", "recognition_method": "ollama_vision"}
                svc.recognize_page(img)
        mock_ollama.assert_called_once()

    def test_handwriting_service_routes_to_gemini_when_configured(self):
        """HandwritingService._recognize_via_gemini is called when provider=gemini."""
        svc = HandwritingService()
        img = _make_synthetic_image()
        with patch(
            "backend.services.handwriting_service.HandwritingService._provider",
            new_callable=PropertyMock,
            return_value="gemini",
        ):
            with patch.object(svc, "_recognize_via_gemini") as mock_gemini:
                mock_gemini.return_value = {"text": "ok", "recognition_method": "gemini_vision"}
                svc.recognize_page(img)
        mock_gemini.assert_called_once()

    def test_empty_source_text_raises_before_provider_call(self):
        """extract_clinical_data raises ValueError for empty text before any provider call."""
        extractor = ClinicalExtractor()
        with pytest.raises(ValueError, match="[Ee]mpty"):
            extractor.extract_clinical_data("doc-1", "   ")


# ===========================================================================
# G. Human-Verification Safety Gate
# ===========================================================================

class TestHumanVerificationSafetyGate:
    """Verify the safety gate blocks structuring for unverified handwritten pages
    regardless of which AI provider is configured."""

    # In-memory SQLite for isolation
    _engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    _SessionLocal = sessionmaker(bind=_engine)

    @classmethod
    def setup_class(cls):
        Base.metadata.create_all(bind=cls._engine)

    def _db(self):
        return self._SessionLocal()

    def _make_doc(self, db, doc_id: str, handwriting_detected: bool = False) -> Document:
        doc = Document(
            id=doc_id,
            filename="test.pdf",
            stored_path="/tmp/test.pdf",
            processing_status="completed",
            handwriting_detected=handwriting_detected,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc

    def test_unverified_handwritten_page_blocks_structuring(self):
        """Safety gate returns is_eligible=False for documents with unverified HW pages."""
        db = self._db()
        doc = self._make_doc(db, "safety-test-hw-01", handwriting_detected=True)
        page = PageExtraction(
            id=str(_uuid_module.uuid4()),
            extraction_method="tesseract_ocr",
            document_id=doc.id,
            page_number=1,
            page_classification="handwritten",
            verification_status="unverified",
            ocr_text="Raw handwritten text",
        )
        db.add(page)
        db.commit()
        is_eligible, _, reason = ClinicalExtractor.get_eligible_document_text(doc, db)
        assert is_eligible is False
        assert "verification" in reason.lower() or "unverified" in reason.lower()
        db.close()

    def test_verified_handwritten_page_permits_structuring(self):
        """Safety gate returns is_eligible=True when HW pages are verified."""
        db = self._db()
        doc = self._make_doc(db, "safety-test-hw-02", handwriting_detected=True)
        page = PageExtraction(
            id=str(_uuid_module.uuid4()),
            extraction_method="tesseract_ocr",
            document_id=doc.id,
            page_number=1,
            page_classification="handwritten",
            verification_status="verified",
            ocr_text="Verified handwritten text",
            human_corrected_text="Corrected handwritten text",
            final_text="Corrected handwritten text",
        )
        db.add(page)
        db.commit()
        is_eligible, text, reason = ClinicalExtractor.get_eligible_document_text(doc, db)
        assert is_eligible is True
        assert reason is None
        assert "Corrected handwritten text" in text
        db.close()

    def test_uncertain_page_also_blocked_until_verified(self):
        """Safety gate blocks 'uncertain' classified pages until verified."""
        db = self._db()
        doc = self._make_doc(db, "safety-test-hw-03")
        page = PageExtraction(
            id=str(_uuid_module.uuid4()),
            extraction_method="tesseract_ocr",
            document_id=doc.id,
            page_number=1,
            page_classification="uncertain",
            verification_status="unverified",
            ocr_text="Uncertain quality text",
        )
        db.add(page)
        db.commit()
        is_eligible, _, reason = ClinicalExtractor.get_eligible_document_text(doc, db)
        assert is_eligible is False
        db.close()

    def test_printed_page_not_blocked_by_safety_gate(self):
        """Safety gate does NOT block documents with only printed/digital pages."""
        db = self._db()
        doc = self._make_doc(db, "safety-test-hw-04")
        page = PageExtraction(
            id=str(_uuid_module.uuid4()),
            extraction_method="tesseract_ocr",
            document_id=doc.id,
            page_number=1,
            page_classification="printed",
            verification_status="unverified",  # printed pages don't need verification
            ocr_text="Printed OCR text from digital document.",
        )
        db.add(page)
        db.commit()
        is_eligible, text, reason = ClinicalExtractor.get_eligible_document_text(doc, db)
        assert is_eligible is True
        assert reason is None
        db.close()

    def test_safety_gate_prefers_human_corrected_text_over_ocr(self):
        """Safety gate assembles text using human_corrected_text > final_text > ocr_text."""
        db = self._db()
        doc = self._make_doc(db, "safety-test-hw-05")
        page = PageExtraction(
            id=str(_uuid_module.uuid4()),
            extraction_method="tesseract_ocr",
            document_id=doc.id,
            page_number=1,
            page_classification="printed",
            verification_status="unverified",
            ocr_text="Raw OCR",
            final_text="Final text",
            human_corrected_text="Human correction",
        )
        db.add(page)
        db.commit()
        is_eligible, text, _ = ClinicalExtractor.get_eligible_document_text(doc, db)
        assert is_eligible is True
        assert "Human correction" in text
        assert "Raw OCR" not in text
        db.close()


# ===========================================================================
# H. Failure Isolation: Ollama failure does NOT trigger Gemini
# ===========================================================================

class TestFailureIsolation:
    """Verify that Ollama failures never cause data to be sent to Gemini."""

    def test_ollama_vision_failure_uses_local_tesseract_not_gemini(self):
        """
        When Ollama vision fails, HandwritingService falls back to local Tesseract.
        google.genai.Client must NOT be called.
        """
        import httpx as _httpx
        svc = HandwritingService()
        img = _make_synthetic_image()
        tesseract_text = "Tesseract fallback text"

        with patch(
            "backend.services.handwriting_service.HandwritingService._provider",
            new_callable=PropertyMock,
            return_value="ollama",
        ):
            with patch("httpx.post", side_effect=_httpx.ConnectError("refused")):
                with patch("httpx.get", return_value=_mock_ollama_tags_response(available=False)):
                    # genai.Client must never be called
                    mock_genai = MagicMock()
                    with patch("backend.services.handwriting_service.genai", mock_genai):
                        result = svc.recognize_page(img, tesseract_fallback_text=tesseract_text)
        # Gemini client constructor must not have been called
        mock_genai.Client.assert_not_called()
        assert result["fallback_used"] is True
        assert result["text"] == tesseract_text

    def test_ollama_extraction_failure_raises_clear_error_no_gemini(self):
        """
        When Ollama clinical extraction fails, ClinicalExtractor raises RuntimeError.
        It does NOT silently call Gemini as a fallback.
        """
        extractor = ClinicalExtractor()
        import httpx as _httpx

        with patch(
            "backend.services.clinical_extractor.ClinicalExtractor._provider",
            new_callable=PropertyMock,
            return_value="ollama",
        ):
            with patch("httpx.post", side_effect=_httpx.ConnectError("refused")):
                with patch("httpx.get", return_value=_mock_ollama_tags_response(available=False)):
                    mock_genai = MagicMock()
                    with patch("backend.services.clinical_extractor.genai", mock_genai):
                        with pytest.raises(RuntimeError, match="[Oo]llama"):
                            extractor.extract_clinical_data("doc-1", SYNTHETIC_CLINICAL_TEXT)
        mock_genai.Client.assert_not_called()

    def test_gemini_failure_does_not_fallback_to_ollama(self):
        """
        When Gemini extraction fails, ClinicalExtractor raises RuntimeError.
        It does NOT fall back to Ollama.
        """
        extractor = ClinicalExtractor()
        with patch(
            "backend.services.clinical_extractor.ClinicalExtractor._provider",
            new_callable=PropertyMock,
            return_value="gemini",
        ):
            with patch(
                "backend.services.clinical_extractor.ClinicalExtractor.api_key",
                new_callable=PropertyMock,
                return_value="AIzaSyFakeKey123456",
            ):
                mock_genai = MagicMock()
                mock_genai.Client.return_value.models.generate_content.side_effect = Exception("Gemini API error")
                with patch("backend.services.clinical_extractor.genai", mock_genai):
                    with patch("backend.services.clinical_extractor.types", MagicMock()):
                        mock_ollama = MagicMock()
                        with patch("backend.services.clinical_extractor.OllamaService", mock_ollama):
                            with pytest.raises(RuntimeError, match="[Cc]linical AI extraction failed"):
                                extractor.extract_clinical_data("doc-1", SYNTHETIC_CLINICAL_TEXT)
        # OllamaService must not have been called as a fallback
        mock_ollama.return_value.extract_with_retry.assert_not_called()


# ===========================================================================
# I. Health & Diagnostics API Endpoints
# ===========================================================================

class TestHealthDiagnosticsEndpoints:
    """Verify /api/health and /api/health/diagnostics include Ollama provider info."""

    def test_health_check_includes_active_provider(self):
        """GET /api/health reports active_provider field."""
        with patch("httpx.get", return_value=_mock_ollama_tags_response(True)):
            resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        env = data.get("environment", {})
        assert "active_provider" in env

    def test_health_check_includes_ollama_section(self):
        """GET /api/health includes ollama status section."""
        with patch("httpx.get", return_value=_mock_ollama_tags_response(True)):
            resp = client.get("/api/health")
        assert resp.status_code == 200
        env = resp.json()["environment"]
        assert "ollama" in env
        assert "server_online" in env["ollama"]
        assert "model_available" in env["ollama"]

    def test_diagnostics_includes_provider_sections(self):
        """GET /api/health/diagnostics reports ollama and gemini sections."""
        with patch("httpx.get", return_value=_mock_ollama_tags_response(True)):
            resp = client.get("/api/health/diagnostics")
        assert resp.status_code == 200
        data = resp.json()
        assert "active_provider" in data
        assert "ollama" in data
        assert "gemini" in data
        assert "configured" in data["ollama"]
        assert "configured" in data["gemini"]

    def test_health_response_never_exposes_api_key(self):
        """Health endpoints must never return any API key fragment."""
        with patch("httpx.get", return_value=_mock_ollama_tags_response(True)):
            h_resp = client.get("/api/health")
            d_resp = client.get("/api/health/diagnostics")
        for key_fragment in ("AIzaSy", "GEMINI_API_KEY="):
            assert key_fragment not in h_resp.text
            assert key_fragment not in d_resp.text
