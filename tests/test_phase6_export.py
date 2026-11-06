import io
import json
import zipfile
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import openpyxl

from backend.database import Base, get_db
from backend.main import app
from backend.models.clinical_records import (
    Diagnosis,
    LabResult,
    Medication,
    Recommendation,
    Symptom,
)
from backend.models.document import Document
from backend.models.patient import Patient
from backend.services.export_service import ExportService


# Use an in-memory SQLite database for isolated test execution
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def test_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        # Seed test documents
        doc1 = Document(
            id="doc-alpha-123",
            filename="John_Doe_Discharge_Summary.pdf",
            stored_path="/mock/path/doc1.pdf",
            file_size_bytes=10240,
            page_count=2,
            document_type="digital",
            extraction_method="pdfplumber",
            character_count=1500,
            processing_status="COMPLETED",
        )
        doc2 = Document(
            id="doc-beta-456",
            filename="Jane_Smith_Lab_Report.pdf",
            stored_path="/mock/path/doc2.pdf",
            file_size_bytes=20480,
            page_count=1,
            document_type="scanned_printed",
            extraction_method="tesseract",
            character_count=850,
            processing_status="COMPLETED",
        )
        db.add_all([doc1, doc2])
        db.commit()

        # Seed test patients
        pat1 = Patient(
            id=1,
            patient_identifier="MRN-1001",
            name="Johnathan Doe",
            age=58,
            gender="Male",
            demographic_notes="Patient lives alone in Boston. Contact daughter Mary.",
            document_id="doc-alpha-123",
        )
        pat2 = Patient(
            id=2,
            patient_identifier="MRN-2002",
            name="Jane Smith",
            age=42,
            gender="Female",
            demographic_notes="Emergency contact husband Robert. Prefers morning appointments.",
            document_id="doc-beta-456",
        )
        db.add_all([pat1, pat2])
        db.commit()

        # Seed symptoms
        s1 = Symptom(
            id=1,
            document_id="doc-alpha-123",
            patient_id=1,
            symptom_name="Chest pain",
            description="Substernal tightness on exertion",
            duration="3 days",
            severity="Moderate",
            page_number=1,
        )
        s2 = Symptom(
            id=2,
            document_id="doc-beta-456",
            patient_id=2,
            symptom_name="Fatigue",
            description="Persistent generalized weakness",
            duration="2 weeks",
            severity="Mild",
            page_number=1,
        )
        db.add_all([s1, s2])

        # Seed diagnoses
        d1 = Diagnosis(
            id=1,
            document_id="doc-alpha-123",
            patient_id=1,
            diagnosis_name="Coronary Artery Disease",
            description="Atherosclerotic cardiovascular disease",
            diagnosis_date="2025-11-01",
            status="Confirmed",
            page_number=1,
        )
        d2 = Diagnosis(
            id=2,
            document_id="doc-beta-456",
            patient_id=2,
            diagnosis_name="Iron Deficiency Anemia",
            description="Microcytic hypochromic anemia",
            diagnosis_date="2025-11-03",
            status="Provisional",
            page_number=1,
        )
        db.add_all([d1, d2])

        # Seed medications
        m1 = Medication(
            id=1,
            document_id="doc-alpha-123",
            patient_id=1,
            medication_name="Aspirin",
            dosage="81mg",
            frequency="Once daily",
            duration="Indefinite",
            route="Oral",
            page_number=2,
        )
        m2 = Medication(
            id=2,
            document_id="doc-beta-456",
            patient_id=2,
            medication_name="Ferrous Sulfate",
            dosage="325mg",
            frequency="Twice daily",
            duration="30 days",
            route="Oral",
            page_number=1,
        )
        db.add_all([m1, m2])

        # Seed laboratory results
        l1 = LabResult(
            id=1,
            document_id="doc-alpha-123",
            patient_id=1,
            test_name="Troponin I",
            result_value="0.02",
            numeric_value=0.02,
            unit="ng/mL",
            reference_range="< 0.04",
            flag="Normal",
            test_date="2025-11-01",
            page_number=2,
        )
        l2 = LabResult(
            id=2,
            document_id="doc-beta-456",
            patient_id=2,
            test_name="Hemoglobin",
            result_value="9.8",
            numeric_value=9.8,
            unit="g/dL",
            reference_range="12.0 - 15.5",
            flag="Low",
            test_date="2025-11-03",
            page_number=1,
        )
        db.add_all([l1, l2])

        # Seed recommendations
        r1 = Recommendation(
            id=1,
            document_id="doc-alpha-123",
            patient_id=1,
            recommendation_text="Follow up with Cardiology in 2 weeks.",
            follow_up_instructions="Schedule stress echocardiogram if chest tightness recurs.",
            page_number=2,
        )
        r2 = Recommendation(
            id=2,
            document_id="doc-beta-456",
            patient_id=2,
            recommendation_text="Repeat CBC in 4 weeks.",
            follow_up_instructions="Maintain dietary iron intake and take supplement with vitamin C.",
            page_number=1,
        )
        db.add_all([r1, r2])
        db.commit()

        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db):
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ==============================================================================
# Unit Tests: ExportService & Pseudonymization
# ==============================================================================

def test_pseudonymization_stability_and_entropy():
    svc = ExportService(salt="test-secret-salt-key")
    # Stable mapping for same ID
    p1 = svc.pseudonymize_patient_id(1)
    p2 = svc.pseudonymize_patient_id(1)
    assert p1 == p2
    assert p1.startswith("SUBJ-")
    assert len(p1) == 17  # "SUBJ-" (5) + 12 hex chars = 17

    # Distinct mapping for different ID
    p_diff = svc.pseudonymize_patient_id(2)
    assert p1 != p_diff

    # Document pseudonym
    d1 = svc.pseudonymize_document_id("doc-alpha-123")
    assert d1.startswith("DOC-")
    assert len(d1) == 16  # "DOC-" (4) + 12 hex chars = 16

    # None handling
    assert svc.pseudonymize_patient_id(None) == ""
    assert svc.pseudonymize_document_id(None) == ""


def test_pseudonymized_filename():
    svc = ExportService(salt="test-salt")
    pname = svc.pseudonymize_filename("doc-alpha-123")
    assert pname.startswith("DOCUMENT_")
    assert pname.endswith(".pdf")
    assert "John_Doe" not in pname


def test_export_data_de_identification_masking(test_db):
    svc = ExportService()
    # In de-identified mode
    data_deid = svc.get_export_data(test_db, de_identify=True)

    patients = data_deid["patients"]
    assert len(patients) == 2
    for p in patients:
        assert p["name"] == "[REDACTED_RESEARCH_SUBJECT]"
        assert p["demographic_notes"] == "[REDACTED_DEMOGRAPHIC_NOTES]"
        assert p["patient_identifier"].startswith("SUBJ-")
        assert p["patient_id"].startswith("SUBJ-")
        assert p["document_id"].startswith("DOC-")
        # Demographic covariates are retained
        assert p["age"] in (58, 42)
        assert p["gender"] in ("Male", "Female")

    # In identified mode (explicit opt-out)
    data_ident = svc.get_export_data(test_db, de_identify=False)
    patients_ident = data_ident["patients"]
    assert patients_ident[0]["name"] == "Johnathan Doe"
    assert patients_ident[0]["patient_identifier"] == "MRN-1001"
    assert "Boston" in patients_ident[0]["demographic_notes"]
    assert patients_ident[0]["document_id"] == "doc-alpha-123"


def test_preservation_of_traceability_and_lab_values(test_db):
    svc = ExportService()
    data = svc.get_export_data(test_db, de_identify=True)

    # Symptoms retain page number and severity
    symptoms = data["symptoms"]
    assert len(symptoms) == 2
    assert symptoms[0]["symptom_name"] == "Chest pain"
    assert symptoms[0]["page_number"] == 1
    assert symptoms[0]["severity"] == "Moderate"

    # Labs retain exact test name, result value, numeric value, unit, reference range, flag, page number
    labs = data["labs"]
    assert len(labs) == 2
    troponin = next(l for l in labs if l["test_name"] == "Troponin I")
    assert troponin["result_value"] == "0.02"
    assert troponin["numeric_value"] == 0.02
    assert troponin["unit"] == "ng/mL"
    assert troponin["reference_range"] == "< 0.04"
    assert troponin["flag"] == "Normal"
    assert troponin["page_number"] == 2

    hemoglobin = next(l for l in labs if l["test_name"] == "Hemoglobin")
    assert hemoglobin["result_value"] == "9.8"
    assert hemoglobin["numeric_value"] == 9.8
    assert hemoglobin["unit"] == "g/dL"
    assert hemoglobin["flag"] == "Low"
    assert hemoglobin["page_number"] == 1


# ==============================================================================
# Integration Tests: REST API Endpoints
# ==============================================================================

def test_api_export_summary(client):
    res = client.get("/api/export/summary")
    assert res.status_code == 200
    body = res.json()
    assert body["total_documents"] == 2
    assert body["total_records"] == 12  # 2 pat + 2 sym + 2 diag + 2 med + 2 lab + 2 rec = 12 total
    assert body["categories"]["patients"] == 2
    assert body["categories"]["symptoms"] == 2
    assert body["categories"]["diagnoses"] == 2
    assert body["categories"]["medications"] == 2
    assert body["categories"]["labs"] == 2
    assert body["categories"]["recommendations"] == 2
    assert body["de_identification_default"] is True


def test_api_export_summary_with_document_filter(client):
    res = client.get("/api/export/summary?document_id=doc-alpha-123")
    assert res.status_code == 200
    body = res.json()
    assert body["document_filter"] == "doc-alpha-123"
    assert body["total_documents"] == 1
    assert body["categories"]["patients"] == 1
    assert body["categories"]["symptoms"] == 1
    assert body["categories"]["diagnoses"] == 1
    assert body["categories"]["medications"] == 1
    assert body["categories"]["labs"] == 1
    assert body["categories"]["recommendations"] == 1


def test_api_export_excel_workbook(client):
    res = client.get("/api/export/excel?de_identify=true")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "attachment; filename=\"medistruct_clinical_dataset_" in res.headers["content-disposition"]
    assert "_deidentified.xlsx" in res.headers["content-disposition"]

    # Verify openpyxl can load the stream and inspect sheets
    excel_bytes = io.BytesIO(res.content)
    wb = openpyxl.load_workbook(excel_bytes)
    sheet_names = wb.sheetnames
    assert "Cohort_Manifest" in sheet_names
    assert "Patients" in sheet_names
    assert "Symptoms" in sheet_names
    assert "Diagnoses" in sheet_names
    assert "Medications" in sheet_names
    assert "Laboratory_Results" in sheet_names
    assert "Recommendations" in sheet_names
    assert "Document_Metadata" in sheet_names

    # Check manifest content
    ws_manifest = wb["Cohort_Manifest"]
    assert ws_manifest.cell(row=1, column=1).value == "MediStruct AI — Research Cohort Export Manifest"

    # Check patient de-identification in Excel sheet
    ws_patients = wb["Patients"]
    # Row 1 is header, Row 2 is first patient
    # Find column indices
    headers = [ws_patients.cell(row=1, column=c).value for c in range(1, ws_patients.max_column + 1)]
    assert "name" in headers
    name_col = headers.index("name") + 1
    val_name = ws_patients.cell(row=2, column=name_col).value
    assert val_name == "[REDACTED_RESEARCH_SUBJECT]"
    assert "Johnathan" not in str(val_name)


def test_api_export_single_category_csv(client):
    res = client.get("/api/export/csv/medications?de_identify=true")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "medistruct_medications_" in res.headers["content-disposition"]

    csv_content = res.content.decode("utf-8-sig")
    assert "record_id,patient_id,document_id,medication_name,dosage,frequency,duration,route,page_number,created_at" in csv_content
    assert "Aspirin" in csv_content
    assert "Ferrous Sulfate" in csv_content
    # Confirm document and patient IDs are pseudonymized
    assert "DOC-" in csv_content
    assert "SUBJ-" in csv_content
    assert "doc-alpha-123" not in csv_content


def test_api_export_single_category_csv_invalid_category(client):
    res = client.get("/api/export/csv/non_existent_category")
    assert res.status_code == 400
    assert "Invalid category" in res.json()["detail"]


def test_api_export_bundle_zip(client):
    res = client.get("/api/export/bundle?de_identify=true")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"
    assert "medistruct_dataset_bundle_" in res.headers["content-disposition"]

    zip_bytes = io.BytesIO(res.content)
    with zipfile.ZipFile(zip_bytes, mode="r") as zf:
        namelist = zf.namelist()
        assert "manifest.csv" in namelist
        assert "README.txt" in namelist
        assert "patients.csv" in namelist
        assert "symptoms.csv" in namelist
        assert "diagnoses.csv" in namelist
        assert "medications.csv" in namelist
        assert "labs.csv" in namelist
        assert "recommendations.csv" in namelist
        assert "documents_metadata.csv" in namelist

        # Inspect README.txt
        readme = zf.read("README.txt").decode("utf-8")
        assert "MEDISTRUCT AI — RESEARCH CLINICAL DATASET EXPORT" in readme
        assert "TRACEABILITY NOTE" in readme

        # Inspect patients.csv
        patients_csv = zf.read("patients.csv").decode("utf-8-sig")
        assert "[REDACTED_RESEARCH_SUBJECT]" in patients_csv
        assert "Johnathan Doe" not in patients_csv


def test_api_export_json_dataset(client):
    res = client.get("/api/export/json?de_identify=true")
    assert res.status_code == 200
    assert "application/json" in res.headers["content-type"]
    body = res.json()
    assert "metadata" in body
    assert "records" in body
    assert body["metadata"]["de_identified"] is True
    assert body["metadata"]["pseudonymization"] == "HMAC-SHA256"
    assert len(body["records"]["symptoms"]) == 2
    assert len(body["records"]["diagnoses"]) == 2


def test_export_with_document_filtering(client):
    res = client.get("/api/export/excel?document_id=doc-alpha-123&de_identify=true")
    assert res.status_code == 200

    excel_bytes = io.BytesIO(res.content)
    wb = openpyxl.load_workbook(excel_bytes)
    ws_symptoms = wb["Symptoms"]
    # Only 1 symptom belonging to doc-alpha-123 should be present
    assert ws_symptoms.max_row == 2  # 1 header + 1 row


def test_empty_database_export_safety():
    # Empty in-memory DB
    empty_engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(bind=empty_engine)
    EmptySession = sessionmaker(bind=empty_engine)
    empty_db = EmptySession()

    try:
        svc = ExportService()
        summary = svc.get_export_summary(empty_db)
        assert summary["total_records"] == 0
        assert summary["total_documents"] == 0

        # Excel export on empty DB should still produce valid workbook
        empty_data = svc.get_export_data(empty_db, de_identify=True)
        buf = svc.export_to_excel(empty_data, de_identify=True)
        wb = openpyxl.load_workbook(buf)
        assert "Cohort_Manifest" in wb.sheetnames

        # ZIP export on empty DB
        zip_buf = svc.export_to_zip(empty_data, de_identify=True)
        with zipfile.ZipFile(zip_buf, "r") as zf:
            assert "manifest.csv" in zf.namelist()
            assert "README.txt" in zf.namelist()
    finally:
        empty_db.close()
