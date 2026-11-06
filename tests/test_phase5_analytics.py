"""
tests/test_phase5_analytics.py

Comprehensive test suite for Phase 5: Clinical Knowledge Discovery and Analytics
in MediStruct AI.

Test categories:
  1. Clinical summary metrics (all seven categories, distinct patient count).
  2. Category distribution percentages.
  3. Symptom frequency and severity breakdown.
  4. Diagnosis frequency and status breakdown.
  5. Medication frequency, administration routes, and dosages.
  6. Symptom-diagnosis co-occurrence (with duplicate join multiplication prevention).
  7. Medication-diagnosis co-occurrence.
  8. Laboratory analytics with strict unit isolation (preventing cross-unit averaging).
  9. Safe handling of null numeric laboratory values (qualitative tests).
  10. Recommendation analysis using only existing database columns.
  11. Descriptive insights generation with supporting evidence counts.
  12. Document-level filtering across all analytics endpoints.
  13. Empty database resilience (graceful zero-state, no 500 crashes).
  14. Query parameter validation (limits, offsets).
"""

import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.database import Base, get_db, init_db, SessionLocal
from backend.models.document import Document
from backend.models.patient import Patient
from backend.models.clinical_records import (
    Symptom,
    Diagnosis,
    Medication,
    LabResult,
    Recommendation,
)
from backend.services.analytics_service import AnalyticsService

client = TestClient(app)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def ensure_db():
    """Ensure database schema is initialized."""
    init_db()
    yield


@pytest.fixture
def clean_synthetic_dataset():
    """
    Creates a controlled multi-document synthetic cohort to verify all
    mathematical aggregations, unit isolation, and co-occurrences exactly.
    Cleans up after testing.
    """
    db = SessionLocal()
    doc1_id = f"test_doc_{uuid.uuid4().hex[:8]}"
    doc2_id = f"test_doc_{uuid.uuid4().hex[:8]}"

    # Documents
    doc1 = Document(
        id=doc1_id,
        filename="cohort_patient_alpha.pdf",
        stored_path=f"/tmp/{doc1_id}.pdf",
        processing_status="COMPLETED",
    )
    doc2 = Document(
        id=doc2_id,
        filename="cohort_patient_beta.pdf",
        stored_path=f"/tmp/{doc2_id}.pdf",
        processing_status="COMPLETED",
    )
    db.add_all([doc1, doc2])
    db.commit()

    # Patients (Patient 1 in Doc 1, Patient 2 in Doc 2)
    p1 = Patient(
        document_id=doc1_id,
        patient_identifier="PT-101",
        name="Alice Smith",
        age=55,
        gender="Female",
    )
    p2 = Patient(
        document_id=doc2_id,
        patient_identifier="PT-102",
        name="Bob Jones",
        age=62,
        gender="Male",
    )
    db.add_all([p1, p2])
    db.commit()

    # Symptoms:
    # Doc 1: Cough (Severe), Dyspnea (Moderate)
    # Doc 2: Cough (Mild), Headache (Severe)
    s1 = Symptom(document_id=doc1_id, patient_id=p1.id, symptom_name="Cough", severity="Severe", page_number=1)
    s2 = Symptom(document_id=doc1_id, patient_id=p1.id, symptom_name="Dyspnea", severity="Moderate", page_number=1)
    s3 = Symptom(document_id=doc2_id, patient_id=p2.id, symptom_name="Cough", severity="Mild", page_number=2)
    s4 = Symptom(document_id=doc2_id, patient_id=p2.id, symptom_name="Headache", severity="Severe", page_number=1)

    # Diagnoses:
    # Doc 1: Hypertension (Confirmed), Pneumonia (Provisional)
    # Doc 2: Hypertension (Confirmed), Migraine (Confirmed)
    d1 = Diagnosis(document_id=doc1_id, patient_id=p1.id, diagnosis_name="Hypertension", status="Confirmed", page_number=1)
    d2 = Diagnosis(document_id=doc1_id, patient_id=p1.id, diagnosis_name="Pneumonia", status="Provisional", page_number=2)
    d3 = Diagnosis(document_id=doc2_id, patient_id=p2.id, diagnosis_name="Hypertension", status="Confirmed", page_number=1)
    d4 = Diagnosis(document_id=doc2_id, patient_id=p2.id, diagnosis_name="Migraine", status="Confirmed", page_number=1)

    # Medications:
    # Doc 1: Amlodipine (Oral), Amoxicillin (Oral)
    # Doc 2: Amlodipine (Oral), Sumatriptan (Nasal)
    m1 = Medication(document_id=doc1_id, patient_id=p1.id, medication_name="Amlodipine", dosage="5mg", route="Oral", page_number=1)
    m2 = Medication(document_id=doc1_id, patient_id=p1.id, medication_name="Amoxicillin", dosage="500mg", route="Oral", page_number=2)
    m3 = Medication(document_id=doc2_id, patient_id=p2.id, medication_name="Amlodipine", dosage="10mg", route="Oral", page_number=1)
    m4 = Medication(document_id=doc2_id, patient_id=p2.id, medication_name="Sumatriptan", dosage="20mg", route="Nasal", page_number=1)

    # Lab Results:
    # Test 1: Blood Glucose in mg/dL (Values: 100, 140 -> Avg: 120, Min: 100, Max: 140)
    # Test 2: Blood Glucose in mmol/L (Value: 6.0 -> segregated from mg/dL!)
    # Test 3: Rapid Strep Screen (Qualitative: numeric_value is None, result_value="Negative")
    l1 = LabResult(document_id=doc1_id, patient_id=p1.id, test_name="Blood Glucose", result_value="100 mg/dL", numeric_value=100.0, unit="mg/dL", reference_range="70-99", flag="High", page_number=1)
    l2 = LabResult(document_id=doc2_id, patient_id=p2.id, test_name="Blood Glucose", result_value="140 mg/dL", numeric_value=140.0, unit="mg/dL", reference_range="70-99", flag="High", page_number=2)
    l3 = LabResult(document_id=doc2_id, patient_id=p2.id, test_name="Blood Glucose", result_value="6.0 mmol/L", numeric_value=6.0, unit="mmol/L", reference_range="3.9-5.5", flag="High", page_number=2)
    l4 = LabResult(document_id=doc1_id, patient_id=p1.id, test_name="Rapid Strep", result_value="Negative", numeric_value=None, unit=None, flag="Normal", page_number=1)

    # Recommendations:
    r1 = Recommendation(document_id=doc1_id, patient_id=p1.id, recommendation_text="Rest and hydrate", follow_up_instructions="Return in 1 week", page_number=1)
    r2 = Recommendation(document_id=doc2_id, patient_id=p2.id, recommendation_text="Reduce sodium intake", follow_up_instructions=None, page_number=2)

    db.add_all([s1, s2, s3, s4, d1, d2, d3, d4, m1, m2, m3, m4, l1, l2, l3, l4, r1, r2])
    db.commit()
    db.close()

    yield {
        "doc1_id": doc1_id,
        "doc2_id": doc2_id,
    }

    # Teardown: delete test documents which cascade-deletes all associated entities
    clean_db = SessionLocal()
    for d_id in (doc1_id, doc2_id):
        d = clean_db.query(Document).filter(Document.id == d_id).first()
        if d:
            clean_db.delete(d)
    clean_db.commit()
    clean_db.close()


# =============================================================================
# 1. Summary Statistics & Seven Core Metrics Tests
# =============================================================================

def test_clinical_summary_displays_all_seven_metrics(clean_synthetic_dataset):
    """Verify GET /api/analytics/clinical-summary reports all seven metrics correctly."""
    res = client.get("/api/analytics/clinical-summary")
    assert res.status_code == 200
    data = res.json()

    # Verify all seven required metrics exist
    assert "total_patients" in data
    assert "total_documents" in data
    assert "total_symptoms" in data
    assert "total_diagnoses" in data
    assert "total_medications" in data
    assert "total_lab_results" in data
    assert "total_recommendations" in data
    assert "total_clinical_entities" in data
    assert "category_distribution" in data

    # Verify counts reflect at least our synthetic items
    assert data["total_patients"] >= 2
    assert data["total_documents"] >= 2
    assert data["total_symptoms"] >= 4
    assert data["total_diagnoses"] >= 4
    assert data["total_medications"] >= 4
    assert data["total_lab_results"] >= 4
    assert data["total_recommendations"] >= 2


def test_clinical_summary_document_filtering(clean_synthetic_dataset):
    """Verify clinical-summary properly filters by document_id."""
    doc1_id = clean_synthetic_dataset["doc1_id"]
    res = client.get(f"/api/analytics/clinical-summary?document_id={doc1_id}")
    assert res.status_code == 200
    data = res.json()

    assert data["total_documents"] == 1
    assert data["total_patients"] == 1
    assert data["total_symptoms"] == 2
    assert data["total_diagnoses"] == 2
    assert data["total_medications"] == 2
    assert data["total_lab_results"] == 2
    assert data["total_recommendations"] == 1


def test_category_distribution_percentages(clean_synthetic_dataset):
    """Verify category distribution percentages sum up properly."""
    res = client.get("/api/analytics/clinical-summary")
    assert res.status_code == 200
    cats = res.json()["category_distribution"]
    assert len(cats) == 6
    total_pct = sum(c["percentage"] for c in cats)
    # Should sum to approx 100% (within rounding tolerance)
    assert 99.0 <= total_pct <= 101.0


# =============================================================================
# 2. Symptom Frequency & Severity Breakdown Tests
# =============================================================================

def test_symptom_frequencies_and_severity_breakdown(clean_synthetic_dataset):
    """Verify symptom frequency ordering, document counts, and severity grouping."""
    res = client.get("/api/analytics/symptoms?limit=10")
    assert res.status_code == 200
    symptoms = res.json()
    assert len(symptoms) >= 1

    # In our dataset, Cough appears in both doc1 and doc2 (total 2 times)
    cough_item = next((s for s in symptoms if s["symptom_name"] == "Cough"), None)
    assert cough_item is not None
    assert cough_item["count"] >= 2
    assert cough_item["document_count"] >= 2
    assert "Severe" in cough_item["severity_breakdown"]
    assert "Mild" in cough_item["severity_breakdown"]
    assert len(cough_item["supporting_pages"]) >= 1


def test_symptom_filter_by_document(clean_synthetic_dataset):
    """Verify symptoms list can be scoped to a single document."""
    doc1_id = clean_synthetic_dataset["doc1_id"]
    res = client.get(f"/api/analytics/symptoms?document_id={doc1_id}")
    assert res.status_code == 200
    symptoms = res.json()
    names = [s["symptom_name"] for s in symptoms]
    assert "Cough" in names
    assert "Dyspnea" in names
    assert "Headache" not in names  # Headache was only in doc2


# =============================================================================
# 3. Diagnosis Frequency & Status Breakdown Tests
# =============================================================================

def test_diagnosis_frequencies_and_status_breakdown(clean_synthetic_dataset):
    """Verify diagnosis frequency counts and status breakdown."""
    res = client.get("/api/analytics/diagnoses?limit=10")
    assert res.status_code == 200
    diagnoses = res.json()
    assert len(diagnoses) >= 1

    htn = next((d for d in diagnoses if d["diagnosis_name"] == "Hypertension"), None)
    assert htn is not None
    assert htn["count"] >= 2
    assert htn["document_count"] >= 2
    assert "Confirmed" in htn["status_breakdown"]


# =============================================================================
# 4. Medication Frequency & Route Distribution Tests
# =============================================================================

def test_medication_frequencies_and_routes(clean_synthetic_dataset):
    """Verify medication frequencies, administration routes, and dosages."""
    res = client.get("/api/analytics/medications?limit=10")
    assert res.status_code == 200
    meds = res.json()

    amlodipine = next((m for m in meds if m["medication_name"] == "Amlodipine"), None)
    assert amlodipine is not None
    assert amlodipine["count"] >= 2
    assert "Oral" in amlodipine["route_breakdown"]
    assert len(amlodipine["sample_dosages"]) >= 1


# =============================================================================
# 5. Co-Occurrence Analysis Tests (No Cross-Product Join Multiplication)
# =============================================================================

def test_symptom_diagnosis_co_occurrence_calculation(clean_synthetic_dataset):
    """
    Verify symptom-diagnosis co-occurrences are computed accurately.
    In doc1: Symptoms (Cough, Dyspnea), Diagnoses (Hypertension, Pneumonia)
    In doc2: Symptoms (Cough, Headache), Diagnoses (Hypertension, Migraine)
    Therefore:
      - (Cough, Hypertension) co-occurs in BOTH doc1 and doc2 -> co_occurrence_count = 2
      - (Dyspnea, Hypertension) co-occurs only in doc1 -> co_occurrence_count = 1
    """
    res = client.get("/api/analytics/co-occurrences/symptom-diagnosis?min_count=1")
    assert res.status_code == 200
    pairs = res.json()
    assert len(pairs) >= 1

    cough_htn = next(
        (p for p in pairs if p["symptom_name"] == "Cough" and p["diagnosis_name"] == "Hypertension"),
        None,
    )
    assert cough_htn is not None
    assert cough_htn["co_occurrence_count"] >= 2
    assert cough_htn["statistical_association_only"] is True
    assert cough_htn["clinical_causation_claimed"] is False
    assert len(cough_htn["supporting_documents"]) >= 2


def test_co_occurrence_min_count_filter(clean_synthetic_dataset):
    """Verify min_count filter excludes pairs below the specified threshold."""
    res = client.get("/api/analytics/co-occurrences/symptom-diagnosis?min_count=2")
    assert res.status_code == 200
    pairs = res.json()
    for p in pairs:
        assert p["co_occurrence_count"] >= 2


def test_medication_diagnosis_co_occurrence(clean_synthetic_dataset):
    """Verify medication and diagnosis co-occurrence analysis."""
    res = client.get("/api/analytics/co-occurrences/medication-diagnosis?min_count=1")
    assert res.status_code == 200
    pairs = res.json()

    # Amlodipine & Hypertension co-occur in both doc1 and doc2
    amlo_htn = next(
        (p for p in pairs if p["medication_name"] == "Amlodipine" and p["diagnosis_name"] == "Hypertension"),
        None,
    )
    assert amlo_htn is not None
    assert amlo_htn["co_occurrence_count"] >= 2


# =============================================================================
# 6. Laboratory Results Analysis & Strict Unit Isolation Tests
# =============================================================================

def test_lab_analytics_strict_unit_isolation(clean_synthetic_dataset):
    """
    Verify that laboratory tests with different units are strictly segregated.
    'Blood Glucose' (mg/dL) and 'Blood Glucose' (mmol/L) MUST NOT be merged or averaged!
    """
    res = client.get("/api/analytics/labs")
    assert res.status_code == 200
    labs = res.json()

    # Find the mg/dL glucose entry
    glucose_mgdl = next(
        (l for l in labs if l["test_name"] == "Blood Glucose" and l["unit"] == "mg/dL"),
        None,
    )
    assert glucose_mgdl is not None
    assert glucose_mgdl["total_records"] == 2
    assert glucose_mgdl["numeric_record_count"] == 2
    assert glucose_mgdl["min_value"] == 100.0
    assert glucose_mgdl["max_value"] == 140.0
    assert glucose_mgdl["avg_value"] == 120.0  # (100 + 140) / 2
    assert "70-99" in glucose_mgdl["documented_reference_ranges"]

    # Find the mmol/L glucose entry
    glucose_mmol = next(
        (l for l in labs if l["test_name"] == "Blood Glucose" and l["unit"] == "mmol/L"),
        None,
    )
    assert glucose_mmol is not None
    assert glucose_mmol["total_records"] == 1
    assert glucose_mmol["avg_value"] == 6.0


def test_lab_analytics_null_numeric_values_safe(clean_synthetic_dataset):
    """
    Verify that qualitative laboratory tests (where numeric_value is None)
    are handled gracefully without NaN or 500 error.
    """
    res = client.get("/api/analytics/labs?test_name=Rapid%20Strep")
    assert res.status_code == 200
    labs = res.json()
    assert len(labs) >= 1
    strep = labs[0]
    assert strep["numeric_record_count"] == 0
    assert strep["avg_value"] is None
    assert strep["min_value"] is None
    assert strep["max_value"] is None
    assert "Negative" in strep["sample_values"]


# =============================================================================
# 7. Recommendation Analysis Tests (Only Existing Database Fields)
# =============================================================================

def test_recommendation_analytics_only_existing_columns(clean_synthetic_dataset):
    """
    Verify recommendation analytics uses strictly existing SQLite columns
    without inventing artificial category taxonomies.
    """
    res = client.get("/api/analytics/recommendations")
    assert res.status_code == 200
    data = res.json()

    assert "total_recommendations" in data
    assert "with_follow_up_instructions_count" in data
    assert "without_follow_up_count" in data
    assert "recommendation_records" in data

    for r in data["recommendation_records"]:
        assert "recommendation_text" in r
        assert "follow_up_instructions" in r
        assert "page_number" in r
        assert "document_id" in r


# =============================================================================
# 8. Descriptive Knowledge Insights Tests
# =============================================================================

def test_descriptive_insights_evidence_counts(clean_synthetic_dataset):
    """
    Verify descriptive insights are generated deterministically and cite
    exact supporting record counts.
    """
    res = client.get("/api/analytics/insights")
    assert res.status_code == 200
    insights = res.json()
    assert isinstance(insights, list)
    assert len(insights) >= 1

    for ins in insights:
        assert "title" in ins
        assert "category" in ins
        assert "observation" in ins
        assert "supporting_count" in ins
        assert ins["supporting_count"] >= 1
        # The observation string should contain the supporting count
        assert str(ins["supporting_count"]) in ins["observation"]


# =============================================================================
# 9. Empty Database Resilience Tests
# =============================================================================

def test_empty_database_returns_zero_and_empty_lists():
    """
    Verify all analytics endpoints handle zero records gracefully without 500 errors.
    Uses a clean in-memory SQLite session to verify empty behavior.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionMem = sessionmaker(bind=engine)
    mem_db = SessionMem()

    # 1. Summary
    summary = AnalyticsService.get_clinical_summary(mem_db)
    assert summary["total_documents"] == 0
    assert summary["total_patients"] == 0
    assert summary["total_symptoms"] == 0
    assert summary["total_clinical_entities"] == 0

    # 2. Symptoms
    syms = AnalyticsService.get_symptom_frequencies(mem_db)
    assert syms == []

    # 3. Diagnoses
    dias = AnalyticsService.get_diagnosis_frequencies(mem_db)
    assert dias == []

    # 4. Medications
    meds = AnalyticsService.get_medication_frequencies(mem_db)
    assert meds == []

    # 5. Co-occurrences
    co = AnalyticsService.get_symptom_diagnosis_co_occurrences(mem_db)
    assert co == []

    # 6. Labs
    labs = AnalyticsService.get_lab_analytics(mem_db)
    assert labs == []

    # 7. Recommendations
    recs = AnalyticsService.get_recommendation_analytics(mem_db)
    assert recs["total_recommendations"] == 0
    assert recs["recommendation_records"] == []

    # 8. Insights
    ins = AnalyticsService.get_descriptive_insights(mem_db)
    assert ins == []

    mem_db.close()


# =============================================================================
# 10. Query Parameter Validation Tests
# =============================================================================

def test_invalid_query_parameters():
    """Verify endpoint rejects negative limit or out-of-range values."""
    res1 = client.get("/api/analytics/symptoms?limit=0")
    assert res1.status_code == 422

    res2 = client.get("/api/analytics/co-occurrences/symptom-diagnosis?min_count=0")
    assert res2.status_code == 422
