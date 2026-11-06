import io
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
import pytest
from reportlab.pdfgen import canvas
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.database import init_db, SessionLocal, engine
from backend.models.document import Document
from backend.models.patient import Patient
from backend.models.clinical_records import (
    Symptom,
    Diagnosis,
    Medication,
    LabResult,
    Recommendation,
)
from backend.models.page_extraction import PageExtraction
from backend.models.schemas import StructuredClinicalPayload, SymptomBase, DiagnosisBase
from backend.services.clinical_extractor import ClinicalExtractor
from backend.services.clinical_persistence import persist_structured_clinical_data
from backend.config import settings

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    yield


def create_synthetic_pdf(text_lines: list, filename: str) -> Path:
    """Helper: Creates a synthetic PDF document for testing."""
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


SYNTHETIC_CLINICAL_PAYLOAD = {
    "patient": {
        "patient_identifier": "SYNTH-8402",
        "name": "Sarah Connor (Synthetic)",
        "age": 42,
        "gender": "Female",
        "demographic_notes": "Allergic to sulfonamides, non-smoker"
    },
    "symptoms": [
        {
            "symptom_name": "Productive cough",
            "description": "Thick yellowish sputum",
            "duration": "5 days",
            "severity": "Moderate",
            "page_number": 1
        }
    ],
    "diagnoses": [
        {
            "diagnosis_name": "Community-acquired pneumonia",
            "description": "Right lower lobe consolidation",
            "diagnosis_date": "2026-11-01",
            "status": "Confirmed",
            "page_number": 1
        }
    ],
    "medications": [
        {
            "medication_name": "Azithromycin",
            "dosage": "500 mg",
            "frequency": "Once daily",
            "duration": "5 days",
            "route": "Oral",
            "page_number": 1
        }
    ],
    "lab_results": [
        {
            "test_name": "C-Reactive Protein (CRP)",
            "result_value": "48.5 mg/L",
            "numeric_value": 48.5,
            "unit": "mg/L",
            "reference_range": "< 5.0",
            "flag": "High",
            "test_date": "2026-11-01",
            "page_number": 1
        }
    ],
    "recommendations": [
        {
            "recommendation_text": "Complete full antibiotic course and rest adequately.",
            "follow_up_instructions": "Return for chest auscultation in 7 days.",
            "page_number": 1
        }
    ]
}


# -----------------------------------------------------------------------------
# Test 1 & 6: Digital Document Clinical Extraction - All 6 Categories
# -----------------------------------------------------------------------------
def test_digital_medical_document_extraction_all_six_categories():
    """Verify that a digital document is structured into all six clinical categories."""
    pdf_path = create_synthetic_pdf(
        ["CLINICAL INTAKE NOTE: Patient Sarah Connor, Age 42, Diagnosis: Community-acquired pneumonia."],
        "digital_intake_test.pdf"
    )
    with open(pdf_path, "rb") as f:
        res = client.post("/api/documents/upload", files=[("files", ("digital_intake_test.pdf", f, "application/pdf"))])
    doc_id = res.json()[0]["id"]

    try:
        # Process document
        client.post(f"/api/documents/{doc_id}/process")

        # Mock ClinicalExtractor AI generation
        mock_payload = StructuredClinicalPayload.model_validate({
            **SYNTHETIC_CLINICAL_PAYLOAD,
            "document_id": doc_id,
        })

        with patch.object(ClinicalExtractor, "extract_clinical_data", return_value=mock_payload):
            struct_res = client.post(f"/api/records/structure/{doc_id}")
            assert struct_res.status_code == 200
            data = struct_res.json()
            assert data["success"] is True
            assert data["entities_saved"]["symptoms"] == 1
            assert data["entities_saved"]["diagnoses"] == 1
            assert data["entities_saved"]["medications"] == 1
            assert data["entities_saved"]["lab_results"] == 1
            assert data["entities_saved"]["recommendations"] == 1
            assert data["patient_id"] is not None

            # Verify all six categories are queryable
            assert len(client.get(f"/api/records/patients?document_id={doc_id}").json()) == 1
            assert len(client.get(f"/api/records/symptoms?document_id={doc_id}").json()) == 1
            assert len(client.get(f"/api/records/diagnoses?document_id={doc_id}").json()) == 1
            assert len(client.get(f"/api/records/medications?document_id={doc_id}").json()) == 1
            assert len(client.get(f"/api/records/labs?document_id={doc_id}").json()) == 1
            assert len(client.get(f"/api/records/recommendations?document_id={doc_id}").json()) == 1

    finally:
        client.delete(f"/api/documents/{doc_id}")
        if pdf_path.exists():
            pdf_path.unlink()


# -----------------------------------------------------------------------------
# Test 2: Scanned Printed Document Extraction
# -----------------------------------------------------------------------------
def test_scanned_printed_document_extraction():
    """Verify that scanned printed document text is eligible and extracted properly."""
    db = SessionLocal()
    try:
        doc = Document(
            id="doc_scanned_printed_synth",
            filename="scanned_lab_panel.pdf",
            stored_path="data/uploads/scanned_lab_panel.pdf",
            document_type="scanned_printed",
            handwriting_detected=False,
            raw_text="--- [PAGE 1] ---\nGLUCOSE 110 mg/dL Normal Fasting",
            character_count=45,
            processing_status="COMPLETED",
        )
        db.add(doc)
        pe = PageExtraction(
            id="pe_scanned_1",
            document_id=doc.id,
            page_number=1,
            page_classification="printed_ocr",
            extraction_method="tesseract_ocr",
            ocr_text="GLUCOSE 110 mg/dL Normal Fasting",
            final_text="GLUCOSE 110 mg/dL Normal Fasting",
            verification_status="verified",
        )
        db.add(pe)
        db.commit()

        is_eligible, text_content, err = ClinicalExtractor.get_eligible_document_text(doc, db)
        assert is_eligible is True
        assert err is None
        assert "GLUCOSE 110" in text_content

    finally:
        db.query(PageExtraction).filter(PageExtraction.document_id == "doc_scanned_printed_synth").delete()
        db.query(Document).filter(Document.id == "doc_scanned_printed_synth").delete()
        db.commit()
        db.close()


# -----------------------------------------------------------------------------
# Test 3: Verified Handwritten Document Extraction Allowed
# -----------------------------------------------------------------------------
def test_verified_handwritten_document_extraction_allowed():
    """Verify that a handwritten document with verification_status='verified' is eligible."""
    db = SessionLocal()
    try:
        doc = Document(
            id="doc_hw_verified_synth",
            filename="rx_doctor_verified.pdf",
            stored_path="data/uploads/rx_doctor_verified.pdf",
            document_type="handwritten",
            handwriting_detected=True,
            raw_text="--- [PAGE 1] ---\nTab Amoxicillin 500mg TID",
            character_count=35,
            processing_status="COMPLETED",
        )
        db.add(doc)
        pe = PageExtraction(
            id="pe_hw_1",
            document_id=doc.id,
            page_number=1,
            page_classification="handwritten",
            extraction_method="gemini_vision",
            gemini_text="Tab Amox[UNCLEAR] 500mg TID",
            human_corrected_text="Tab Amoxicillin 500mg TID (Verified)",
            final_text="Tab Amoxicillin 500mg TID (Verified)",
            verification_status="verified",
        )
        db.add(pe)
        db.commit()

        is_eligible, text_content, err = ClinicalExtractor.get_eligible_document_text(doc, db)
        assert is_eligible is True
        assert err is None
        assert "Tab Amoxicillin 500mg TID (Verified)" in text_content

    finally:
        db.query(PageExtraction).filter(PageExtraction.document_id == "doc_hw_verified_synth").delete()
        db.query(Document).filter(Document.id == "doc_hw_verified_synth").delete()
        db.commit()
        db.close()


# -----------------------------------------------------------------------------
# Test 4: Unverified Handwritten Document Blocked From Confirmed Structuring
# -----------------------------------------------------------------------------
def test_unverified_handwritten_document_blocked():
    """Verify that unverified handwritten pages block clinical structuring with clear 400 error."""
    db = SessionLocal()
    try:
        doc = Document(
            id="doc_hw_unverified_synth",
            filename="rx_doctor_unverified.pdf",
            stored_path="data/uploads/rx_doctor_unverified.pdf",
            document_type="handwritten",
            handwriting_detected=True,
            raw_text="--- [PAGE 1] ---\nTab Amox[UNCLEAR] 500mg TID",
            character_count=35,
            processing_status="COMPLETED",
        )
        db.add(doc)
        pe = PageExtraction(
            id="pe_hw_unver_1",
            document_id=doc.id,
            page_number=1,
            page_classification="handwritten",
            extraction_method="gemini_vision",
            gemini_text="Tab Amox[UNCLEAR] 500mg TID",
            verification_status="pending",  # Unverified!
        )
        db.add(pe)
        db.commit()

        is_eligible, _, reason = ClinicalExtractor.get_eligible_document_text(doc, db)
        assert is_eligible is False
        assert "Clinical safety protocol" in reason
        assert "Human verification is strictly required" in reason

        res = client.post(f"/api/records/structure/{doc.id}")
        assert res.status_code == 400
        assert "Human verification is strictly required" in res.json()["detail"]

    finally:
        db.query(PageExtraction).filter(PageExtraction.document_id == "doc_hw_unverified_synth").delete()
        db.query(Document).filter(Document.id == "doc_hw_unverified_synth").delete()
        db.commit()
        db.close()


# -----------------------------------------------------------------------------
# Test 5: Human-Corrected Text Used Instead of Original OCR Text
# -----------------------------------------------------------------------------
def test_human_corrected_text_selected_over_ocr():
    """Verify that when human correction exists, it is selected instead of raw OCR."""
    db = SessionLocal()
    try:
        doc = Document(
            id="doc_corrected_synth",
            filename="clinical_note_corrected.pdf",
            stored_path="data/uploads/clinical_note_corrected.pdf",
            document_type="mixed",
            handwriting_detected=True,
            raw_text="--- [PAGE 1] ---\nCORRUPTED OCR GARBAGE",
            character_count=30,
            processing_status="COMPLETED",
        )
        db.add(doc)
        pe = PageExtraction(
            id="pe_corr_1",
            document_id=doc.id,
            page_number=1,
            page_classification="handwritten",
            ocr_text="CORRUPTED OCR GARBAGE",
            gemini_text="Med: Met[UNCLEAR] 500mg",
            human_corrected_text="Medication: Metformin 500mg twice daily with meals",
            final_text="Medication: Metformin 500mg twice daily with meals",
            verification_status="verified",
        )
        db.add(pe)
        db.commit()

        is_eligible, text_content, _ = ClinicalExtractor.get_eligible_document_text(doc, db)
        assert is_eligible is True
        assert "CORRUPTED OCR GARBAGE" not in text_content
        assert "Metformin 500mg twice daily with meals" in text_content

    finally:
        db.query(PageExtraction).filter(PageExtraction.document_id == "doc_corrected_synth").delete()
        db.query(Document).filter(Document.id == "doc_corrected_synth").delete()
        db.commit()
        db.close()


# -----------------------------------------------------------------------------
# Test 7, 8, 9: Missing Fields Remain Null - No Invention of Demographics or Dosages
# -----------------------------------------------------------------------------
def test_missing_fields_remain_null_no_fabrication():
    """Verify that unstated clinical fields remain null and are not fabricated."""
    minimal_payload = {
        "document_id": "doc_minimal_test",
        "patient": {
            "name": "Jane Minimal (Synthetic)",
            "age": None,
            "gender": None,
            "patient_identifier": None,
            "demographic_notes": None,
        },
        "symptoms": [
            {
                "symptom_name": "Headache",
                "duration": None,
                "severity": None,
                "description": None,
                "page_number": 1,
            }
        ],
        "diagnoses": [
            {
                "diagnosis_name": "Tension headache",
                "description": None,
                "diagnosis_date": None,
                "status": None,
                "page_number": 1,
            }
        ],
        "medications": [
            {
                "medication_name": "Acetaminophen",
                "dosage": None,
                "frequency": None,
                "duration": None,
                "route": None,
                "page_number": 1,
            }
        ],
        "lab_results": [],
        "recommendations": [],
    }

    model = StructuredClinicalPayload.model_validate(minimal_payload)
    assert model.patient.age is None
    assert model.patient.gender is None
    assert model.symptoms[0].duration is None
    assert model.symptoms[0].severity is None
    assert model.medications[0].dosage is None


# -----------------------------------------------------------------------------
# Test 10: Invalid Gemini JSON Handling Without Crashing
# -----------------------------------------------------------------------------
def test_invalid_gemini_json_handling():
    """Verify that malformed or non-JSON model output is handled with clear error."""
    extractor = ClinicalExtractor()

    with patch(
        "backend.services.clinical_extractor.ClinicalExtractor._provider",
        new_callable=PropertyMock,
        return_value="gemini",
    ):
        with patch.object(settings, "GEMINI_API_KEY", "AIzaSyFakeKeyForTest"):
            with patch("backend.services.clinical_extractor.genai.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_resp = MagicMock()
                mock_resp.text = "This is plain text with no JSON: Patient has fever."
                mock_client.models.generate_content.return_value = mock_resp
                mock_client_cls.return_value = mock_client

                with pytest.raises(RuntimeError) as exc_info:
                    extractor.extract_clinical_data("doc_test", "Patient has fever")
                assert "invalid json" in str(exc_info.value).lower()


# -----------------------------------------------------------------------------
# Test 11: Gemini API Failure Handling
# -----------------------------------------------------------------------------
def test_gemini_api_failure_handling():
    """Verify that network or quota failures from Gemini raise RuntimeError without crash."""
    extractor = ClinicalExtractor()

    with patch(
        "backend.services.clinical_extractor.ClinicalExtractor._provider",
        new_callable=PropertyMock,
        return_value="gemini",
    ):
        with patch.object(settings, "GEMINI_API_KEY", "AIzaSyFakeKeyForTest"):
            with patch("backend.services.clinical_extractor.genai.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.models.generate_content.side_effect = RuntimeError("429 Resource Exhausted / Quota Exceeded")
                mock_client_cls.return_value = mock_client

                with pytest.raises(RuntimeError) as exc_info:
                    extractor.extract_clinical_data("doc_test", "Sample medical text")
                assert "429" in str(exc_info.value) or "Resource Exhausted" in str(exc_info.value)


# -----------------------------------------------------------------------------
# Test 12: Missing Gemini API Key Handling
# -----------------------------------------------------------------------------
def test_missing_gemini_api_key_handling():
    """Verify that an empty API key raises a clear configuration error."""
    with patch(
        "backend.services.clinical_extractor.ClinicalExtractor._provider",
        new_callable=PropertyMock,
        return_value="gemini",
    ):
        with patch(
            "backend.services.clinical_extractor.ClinicalExtractor.api_key",
            new_callable=PropertyMock,
            return_value="",
        ):
            extractor = ClinicalExtractor()
            with pytest.raises(RuntimeError) as exc_info:
                extractor.extract_clinical_data("doc_test", "Sample medical text")
            assert "not configured" in str(exc_info.value).lower()


# -----------------------------------------------------------------------------
# Test 13 & 14: Database Persistence and Retrieval
# -----------------------------------------------------------------------------
def test_database_persistence_and_retrieval_all_entities():
    """Verify persistence of structured clinical entities and correct retrieval."""
    pdf_path = create_synthetic_pdf(["Consultation Notes."], "persist_test.pdf")
    with open(pdf_path, "rb") as f:
        res = client.post("/api/documents/upload", files=[("files", ("persist_test.pdf", f, "application/pdf"))])
    doc_id = res.json()[0]["id"]

    try:
        payload = StructuredClinicalPayload.model_validate({
            **SYNTHETIC_CLINICAL_PAYLOAD,
            "document_id": doc_id,
        })

        db = SessionLocal()
        save_res = persist_structured_clinical_data(db, payload)
        db.close()

        assert save_res["success"] is True
        assert save_res["entities_saved"]["symptoms"] == 1
        assert save_res["entities_saved"]["diagnoses"] == 1
        assert save_res["entities_saved"]["medications"] == 1
        assert save_res["entities_saved"]["lab_results"] == 1
        assert save_res["entities_saved"]["recommendations"] == 1

        syms = client.get(f"/api/records/symptoms?document_id={doc_id}").json()
        assert len(syms) == 1
        assert syms[0]["symptom_name"] == "Productive cough"
        assert syms[0]["page_number"] == 1

        labs = client.get(f"/api/records/labs?document_id={doc_id}").json()
        assert len(labs) == 1
        assert labs[0]["test_name"] == "C-Reactive Protein (CRP)"
        assert labs[0]["numeric_value"] == 48.5

    finally:
        client.delete(f"/api/documents/{doc_id}")
        if pdf_path.exists():
            pdf_path.unlink()


# -----------------------------------------------------------------------------
# Test 15: Duplicate Prevention on Re-Extraction
# -----------------------------------------------------------------------------
def test_duplicate_prevention_on_multiple_extractions():
    """Verify that structuring the same document twice does not create duplicate entity rows."""
    pdf_path = create_synthetic_pdf(["Duplicate prevention test."], "dup_prevent_test.pdf")
    with open(pdf_path, "rb") as f:
        res = client.post("/api/documents/upload", files=[("files", ("dup_prevent_test.pdf", f, "application/pdf"))])
    doc_id = res.json()[0]["id"]

    try:
        payload = StructuredClinicalPayload.model_validate({
            **SYNTHETIC_CLINICAL_PAYLOAD,
            "document_id": doc_id,
        })

        db = SessionLocal()
        res1 = persist_structured_clinical_data(db, payload)
        assert res1["entities_saved"]["symptoms"] == 1

        res2 = persist_structured_clinical_data(db, payload)
        assert res2["entities_saved"]["symptoms"] == 0
        db.close()

        syms = client.get(f"/api/records/symptoms?document_id={doc_id}").json()
        assert len(syms) == 1

    finally:
        client.delete(f"/api/documents/{doc_id}")
        if pdf_path.exists():
            pdf_path.unlink()


# -----------------------------------------------------------------------------
# Test 16: Patient Identity Protection Across Documents
# -----------------------------------------------------------------------------
def test_patient_identity_protection_separate_records():
    """Verify that patients with different document IDs or identifiers remain independent records."""
    db = SessionLocal()
    try:
        # Create parent documents first for foreign key integrity
        d1 = Document(id="doc_A", filename="doc_a.pdf", stored_path="data/uploads/doc_a.pdf")
        d2 = Document(id="doc_B", filename="doc_b.pdf", stored_path="data/uploads/doc_b.pdf")
        db.add_all([d1, d2])
        db.flush()

        p1 = Patient(document_id="doc_A", name="John Smith", patient_identifier="PT-101")
        p2 = Patient(document_id="doc_B", name="John Smith", patient_identifier="PT-102")
        db.add_all([p1, p2])
        db.commit()

        patients = db.query(Patient).filter(Patient.name == "John Smith").all()
        assert len(patients) == 2
        assert patients[0].id != patients[1].id
        assert patients[0].patient_identifier != patients[1].patient_identifier

    finally:
        db.rollback()
        db.query(Patient).filter(Patient.document_id.in_(["doc_A", "doc_B"])).delete()
        db.query(Document).filter(Document.id.in_(["doc_A", "doc_B"])).delete()
        db.commit()
        db.close()


# -----------------------------------------------------------------------------
# Test 17: Document and Page Reference Preservation
# -----------------------------------------------------------------------------
def test_document_and_page_reference_preservation():
    """Verify that extracted findings preserve exact page number and document ID."""
    db = SessionLocal()
    try:
        doc = Document(id="doc_citation_test", filename="doc_cit.pdf", stored_path="data/uploads/doc_cit.pdf")
        db.add(doc)
        db.flush()

        symptom = Symptom(
            document_id="doc_citation_test",
            symptom_name="Dyspnea on exertion",
            severity="Severe",
            page_number=3,
        )
        db.add(symptom)
        db.commit()

        queried = db.query(Symptom).filter(Symptom.document_id == "doc_citation_test").first()
        assert queried.page_number == 3
        assert queried.document_id == "doc_citation_test"

    finally:
        db.rollback()
        db.query(Symptom).filter(Symptom.document_id == "doc_citation_test").delete()
        db.query(Document).filter(Document.id == "doc_citation_test").delete()
        db.commit()
        db.close()


# -----------------------------------------------------------------------------
# Test 18: Multi-Page Document Source Text Assembly
# -----------------------------------------------------------------------------
def test_multipage_document_source_text_assembly():
    """Verify that multi-page documents assemble text blocks preserving page markers."""
    db = SessionLocal()
    try:
        doc = Document(
            id="doc_multipage_assembly",
            filename="multipage_report.pdf",
            stored_path="data/uploads/multipage_report.pdf",
            document_type="mixed",
            character_count=100,
            processing_status="COMPLETED",
        )
        db.add(doc)

        pe1 = PageExtraction(
            id="pe_multi_1",
            document_id=doc.id,
            page_number=1,
            page_classification="digital",
            final_text="Page 1: Consultation notes and symptoms.",
            verification_status="verified",
        )
        pe2 = PageExtraction(
            id="pe_multi_2",
            document_id=doc.id,
            page_number=2,
            page_classification="printed_ocr",
            final_text="Page 2: Laboratory panel findings.",
            verification_status="verified",
        )
        db.add_all([pe1, pe2])
        db.commit()

        is_eligible, text_content, _ = ClinicalExtractor.get_eligible_document_text(doc, db)
        assert is_eligible is True
        assert "--- [PAGE 1] ---" in text_content
        assert "Page 1: Consultation notes" in text_content
        assert "--- [PAGE 2] ---" in text_content
        assert "Page 2: Laboratory panel" in text_content

    finally:
        db.query(PageExtraction).filter(PageExtraction.document_id == "doc_multipage_assembly").delete()
        db.query(Document).filter(Document.id == "doc_multipage_assembly").delete()
        db.commit()
        db.close()


# -----------------------------------------------------------------------------
# Test 19: Transaction Rollback on Error
# -----------------------------------------------------------------------------
def test_transaction_rollback_on_persistence_error():
    """Verify that if an insertion fails during transactional structuring, changes are rolled back."""
    pdf_path = create_synthetic_pdf(["Rollback test."], "rollback_test.pdf")
    with open(pdf_path, "rb") as f:
        res = client.post("/api/documents/upload", files=[("files", ("rollback_test.pdf", f, "application/pdf"))])
    doc_id = res.json()[0]["id"]

    try:
        db = SessionLocal()
        payload = StructuredClinicalPayload(
            document_id=doc_id,
            patient=None,
            symptoms=[SymptomBase(symptom_name="Valid Symptom", page_number=1)],
            diagnoses=[],
            medications=[],
            lab_results=[],
            recommendations=[],
        )

        with patch.object(db, "commit", side_effect=RuntimeError("Simulated Disk Full")):
            with pytest.raises(RuntimeError):
                persist_structured_clinical_data(db, payload)

        db.rollback()
        db.close()

        syms = client.get(f"/api/records/symptoms?document_id={doc_id}").json()
        assert len(syms) == 0

    finally:
        client.delete(f"/api/documents/{doc_id}")
        if pdf_path.exists():
            pdf_path.unlink()


# -----------------------------------------------------------------------------
# Test 20: Existing Database Data Preservation
# -----------------------------------------------------------------------------
def test_existing_database_records_remain_intact_after_structuring():
    """Verify that persisting entities for a new document does not delete or alter old records."""
    db = SessionLocal()
    try:
        anchor_doc = Document(
            id="doc_existing_anchor",
            filename="anchor.pdf",
            stored_path="data/uploads/anchor.pdf",
        )
        db.add(anchor_doc)
        db.flush()

        old_diag = Diagnosis(
            document_id="doc_existing_anchor",
            diagnosis_name="Hypertension Stage 2",
            status="Confirmed",
            page_number=1,
        )
        db.add(old_diag)
        db.commit()

        pdf_path = create_synthetic_pdf(["New document."], "new_doc.pdf")
        with open(pdf_path, "rb") as f:
            res = client.post("/api/documents/upload", files=[("files", ("new_doc.pdf", f, "application/pdf"))])
        new_doc_id = res.json()[0]["id"]

        new_payload = StructuredClinicalPayload(
            document_id=new_doc_id,
            patient=None,
            symptoms=[],
            diagnoses=[DiagnosisBase(diagnosis_name="Type 2 Diabetes Mellitus", page_number=1)],
            medications=[],
            lab_results=[],
            recommendations=[],
        )
        persist_structured_clinical_data(db, new_payload)

        assert db.query(Diagnosis).filter(Diagnosis.document_id == "doc_existing_anchor").first() is not None
        assert db.query(Diagnosis).filter(Diagnosis.document_id == new_doc_id).first() is not None

        client.delete(f"/api/documents/{new_doc_id}")
        if pdf_path.exists():
            pdf_path.unlink()

    finally:
        db.rollback()
        db.query(Diagnosis).filter(Diagnosis.document_id == "doc_existing_anchor").delete()
        db.query(Document).filter(Document.id == "doc_existing_anchor").delete()
        db.commit()
        db.close()


# -----------------------------------------------------------------------------
# Test 21: Document Deletion Regression - Cascades to All Structured Entities
# -----------------------------------------------------------------------------
def test_document_deletion_cascades_to_all_six_categories():
    """Verify that deleting a document cascades to delete its patient and all 5 entity types."""
    pdf_path = create_synthetic_pdf(["Cascade test."], "cascade_test.pdf")
    with open(pdf_path, "rb") as f:
        res = client.post("/api/documents/upload", files=[("files", ("cascade_test.pdf", f, "application/pdf"))])
    doc_id = res.json()[0]["id"]

    try:
        payload = StructuredClinicalPayload.model_validate({
            **SYNTHETIC_CLINICAL_PAYLOAD,
            "document_id": doc_id,
        })
        db = SessionLocal()
        persist_structured_clinical_data(db, payload)
        db.close()

        del_res = client.delete(f"/api/documents/{doc_id}")
        assert del_res.status_code == 200

        assert len(client.get(f"/api/records/patients?document_id={doc_id}").json()) == 0
        assert len(client.get(f"/api/records/symptoms?document_id={doc_id}").json()) == 0
        assert len(client.get(f"/api/records/diagnoses?document_id={doc_id}").json()) == 0
        assert len(client.get(f"/api/records/medications?document_id={doc_id}").json()) == 0
        assert len(client.get(f"/api/records/labs?document_id={doc_id}").json()) == 0
        assert len(client.get(f"/api/records/recommendations?document_id={doc_id}").json()) == 0

    finally:
        if pdf_path.exists():
            pdf_path.unlink()


# -----------------------------------------------------------------------------
# Test 22: Search and Filter API Integration Across All Categories
# -----------------------------------------------------------------------------
def test_search_and_filter_api_across_categories():
    """Verify search and filter parameters work across all clinical record API endpoints."""
    db = SessionLocal()
    doc_id = "doc_search_test"
    try:
        doc = Document(id=doc_id, filename="search_doc.pdf", stored_path="data/uploads/search_doc.pdf")
        db.add(doc)
        db.flush()

        p = Patient(document_id=doc_id, name="Eleanor Rigby", patient_identifier="RIG-990")
        s = Symptom(document_id=doc_id, symptom_name="Tachycardia", severity="Severe", page_number=1)
        d = Diagnosis(document_id=doc_id, diagnosis_name="Supraventricular Tachycardia", page_number=1)
        m = Medication(document_id=doc_id, medication_name="Metoprolol Succinate", dosage="25 mg", page_number=1)
        l = LabResult(document_id=doc_id, test_name="Serum Potassium", result_value="3.2 mmol/L", flag="Low", page_number=1)
        r = Recommendation(document_id=doc_id, recommendation_text="Cardiology consultation requested", page_number=1)
        db.add_all([p, s, d, m, l, r])
        db.commit()

        # Test search query filters
        p_res = client.get("/api/records/patients?search=Rigby").json()
        assert len(p_res) >= 1
        assert p_res[0]["name"] == "Eleanor Rigby"

        s_res = client.get("/api/records/symptoms?search=Tachycardia&severity=Severe").json()
        assert len(s_res) >= 1
        assert s_res[0]["symptom_name"] == "Tachycardia"

        d_res = client.get("/api/records/diagnoses?search=Supraventricular").json()
        assert len(d_res) >= 1

        m_res = client.get("/api/records/medications?search=Metoprolol").json()
        assert len(m_res) >= 1

        l_res = client.get("/api/records/labs?search=Potassium&flag=Low").json()
        assert len(l_res) >= 1

        r_res = client.get("/api/records/recommendations?search=Cardiology").json()
        assert len(r_res) >= 1

    finally:
        db.rollback()
        db.query(Patient).filter(Patient.document_id == doc_id).delete()
        db.query(Symptom).filter(Symptom.document_id == doc_id).delete()
        db.query(Diagnosis).filter(Diagnosis.document_id == doc_id).delete()
        db.query(Medication).filter(Medication.document_id == doc_id).delete()
        db.query(LabResult).filter(LabResult.document_id == doc_id).delete()
        db.query(Recommendation).filter(Recommendation.document_id == doc_id).delete()
        db.query(Document).filter(Document.id == doc_id).delete()
        db.commit()
        db.close()
