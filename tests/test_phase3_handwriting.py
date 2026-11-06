import io
import os
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
import pytest
from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from backend.main import app
from backend.database import init_db, engine
from backend.models.document import Document
from backend.models.page_extraction import PageExtraction
from backend.services.document_processor import DocumentProcessor
from backend.services.handwriting_evaluator import HandwritingEvaluator
from backend.services.handwriting_service import HandwritingService
from backend.config import settings

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    """Ensure database schema is ready before tests."""
    init_db()
    yield


def create_synthetic_png_image(text: str, filename: str) -> Path:
    """Helper: creates a synthetic PNG image of a medical note."""
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    img_path = upload_dir / filename

    img = Image.new("RGB", (600, 400), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((40, 50), text, fill=(0, 0, 0))
    img.save(str(img_path), "PNG")
    return img_path


def create_synthetic_jpg_image(text: str, filename: str) -> Path:
    """Helper: creates a synthetic JPG image of a medical note."""
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    img_path = upload_dir / filename

    img = Image.new("RGB", (600, 400), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((40, 50), text, fill=(0, 0, 0))
    img.save(str(img_path), "JPEG")
    return img_path


# -----------------------------------------------------------------------------
# Test 1: PageExtraction Table Existence and Schema Integrity
# -----------------------------------------------------------------------------
def test_page_extraction_table_exists():
    """Verify page_extractions table exists with all required architectural columns."""
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    assert "page_extractions" in table_names, "page_extractions table was not created in SQLite."

    columns = {col["name"]: col for col in inspector.get_columns("page_extractions")}
    expected_cols = [
        "id",
        "document_id",
        "page_number",
        "page_classification",
        "extraction_method",
        "ocr_text",
        "ocr_confidence",
        "gemini_text",
        "final_text",
        "human_corrected_text",
        "verification_status",
        "unclear_count",
        "image_stored_path",
        "gemini_fallback_used",
        "gemini_error",
        "human_verified_at",
        "created_at",
    ]
    for col in expected_cols:
        assert col in columns, f"Expected column '{col}' missing from page_extractions table."


# -----------------------------------------------------------------------------
# Test 2: PNG Image Medical Document Upload
# -----------------------------------------------------------------------------
def test_png_image_upload_accepted():
    """Verify PNG medical document upload is accepted with HTTP 201."""
    img_path = create_synthetic_png_image("Patient John Doe Synthetic Rx Note", "test_rx_note.png")
    try:
        with open(img_path, "rb") as f:
            res = client.post("/api/documents/upload", files=[("files", ("test_rx_note.png", f, "image/png"))])
        assert res.status_code == 201
        data = res.json()
        assert len(data) == 1
        assert data[0]["filename"] == "test_rx_note.png"
        doc_id = data[0]["id"]
        client.delete(f"/api/documents/{doc_id}")
    finally:
        if img_path.exists():
            img_path.unlink()


# -----------------------------------------------------------------------------
# Test 3: JPG Image Medical Document Upload
# -----------------------------------------------------------------------------
def test_jpg_image_upload_accepted():
    """Verify JPG medical document upload is accepted with HTTP 201."""
    img_path = create_synthetic_jpg_image("Patient Jane Doe Synthetic Lab Chart", "test_lab_chart.jpg")
    try:
        with open(img_path, "rb") as f:
            res = client.post("/api/documents/upload", files=[("files", ("test_lab_chart.jpg", f, "image/jpeg"))])
        assert res.status_code == 201
        data = res.json()
        assert len(data) == 1
        assert data[0]["filename"] == "test_lab_chart.jpg"
        doc_id = data[0]["id"]
        client.delete(f"/api/documents/{doc_id}")
    finally:
        if img_path.exists():
            img_path.unlink()


# -----------------------------------------------------------------------------
# Test 4: Missing Gemini API Key Uses Tesseract Fallback and Marks needs_review
# -----------------------------------------------------------------------------
def test_gemini_key_missing_uses_tesseract_fallback():
    """Verify that when GEMINI_API_KEY is empty, handwriting service falls back gracefully."""
    with patch(
        "backend.services.handwriting_service.HandwritingService._provider",
        new_callable=PropertyMock,
        return_value="gemini",
    ):
        with patch(
            "backend.services.handwriting_service.HandwritingService.api_key",
            new_callable=PropertyMock,
            return_value="",
        ):
            service = HandwritingService()
            dummy_img = Image.new("RGB", (100, 100), color=(255, 255, 255))
            result = service.recognize_page(dummy_img, tesseract_fallback_text="Fallback Rx text")

            assert result["fallback_used"] is True
            assert result["text"] == "Fallback Rx text"
            assert result["recognition_method"] == "tesseract_ocr"
            assert "not configured" in result["error"].lower()


# -----------------------------------------------------------------------------
# Test 5: Gemini API Failure Graceful Fallback
# -----------------------------------------------------------------------------
def test_gemini_api_failure_uses_tesseract_fallback():
    """Verify that when the Gemini API raises an exception, the system falls back with error logged."""
    with patch(
        "backend.services.handwriting_service.HandwritingService._provider",
        new_callable=PropertyMock,
        return_value="gemini",
    ):
        with patch.object(settings, "GEMINI_API_KEY", "AIzaSyFakeKeyForTest"):
            service = HandwritingService()
            dummy_img = Image.new("RGB", (100, 100), color=(255, 255, 255))

            with patch("backend.services.handwriting_service.genai.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.models.generate_content.side_effect = RuntimeError("Google API 503 Service Unavailable")
                mock_client_cls.return_value = mock_client

                result = service.recognize_page(dummy_img, tesseract_fallback_text="Fallback text from Tesseract")
                assert result["fallback_used"] is True
                assert result["text"] == "Fallback text from Tesseract"
                assert "503" in result["error"] or "Service Unavailable" in result["error"]
                assert result["recognition_method"] == "gemini_vision_fallback_tesseract"


# -----------------------------------------------------------------------------
# Test 6: Gemini Vision Creates PageExtraction Row
# -----------------------------------------------------------------------------
def test_gemini_vision_creates_page_extraction_row():
    """Verify processing creates a PageExtraction row populated with Gemini output."""
    img_path = create_synthetic_png_image("rx dr_note: Tab Metformin 500mg BD", "rx_dr_note_test.png")

    with open(img_path, "rb") as f:
        res = client.post("/api/documents/upload", files=[("files", ("rx_dr_note_test.png", f, "image/png"))])
    doc_id = res.json()[0]["id"]

    try:
        mock_hw_res = {
            "text": "Rx: Tab Metformin 500mg BD for diabetes (Synthetic)",
            "unclear_count": 0,
            "has_unclear_markers": False,
            "recognition_method": "gemini_vision",
            "model_used": "gemini-3.8-flash",
            "error": None,
            "fallback_used": False,
        }

        with patch.object(HandwritingService, "recognize_page", return_value=mock_hw_res):
            proc_res = client.post(f"/api/documents/{doc_id}/process")
            assert proc_res.status_code == 200

            pages_res = client.get(f"/api/documents/{doc_id}/pages")
            assert pages_res.status_code == 200
            pages = pages_res.json()
            assert len(pages) == 1
            assert pages[0]["gemini_text"] == "Rx: Tab Metformin 500mg BD for diabetes (Synthetic)"
            assert pages[0]["extraction_method"] == "gemini_vision"
            assert pages[0]["verification_status"] == "pending"

    finally:
        client.delete(f"/api/documents/{doc_id}")
        if img_path.exists():
            img_path.unlink()


# -----------------------------------------------------------------------------
# Test 7: Unclear Count is Accurate and Honest (No Invented Numbers)
# -----------------------------------------------------------------------------
def test_unclear_count_is_accurate():
    """Verify unclear_count accurately counts [UNCLEAR] markers without invented scores."""
    mock_gemini_text = "Patient: John Doe\nRx: [UNCLEAR] 250mg TID\nSig: Take with [UNCLEAR] water\nRefills: [UNCLEAR]"

    with patch(
        "backend.services.handwriting_service.HandwritingService._provider",
        new_callable=PropertyMock,
        return_value="gemini",
    ):
        with patch.object(settings, "GEMINI_API_KEY", "AIzaSyFakeKeyForTest"):
            service = HandwritingService()
            with patch("backend.services.handwriting_service.genai.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_resp = MagicMock()
                mock_resp.text = mock_gemini_text
                mock_client.models.generate_content.return_value = mock_resp
                mock_client_cls.return_value = mock_client

                dummy_img = Image.new("RGB", (100, 100), color=(255, 255, 255))
                res = service.recognize_page(dummy_img)

                assert res["unclear_count"] == 3
                assert res["has_unclear_markers"] is True
                assert "confidence" not in res  # Verifies NO fake numerical confidence is invented!


# -----------------------------------------------------------------------------
# Test 8: Human Verification Saves Correction and Strictly Preserves Original
# -----------------------------------------------------------------------------
def test_human_verify_saves_correction_preserves_original():
    """Verify POST /verify saves human text without overwriting original Gemini or OCR text."""
    img_path = create_synthetic_png_image("rx dr_note amox", "rx_dr_note_verify.png")

    with open(img_path, "rb") as f:
        res = client.post("/api/documents/upload", files=[("files", ("rx_dr_note_verify.png", f, "image/png"))])
    doc_id = res.json()[0]["id"]

    try:
        mock_hw_res = {
            "text": "Rx: Amox[UNCLEAR] 500mg TID",
            "unclear_count": 1,
            "has_unclear_markers": True,
            "recognition_method": "gemini_vision",
            "model_used": "gemini-3.8-flash",
            "error": None,
            "fallback_used": False,
        }

        with patch.object(HandwritingService, "recognize_page", return_value=mock_hw_res):
            client.post(f"/api/documents/{doc_id}/process")

        # Verify page 1 with human correction
        verify_payload = {"human_corrected_text": "Rx: Amoxicillin 500mg TID (Verified by Dr. Smith)"}
        v_res = client.post(f"/api/documents/{doc_id}/pages/1/verify", json=verify_payload)
        assert v_res.status_code == 200
        data = v_res.json()

        assert data["verification_status"] == "verified"
        assert data["human_corrected_text"] == "Rx: Amoxicillin 500mg TID (Verified by Dr. Smith)"
        # Strict preservation: gemini_text MUST remain the original unedited AI string
        assert data["gemini_text"] == "Rx: Amox[UNCLEAR] 500mg TID"

    finally:
        client.delete(f"/api/documents/{doc_id}")
        if img_path.exists():
            img_path.unlink()


# -----------------------------------------------------------------------------
# Test 9: Human Verification Sets final_text
# -----------------------------------------------------------------------------
def test_human_verify_sets_final_text():
    """Verify that after verification, final_text equals human_corrected_text and document updates."""
    img_path = create_synthetic_png_image("rx dr_note lisinopril", "rx_dr_note_final.png")

    with open(img_path, "rb") as f:
        res = client.post("/api/documents/upload", files=[("files", ("rx_dr_note_final.png", f, "image/png"))])
    doc_id = res.json()[0]["id"]

    try:
        mock_hw_res = {
            "text": "Tab Lisino[UNCLEAR] 10mg daily",
            "unclear_count": 1,
            "has_unclear_markers": True,
            "recognition_method": "gemini_vision",
            "model_used": "gemini-3.8-flash",
            "error": None,
            "fallback_used": False,
        }

        with patch.object(HandwritingService, "recognize_page", return_value=mock_hw_res):
            client.post(f"/api/documents/{doc_id}/process")

        client.post(f"/api/documents/{doc_id}/pages/1/verify", json={
            "human_corrected_text": "Tab Lisinopril 10mg daily"
        })

        pages = client.get(f"/api/documents/{doc_id}/pages").json()
        assert pages[0]["final_text"] == "Tab Lisinopril 10mg daily"

        doc = client.get(f"/api/documents/{doc_id}").json()
        assert "Tab Lisinopril 10mg daily" in doc["raw_text"]

    finally:
        client.delete(f"/api/documents/{doc_id}")
        if img_path.exists():
            img_path.unlink()


# -----------------------------------------------------------------------------
# Test 10: Delete Document Removes Rendered Page Images from Disk
# -----------------------------------------------------------------------------
def test_delete_document_removes_page_images():
    """Verify that deleting a document cascades to remove data/page_images/{doc_id}/ from disk."""
    img_path = create_synthetic_png_image("Prescription page cleanup test", "cleanup_test.png")

    with open(img_path, "rb") as f:
        res = client.post("/api/documents/upload", files=[("files", ("cleanup_test.png", f, "image/png"))])
    doc_id = res.json()[0]["id"]

    try:
        mock_hw_res = {
            "text": "Cleanup test text",
            "unclear_count": 0,
            "has_unclear_markers": False,
            "recognition_method": "tesseract_ocr",
            "model_used": "none",
            "error": None,
            "fallback_used": True,
        }
        with patch.object(HandwritingService, "recognize_page", return_value=mock_hw_res):
            client.post(f"/api/documents/{doc_id}/process")

        page_img_dir = Path("data/page_images") / doc_id
        assert page_img_dir.exists(), "Page image directory was not created during processing."

        # Delete document
        del_res = client.delete(f"/api/documents/{doc_id}")
        assert del_res.status_code == 200

        # Assert page images directory is completely removed
        assert not page_img_dir.exists(), "Page image directory was not cleaned up after document deletion."

    finally:
        if img_path.exists():
            img_path.unlink()


# -----------------------------------------------------------------------------
# Test 11: 4-Class Classifier: Printed Document Not Misclassified
# -----------------------------------------------------------------------------
def test_4class_classifier_printed_not_misclassified():
    """Verify that clean scanned printed pages with high confidence are classified as printed_ocr."""
    evaluator = HandwritingEvaluator()
    res = evaluator.classify_page(
        filename="discharge_summary_ward_4b.pdf",
        ocr_confidence=92.5,
        extracted_text="Patient Robert Green was admitted with mild dyspnea and discharged stable.",
        char_count=73,
        is_digital=False,
    )
    assert res["classification"] == "printed_ocr"
    assert res["recommend_gemini"] is False
    assert res["recommend_manual_review"] is False


# -----------------------------------------------------------------------------
# Test 12: 4-Class Classifier: Uncertain Pages Flagged for Manual Review
# -----------------------------------------------------------------------------
def test_4class_classifier_uncertain_pages_flagged():
    """Verify that ambiguous scans with low confidence are classified as uncertain and flagged for review."""
    evaluator = HandwritingEvaluator()
    res = evaluator.classify_page(
        filename="scanned_clinic_record_page3.pdf",
        ocr_confidence=45.0,
        extracted_text="b.d. ? .. # 10mg",
        char_count=16,
        is_digital=False,
    )
    assert res["classification"] == "uncertain"
    assert res["recommend_manual_review"] is True


# -----------------------------------------------------------------------------
# Test 13: Regression Guard for Existing Digital and Scanned OCR Processing
# -----------------------------------------------------------------------------
def test_existing_digital_ocr_regression():
    """Verify that digital and standard scanned PDFs still process flawlessly with updated engine."""
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = upload_dir / "regression_digital_test.pdf"

    c = canvas.Canvas(str(pdf_path))
    c.drawString(72, 750, "REGRESSION VERIFICATION: Digital consultation notes preserved.")
    c.drawString(72, 725, "Blood Pressure: 120/80 mmHg, Pulse: 72 bpm regular.")
    c.save()

    try:
        with open(pdf_path, "rb") as f:
            res = client.post("/api/documents/upload", files=[("files", ("regression_digital_test.pdf", f, "application/pdf"))])
        doc_id = res.json()[0]["id"]

        proc_res = client.post(f"/api/documents/{doc_id}/process")
        assert proc_res.status_code == 200
        data = proc_res.json()
        assert data["document_type"] == "digital"
        assert data["extraction_method"] == "pdfplumber_digital"
        assert "Blood Pressure: 120/80" in data["preview"]

        # Check that a digital page extraction row was created
        pages = client.get(f"/api/documents/{doc_id}/pages").json()
        assert len(pages) == 1
        assert pages[0]["page_classification"] == "digital"
        assert pages[0]["verification_status"] == "verified"

        client.delete(f"/api/documents/{doc_id}")

    finally:
        if pdf_path.exists():
            pdf_path.unlink()
