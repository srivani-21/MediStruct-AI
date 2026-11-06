from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.database import get_db
from backend.models.document import Document
from backend.models.patient import Patient
from backend.models.clinical_records import (
    Symptom,
    Diagnosis,
    Medication,
    LabResult,
    Recommendation,
)
from backend.models.schemas import (
    OverviewMetricsResponse,
    ClinicalSummaryResponse,
    SymptomFrequencyItem,
    DiagnosisFrequencyItem,
    MedicationFrequencyItem,
    CoOccurrenceItem,
    LabAnalyticsItem,
    RecommendationAnalyticsResponse,
    DescriptiveInsightItem,
)
from backend.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/api/analytics", tags=["Analytics & Discovery"])


# ==============================================================================
# Existing Phase 1-2 Endpoint (Preserved for Overview Page)
# ==============================================================================

@router.get("/overview", response_model=OverviewMetricsResponse)
def get_overview_metrics(db: Session = Depends(get_db)):
    """
    Computes real database-derived counts for the Overview dashboard.
    No hardcoded, fake, or simulated statistics.
    """
    total_docs = db.query(func.count(Document.id)).scalar() or 0
    proc_docs = (
        db.query(func.count(Document.id))
        .filter(Document.processing_status == "COMPLETED")
        .scalar()
        or 0
    )
    total_patients = db.query(func.count(Patient.id)).scalar() or 0
    total_symptoms = db.query(func.count(Symptom.id)).scalar() or 0
    total_diagnoses = db.query(func.count(Diagnosis.id)).scalar() or 0
    total_medications = db.query(func.count(Medication.id)).scalar() or 0
    total_labs = db.query(func.count(LabResult.id)).scalar() or 0
    total_recs = db.query(func.count(Recommendation.id)).scalar() or 0

    return OverviewMetricsResponse(
        total_documents=total_docs,
        successfully_processed_documents=proc_docs,
        total_patients=total_patients,
        total_symptoms=total_symptoms,
        total_diagnoses=total_diagnoses,
        total_medications=total_medications,
        total_lab_tests=total_labs,
        total_recommendations=total_recs,
    )


# ==============================================================================
# Phase 5: Clinical Statistics & Category Distributions
# ==============================================================================

@router.get("/clinical-summary", response_model=ClinicalSummaryResponse)
def get_clinical_summary(
    document_id: Optional[str] = Query(None, description="Optional filter by document ID"),
    db: Session = Depends(get_db),
):
    """
    Returns exact SQLite-derived counts for all seven core entities:
    Patients, Documents, Symptoms, Diagnoses, Medications, Lab Results, Recommendations.
    Also provides relative percentage distribution across categories.
    """
    return AnalyticsService.get_clinical_summary(db=db, document_id=document_id)


# ==============================================================================
# Phase 5: Symptom and Diagnosis Analysis
# ==============================================================================

@router.get("/symptoms", response_model=List[SymptomFrequencyItem])
def get_symptom_analytics(
    document_id: Optional[str] = Query(None, description="Filter by document ID"),
    limit: int = Query(10, ge=1, le=100, description="Max symptoms to return"),
    db: Session = Depends(get_db),
):
    """
    Computes symptom frequencies, distinct document appearances,
    severity distributions, and source page citations.
    """
    return AnalyticsService.get_symptom_frequencies(
        db=db, document_id=document_id, limit=limit
    )


@router.get("/diagnoses", response_model=List[DiagnosisFrequencyItem])
def get_diagnosis_analytics(
    document_id: Optional[str] = Query(None, description="Filter by document ID"),
    limit: int = Query(10, ge=1, le=100, description="Max diagnoses to return"),
    db: Session = Depends(get_db),
):
    """
    Computes diagnosis frequencies, distinct document appearances,
    clinical status distributions, and source page citations.
    """
    return AnalyticsService.get_diagnosis_frequencies(
        db=db, document_id=document_id, limit=limit
    )


# ==============================================================================
# Phase 5: Medication Analysis
# ==============================================================================

@router.get("/medications", response_model=List[MedicationFrequencyItem])
def get_medication_analytics(
    document_id: Optional[str] = Query(None, description="Filter by document ID"),
    limit: int = Query(10, ge=1, le=100, description="Max medications to return"),
    db: Session = Depends(get_db),
):
    """
    Computes medication frequencies, administration routes, sample dosages,
    and supporting page citations.
    """
    return AnalyticsService.get_medication_frequencies(
        db=db, document_id=document_id, limit=limit
    )


# ==============================================================================
# Phase 5: Co-Occurrence Analysis (Evidence-Based Associations)
# ==============================================================================

@router.get("/co-occurrences/symptom-diagnosis", response_model=List[CoOccurrenceItem])
def get_symptom_diagnosis_co_occurrences(
    document_id: Optional[str] = Query(None, description="Filter by document ID"),
    min_count: int = Query(1, ge=1, description="Minimum co-occurrence threshold"),
    limit: int = Query(15, ge=1, le=100, description="Max pairs to return"),
    db: Session = Depends(get_db),
):
    """
    Analyzes documented co-occurrences of symptoms and diagnoses within the same document.
    Uses distinct (document, symptom, diagnosis) aggregation to prevent duplicate join multiplication.
    Never claims or implies clinical causation.
    """
    return AnalyticsService.get_symptom_diagnosis_co_occurrences(
        db=db, document_id=document_id, min_count=min_count, limit=limit
    )


@router.get("/co-occurrences/medication-diagnosis", response_model=List[CoOccurrenceItem])
def get_medication_diagnosis_co_occurrences(
    document_id: Optional[str] = Query(None, description="Filter by document ID"),
    min_count: int = Query(1, ge=1, description="Minimum co-occurrence threshold"),
    limit: int = Query(15, ge=1, le=100, description="Max pairs to return"),
    db: Session = Depends(get_db),
):
    """
    Analyzes documented co-occurrences of medications and diagnoses within the same document.
    Uses distinct aggregation to avoid cross-product join multiplication.
    """
    return AnalyticsService.get_medication_diagnosis_co_occurrences(
        db=db, document_id=document_id, min_count=min_count, limit=limit
    )


# ==============================================================================
# Phase 5: Laboratory Results Analysis (Unit-Isolated)
# ==============================================================================

@router.get("/labs", response_model=List[LabAnalyticsItem])
def get_lab_analytics(
    document_id: Optional[str] = Query(None, description="Filter by document ID"),
    test_name: Optional[str] = Query(None, description="Filter or search by lab test name"),
    limit: int = Query(15, ge=1, le=100, description="Max lab test groups to return"),
    db: Session = Depends(get_db),
):
    """
    Analyzes laboratory findings strictly grouped by (test_name, unit).
    Guarantees that incompatible units are never aggregated or compared together.
    Safely calculates numeric min, max, avg where numeric_value exists.
    """
    return AnalyticsService.get_lab_analytics(
        db=db, document_id=document_id, test_name=test_name, limit=limit
    )


# ==============================================================================
# Phase 5: Recommendation Analysis
# ==============================================================================

@router.get("/recommendations", response_model=RecommendationAnalyticsResponse)
def get_recommendation_analytics(
    document_id: Optional[str] = Query(None, description="Filter by document ID"),
    limit: int = Query(15, ge=1, le=100, description="Max records to return"),
    db: Session = Depends(get_db),
):
    """
    Analyzes documented clinical recommendations using ONLY existing database columns:
    recommendation_text, follow_up_instructions, page_number, document_id.
    Does not invent non-existent recommendation taxonomies.
    """
    return AnalyticsService.get_recommendation_analytics(
        db=db, document_id=document_id, limit=limit
    )


# ==============================================================================
# Phase 5: Descriptive Knowledge Insights
# ==============================================================================

@router.get("/insights", response_model=List[DescriptiveInsightItem])
def get_descriptive_insights(
    document_id: Optional[str] = Query(None, description="Filter by document ID"),
    db: Session = Depends(get_db),
):
    """
    Generates deterministic, evidence-based observations from verified SQLite records.
    Every observation includes its supporting record count.
    Returns empty list if insufficient records exist (no AI hallucination).
    """
    return AnalyticsService.get_descriptive_insights(db=db, document_id=document_id)
