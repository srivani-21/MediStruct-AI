import io
import os
from pathlib import Path
import pytest
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import init_db, SessionLocal
from backend.models.document import Document
from backend.services.pdf_extractor import DigitalPDFExtractor
from backend.services.ocr_extractor import OCRExtractor
from backend.services.handwriting_evaluator import HandwritingEvaluator
from backend.services.document_processor import DocumentProcessor

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    yield


def create_digital_pdf(text_lines: list, filename: str) -> Path:
    """Helper: Creates a digital text PDF with an embedded font text layer."""
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = upload_dir / filename

    c = canvas.Canvas(str(pdf_path))
    y = 750
    for line in text_lines:
        c.drawString(72, y, line)
        y -= 25
    c.save()
    return pdf_path


def create_scanned_image_pdf(text_to_draw: str, filename: str) -> Path:
    """
    Helper: Creates a true scanned/image-only PDF with NO text layer.
    Draws text into a bitmap raster image (PIL), then saves the raster as PDF.
    """
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = upload_dir / filename

    # Create 800x1000 white image
    img = Image.new("RGB", (800, 1000), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    # Draw dark text on white canvas
    draw.text((80, 200), text_to_draw, fill=(0, 0, 0))

    # Save as PDF without any text layer
    img.save(str(pdf_path), "PDF", resolution=150.0)
    return pdf_path


def test_digital_pdf_text_extraction():
    """Verify digital PDF text extraction via pdfplumber/pypdf preserves page numbers and text."""
    lines = [
        "CLINICAL INTAKE REPORT",
        "Patient ID: PT-39201",
        "Primary Diagnosis: Acute Bronchitis",
        "Prescription: Amoxicillin 500mg TID for 7 days",
    ]
    pdf_path = create_digital_pdf(lines, "test_digital_sample.pdf")

    try:
        extractor = DigitalPDFExtractor()
        pages = extractor.extract_text_by_pages(str(pdf_path))

        assert len(pages) == 1
        assert pages[0]["page_number"] == 1
        assert pages[0]["is_digital"] is True
        assert "Acute Bronchitis" in pages[0]["text"]
        assert "Amoxicillin" in pages[0]["text"]
        assert pages[0]["char_count"] > 50

    finally:
        if pdf_path.exists():
            pdf_path.unlink()


def test_scanned_image_pdf_ocr():
    """Verify scanned image-only PDF triggers OCR and extracts text via Tesseract."""
    scanned_text = "RADIOLOGY REPORT: Chest X-Ray reveals mild bilateral interstitial opacity."
    pdf_path = create_scanned_image_pdf(scanned_text, "test_scanned_xray.pdf")

    try:
        # 1. Digital extractor should find NO text layer
        digital_pages = DigitalPDFExtractor.extract_text_by_pages(str(pdf_path))
        assert len(digital_pages) == 1
        assert digital_pages[0]["char_count"] == 0
        assert digital_pages[0]["is_digital"] is False

        # 2. OCR extractor should render and recognize text
        ocr = OCRExtractor()
        is_ok, msg = ocr.check_tesseract_available()
        assert is_ok, f"Tesseract not accessible: {msg}"

        ocr_result = ocr.ocr_single_page(str(pdf_path), page_number=1)
        assert ocr_result["char_count"] > 0
        # Check for key tokens in recognized OCR string
        assert "RADIOLOGY" in ocr_result["text"] or "X-Ray" in ocr_result["text"] or "opacity" in ocr_result["text"]

    finally:
        if pdf_path.exists():
            pdf_path.unlink()


def test_multipage_mixed_pdf_processing():
    """Verify a mixed document (Page 1 digital, Page 2 scanned) processes each page appropriately."""
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = upload_dir / "test_mixed_doc.pdf"

    # Create Page 1 digital, Page 2 image
    c = canvas.Canvas(str(pdf_path))
    c.drawString(72, 750, "PAGE 1: Digital Consultation Notes for Patient Robert Green.")
    c.drawString(72, 725, "Symptoms: Low grade fever and persistent fatigue for 5 days.")
    c.showPage()  # Move to Page 2 (leave blank of text, draw image)
    
    # Raster bitmap for page 2
    img2 = Image.new("RGB", (400, 200), color=(255, 255, 255))
    draw2 = ImageDraw.Draw(img2)
    draw2.text((20, 80), "PAGE 2 SCANNED LAB: WBC 11.5 HGB 14.2", fill=(0, 0, 0))
    img2_path = upload_dir / "temp_img2.png"
    img2.save(str(img2_path))

    c.drawImage(str(img2_path), 72, 500, width=400, height=200)
    c.showPage()
    c.save()

    # Upload document to database
    with open(pdf_path, "rb") as f:
        upload_res = client.post("/api/documents/upload", files=[("files", ("test_mixed_doc.pdf", f, "application/pdf"))])
    assert upload_res.status_code == 201
    doc_id = upload_res.json()[0]["id"]

    try:
        # Process document
        proc_res = client.post(f"/api/documents/{doc_id}/process")
        assert proc_res.status_code == 200
        data = proc_res.json()

        assert data["page_count"] == 2
        assert data["processing_status"] == "COMPLETED"
        assert data["document_type"] == "mixed"
        assert data["extraction_method"] == "hybrid_digital_ocr"
        assert data["character_count"] > 50

        # Verify page citations exist in raw text
        doc_detail = client.get(f"/api/documents/{doc_id}").json()
        assert "--- [PAGE 1] ---" in doc_detail["raw_text"]
        assert "--- [PAGE 2] ---" in doc_detail["raw_text"]

    finally:
        client.delete(f"/api/documents/{doc_id}")
        if img2_path.exists():
            img2_path.unlink()
        if pdf_path.exists():
            pdf_path.unlink()


def test_force_ocr_override():
    """Verify that force_ocr=True applies OCR across all pages even on digital documents."""
    pdf_path = create_digital_pdf(
        ["CLINICAL LAB REPORT: Glucose 95 mg/dL, Fasting status verified."],
        "force_ocr_sample.pdf"
    )

    with open(pdf_path, "rb") as f:
        upload_res = client.post("/api/documents/upload", files=[("files", ("force_ocr_sample.pdf", f, "application/pdf"))])
    doc_id = upload_res.json()[0]["id"]

    try:
        # Process with force_ocr=true
        proc_res = client.post(f"/api/documents/{doc_id}/process?force_ocr=true")
        assert proc_res.status_code == 200
        data = proc_res.json()

        assert data["extraction_method"] == "force_tesseract_ocr"
        assert data["character_count"] > 0
        assert "Glucose" in data["preview"] or "Fasting" in data["preview"]

    finally:
        client.delete(f"/api/documents/{doc_id}")
        if pdf_path.exists():
            pdf_path.unlink()


def test_blank_scanned_pdf_fails_without_silent_success():
    """Verify that a completely blank scanned document fails and is never labeled completed."""
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = upload_dir / "blank_document.pdf"

    # Completely blank white image saved as PDF
    img = Image.new("RGB", (600, 800), color=(255, 255, 255))
    img.save(str(pdf_path), "PDF")

    with open(pdf_path, "rb") as f:
        upload_res = client.post("/api/documents/upload", files=[("files", ("blank_document.pdf", f, "application/pdf"))])
    doc_id = upload_res.json()[0]["id"]

    try:
        # Processing should return 422 or fail gracefully
        proc_res = client.post(f"/api/documents/{doc_id}/process")
        assert proc_res.status_code in [422, 500]

        # Verify DB status is FAILED, NOT COMPLETED
        status_res = client.get(f"/api/documents/{doc_id}/status").json()
        assert status_res["status"] == "FAILED"
        assert "No legible text could be extracted" in status_res["error_message"]

    finally:
        client.delete(f"/api/documents/{doc_id}")
        if pdf_path.exists():
            pdf_path.unlink()


def test_handwriting_evaluation_and_detection():
    """Verify that handwriting evaluator identifies prescription/handwritten clinical records."""
    evaluator = HandwritingEvaluator()

    # Case 1: Prescription doctor note keyword
    res1 = evaluator.evaluate_page(
        filename="rx_doctor_note_prescriptions.pdf",
        ocr_confidence=55.0,
        extracted_text="Tab Metformin 500 BD Sig",
        char_count=25,
    )
    assert res1["handwriting_detected"] is True
    assert "Multimodal Vision AI" in res1["recommendation"]

    # Case 2: Clean printed documentation
    res2 = evaluator.evaluate_page(
        filename="hospital_discharge_summary.pdf",
        ocr_confidence=95.0,
        extracted_text="Patient admitted on October 14th with shortness of breath.",
        char_count=58,
    )
    assert res2["handwriting_detected"] is False
    assert "Standard OCR/Digital parsing is appropriate" in res2["recommendation"]
