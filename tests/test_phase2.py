import os
import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

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

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    """Ensure database tables are initialized before tests run."""
    init_db()
    yield


def test_database_connectivity_and_tables():
    """Verify SQLite connection and that all required tables exist."""
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    required_tables = [
        "documents",
        "patients",
        "symptoms",
        "diagnoses",
        "medications",
        "lab_results",
        "recommendations",
    ]
    for table in required_tables:
        assert table in table_names, f"Expected table '{table}' missing from database."


def test_document_model_handwriting_architecture_fields():
    """Verify Document model supports classification of digital, scanned, and handwritten documents."""
    inspector = inspect(engine)
    columns = {col["name"]: col for col in inspector.get_columns("documents")}

    assert "document_type" in columns
    assert "handwriting_detected" in columns
    assert "extraction_method" in columns
    assert "raw_text" in columns
    assert "character_count" in columns
    assert "processing_status" in columns


def test_upload_single_and_multiple_pdf_documents():
    """Test multi-PDF document upload endpoint with unique ID generation and storage."""
    # Synthetic PDF 1
    pdf_content_1 = b"%PDF-1.4 synthetic medical record 1 text"
    # Synthetic PDF 2
    pdf_content_2 = b"%PDF-1.4 synthetic medical record 2 text"

    files = [
        ("files", ("test_clinical_report_1.pdf", io.BytesIO(pdf_content_1), "application/pdf")),
        ("files", ("test_clinical_report_2.pdf", io.BytesIO(pdf_content_2), "application/pdf")),
    ]

    response = client.post("/api/documents/upload", files=files)
    assert response.status_code == 201
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"].startswith("doc_")
    assert data[1]["id"].startswith("doc_")
    assert data[0]["filename"] == "test_clinical_report_1.pdf"
    assert data[1]["filename"] == "test_clinical_report_2.pdf"
    assert data[0]["processing_status"] == "PENDING"

    # Cleanup created documents
    for doc in data:
        client.delete(f"/api/documents/{doc['id']}")


def test_invalid_file_format_rejection():
    """Verify that non-PDF files are rejected with a clear 400 Bad Request error."""
    files = [
        ("files", ("not_a_medical_doc.txt", io.BytesIO(b"Hello world"), "text/plain")),
    ]
    response = client.post("/api/documents/upload", files=files)
    assert response.status_code == 400
    assert "MediStruct AI requires PDF documents" in response.json()["detail"]


def test_list_and_search_documents():
    """Test listing documents with status and search filters."""
    # Upload a document with a distinct name
    pdf_bytes = b"%PDF-1.4 synthetic lab report"
    files = [("files", ("cardiology_ecg_report.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    upload_res = client.post("/api/documents/upload", files=files)
    assert upload_res.status_code == 201
    doc_id = upload_res.json()[0]["id"]

    try:
        # Search by filename
        list_res = client.get("/api/documents?search=cardiology")
        assert list_res.status_code == 200
        docs = list_res.json()
        assert any(d["id"] == doc_id for d in docs)

        # Filter by status
        pending_res = client.get("/api/documents?status=PENDING")
        assert pending_res.status_code == 200
        assert any(d["id"] == doc_id for d in pending_res.json())

    finally:
        client.delete(f"/api/documents/{doc_id}")


def test_transactional_clinical_records_persistence_and_retrieval():
    """Test full transactional insertion of structured clinical entities with page citations."""
    # 1. Upload a document
    pdf_bytes = b"%PDF-1.4 synthetic oncology consult"
    files = [("files", ("oncology_consultation.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    upload_res = client.post("/api/documents/upload", files=files)
    doc_id = upload_res.json()[0]["id"]

    try:
        # 2. Persist structured clinical payload
        payload = {
            "document_id": doc_id,
            "patient": {
                "patient_identifier": "ONC-9402",
                "name": "Jane Doe (Synthetic)",
                "age": 58,
                "gender": "Female",
                "demographic_notes": "Non-smoker, allergic to penicillin",
            },
            "symptoms": [
                {
                    "symptom_name": "Persistent dry cough",
                    "description": "Worse at night, non-productive",
                    "duration": "3 weeks",
                    "severity": "Moderate",
                    "page_number": 1,
                },
                {
                    "symptom_name": "Fatigue",
                    "description": "Generalized lethargy",
                    "duration": "1 month",
                    "severity": "Mild",
                    "page_number": 1,
                },
            ],
            "diagnoses": [
                {
                    "diagnosis_name": "Bronchial inflammation",
                    "description": "Secondary to viral syndrome",
                    "diagnosis_date": "2026-10-15",
                    "status": "Provisional",
                    "page_number": 2,
                }
            ],
            "medications": [
                {
                    "medication_name": "Albuterol sulfate inhaler",
                    "dosage": "90 mcg",
                    "frequency": "Every 4-6 hours PRN",
                    "duration": "14 days",
                    "route": "Inhalation",
                    "page_number": 2,
                }
            ],
            "lab_results": [
                {
                    "test_name": "Hemoglobin",
                    "result_value": "13.8 g/dL",
                    "numeric_value": 13.8,
                    "unit": "g/dL",
                    "reference_range": "12.0 - 15.5",
                    "flag": "Normal",
                    "test_date": "2026-10-14",
                    "page_number": 3,
                }
            ],
            "recommendations": [
                {
                    "recommendation_text": "Follow up in clinic in 2 weeks if cough persists.",
                    "follow_up_instructions": "Return sooner if shortness of breath develops.",
                    "page_number": 3,
                }
            ],
        }

        save_res = client.post("/api/records/structured", json=payload)
        assert save_res.status_code == 201
        res_data = save_res.json()
        assert res_data["success"] is True
        assert res_data["entities_saved"]["symptoms"] == 2
        assert res_data["entities_saved"]["diagnoses"] == 1
        assert res_data["entities_saved"]["medications"] == 1
        assert res_data["entities_saved"]["lab_results"] == 1
        assert res_data["entities_saved"]["recommendations"] == 1

        # 3. Verify retrieval endpoints
        symptoms_res = client.get(f"/api/records/symptoms?document_id={doc_id}")
        assert symptoms_res.status_code == 200
        assert len(symptoms_res.json()) == 2
        assert symptoms_res.json()[0]["page_number"] == 1

        diagnoses_res = client.get(f"/api/records/diagnoses?document_id={doc_id}")
        assert len(diagnoses_res.json()) == 1
        assert diagnoses_res.json()[0]["diagnosis_name"] == "Bronchial inflammation"
        assert diagnoses_res.json()[0]["page_number"] == 2

        meds_res = client.get(f"/api/records/medications?document_id={doc_id}")
        assert len(meds_res.json()) == 1
        assert meds_res.json()[0]["medication_name"] == "Albuterol sulfate inhaler"

        labs_res = client.get(f"/api/records/labs?document_id={doc_id}")
        assert len(labs_res.json()) == 1
        assert labs_res.json()[0]["numeric_value"] == 13.8

        recs_res = client.get(f"/api/records/recommendations?document_id={doc_id}")
        assert len(recs_res.json()) == 1

        # 4. Verify Document detail includes counts
        detail_res = client.get(f"/api/documents/{doc_id}")
        assert detail_res.status_code == 200
        detail = detail_res.json()
        assert detail["processing_status"] == "COMPLETED"
        assert detail["record_counts"]["symptoms"] == 2
        assert detail["record_counts"]["diagnoses"] == 1
        assert detail["record_counts"]["medications"] == 1
        assert detail["record_counts"]["lab_results"] == 1
        assert detail["record_counts"]["recommendations"] == 1
        assert detail["patient"]["name"] == "Jane Doe (Synthetic)"

        # 5. Verify dynamic overview metrics
        metrics_res = client.get("/api/analytics/overview")
        assert metrics_res.status_code == 200
        metrics = metrics_res.json()
        assert metrics["total_documents"] >= 1
        assert metrics["total_symptoms"] >= 2
        assert metrics["total_diagnoses"] >= 1
        assert metrics["total_medications"] >= 1
        assert metrics["total_lab_tests"] >= 1

    finally:
        # 6. Test Cascade Deletion: deleting document should delete child records
        del_res = client.delete(f"/api/documents/{doc_id}")
        assert del_res.status_code == 200

        # Verify child symptoms were cascade-deleted
        clean_symptoms = client.get(f"/api/records/symptoms?document_id={doc_id}").json()
        assert len(clean_symptoms) == 0


def test_duplicate_prevention_on_structured_persistence():
    """Verify that posting identical clinical findings for the same doc and page does not create duplicates."""
    pdf_bytes = b"%PDF-1.4 synthetic duplicate test"
    files = [("files", ("duplicate_test.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    upload_res = client.post("/api/documents/upload", files=files)
    doc_id = upload_res.json()[0]["id"]

    try:
        payload = {
            "document_id": doc_id,
            "symptoms": [
                {"symptom_name": "Chest tightness", "page_number": 1},
            ],
            "diagnoses": [
                {"diagnosis_name": "Asthma exacerbation", "page_number": 1},
            ],
            "medications": [],
            "lab_results": [],
            "recommendations": [],
        }

        # First post
        res1 = client.post("/api/records/structured", json=payload)
        assert res1.status_code == 201
        assert res1.json()["entities_saved"]["symptoms"] == 1

        # Second identical post
        res2 = client.post("/api/records/structured", json=payload)
        assert res2.status_code == 201
        # Should be 0 newly added because it already existed
        assert res2.json()["entities_saved"]["symptoms"] == 0

        # Query symptoms directly to confirm exactly 1 symptom exists
        symptoms = client.get(f"/api/records/symptoms?document_id={doc_id}").json()
        assert len(symptoms) == 1

    finally:
        client.delete(f"/api/documents/{doc_id}")


def test_safe_database_reinitialization_preserves_data():
    """Verify that calling init_db() does not drop tables or delete existing data."""
    pdf_bytes = b"%PDF-1.4 synthetic persistent report"
    files = [("files", ("persistent_patient_record.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    upload_res = client.post("/api/documents/upload", files=files)
    doc_id = upload_res.json()[0]["id"]

    try:
        # Re-run init_db multiple times
        init_db()
        init_db()

        # Document must still exist
        doc_res = client.get(f"/api/documents/{doc_id}")
        assert doc_res.status_code == 200
        assert doc_res.json()["filename"] == "persistent_patient_record.pdf"

    finally:
        client.delete(f"/api/documents/{doc_id}")
