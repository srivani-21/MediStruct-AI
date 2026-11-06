from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_

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
    PatientResponse,
    SymptomResponse,
    DiagnosisResponse,
    MedicationResponse,
    LabResultResponse,
    RecommendationResponse,
    StructuredClinicalPayload,
)
from backend.services.clinical_extractor import ClinicalExtractor
from backend.services.clinical_persistence import persist_structured_clinical_data

router = APIRouter(prefix="/api/records", tags=["Structured Clinical Records"])


# ==============================================================================
# Patient Endpoints
# ==============================================================================

@router.get("/patients", response_model=List[PatientResponse])
def get_patients(
    document_id: Optional[str] = Query(None, description="Filter by source document ID"),
    search: Optional[str] = Query(None, description="Search by patient name or identifier"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieve extracted patient demographic records with optional search."""
    query = db.query(Patient)
    if document_id:
        query = query.filter(Patient.document_id == document_id)
    if search:
        query = query.filter(
            or_(
                Patient.name.ilike(f"%{search}%"),
                Patient.patient_identifier.ilike(f"%{search}%"),
            )
        )
    return query.order_by(desc(Patient.created_at)).offset(offset).limit(limit).all()


# ==============================================================================
# Symptoms Endpoints
# ==============================================================================

@router.get("/symptoms", response_model=List[SymptomResponse])
def get_symptoms(
    document_id: Optional[str] = Query(None, description="Filter by source document ID"),
    severity: Optional[str] = Query(None, description="Filter by severity (e.g. Mild, Moderate, Severe)"),
    search: Optional[str] = Query(None, description="Search by symptom name or description"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieve extracted clinical symptoms with severity, source page citations, and search."""
    query = db.query(Symptom)
    if document_id:
        query = query.filter(Symptom.document_id == document_id)
    if severity:
        query = query.filter(Symptom.severity.ilike(f"%{severity}%"))
    if search:
        query = query.filter(
            or_(
                Symptom.symptom_name.ilike(f"%{search}%"),
                Symptom.description.ilike(f"%{search}%"),
            )
        )
    return query.order_by(desc(Symptom.created_at)).offset(offset).limit(limit).all()


# ==============================================================================
# Diagnoses Endpoints
# ==============================================================================

@router.get("/diagnoses", response_model=List[DiagnosisResponse])
def get_diagnoses(
    document_id: Optional[str] = Query(None, description="Filter by source document ID"),
    search: Optional[str] = Query(None, description="Search by diagnosis name or description"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieve extracted medical diagnoses with descriptions, page citations, and search."""
    query = db.query(Diagnosis)
    if document_id:
        query = query.filter(Diagnosis.document_id == document_id)
    if search:
        query = query.filter(
            or_(
                Diagnosis.diagnosis_name.ilike(f"%{search}%"),
                Diagnosis.description.ilike(f"%{search}%"),
            )
        )
    return query.order_by(desc(Diagnosis.created_at)).offset(offset).limit(limit).all()


# ==============================================================================
# Medications Endpoints
# ==============================================================================

@router.get("/medications", response_model=List[MedicationResponse])
def get_medications(
    document_id: Optional[str] = Query(None, description="Filter by source document ID"),
    search: Optional[str] = Query(None, description="Search by medication name or dosage"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieve extracted prescribed medications, dosages, routes, page citations, and search."""
    query = db.query(Medication)
    if document_id:
        query = query.filter(Medication.document_id == document_id)
    if search:
        query = query.filter(
            or_(
                Medication.medication_name.ilike(f"%{search}%"),
                Medication.dosage.ilike(f"%{search}%"),
            )
        )
    return query.order_by(desc(Medication.created_at)).offset(offset).limit(limit).all()


# ==============================================================================
# Laboratory Results Endpoints
# ==============================================================================

@router.get("/labs", response_model=List[LabResultResponse])
def get_lab_results(
    document_id: Optional[str] = Query(None, description="Filter by source document ID"),
    flag: Optional[str] = Query(None, description="Filter by diagnostic flag: Normal, High, Low, Critical"),
    search: Optional[str] = Query(None, description="Search by test name or result value"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieve laboratory and diagnostic test findings with units, reference ranges, and search."""
    query = db.query(LabResult)
    if document_id:
        query = query.filter(LabResult.document_id == document_id)
    if flag:
        query = query.filter(LabResult.flag.ilike(f"%{flag}%"))
    if search:
        query = query.filter(
            or_(
                LabResult.test_name.ilike(f"%{search}%"),
                LabResult.result_value.ilike(f"%{search}%"),
            )
        )
    return query.order_by(desc(LabResult.created_at)).offset(offset).limit(limit).all()


# ==============================================================================
# Recommendations Endpoints
# ==============================================================================

@router.get("/recommendations", response_model=List[RecommendationResponse])
def get_recommendations(
    document_id: Optional[str] = Query(None, description="Filter by source document ID"),
    search: Optional[str] = Query(None, description="Search by recommendation text"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieve clinical follow-ups, lifestyle advice, care recommendations, and search."""
    query = db.query(Recommendation)
    if document_id:
        query = query.filter(Recommendation.document_id == document_id)
    if search:
        query = query.filter(
            or_(
                Recommendation.recommendation_text.ilike(f"%{search}%"),
                Recommendation.follow_up_instructions.ilike(f"%{search}%"),
            )
        )
    return query.order_by(desc(Recommendation.created_at)).offset(offset).limit(limit).all()


# ==============================================================================
# Transactional Batch Structuring Persistence Endpoint
# ==============================================================================

@router.post("/structured", status_code=status.HTTP_201_CREATED)
def save_structured_clinical_data(
    payload: StructuredClinicalPayload,
    db: Session = Depends(get_db),
):
    """
    Atomically persist a complete set of extracted clinical entities for a document.
    Ensures transactional safety: if any insertion fails, the entire transaction is rolled back.
    Preserves exact document ID and page number references for research traceability.
    """
    try:
        result = persist_structured_clinical_data(db, payload)
        return result
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(val_err)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transaction rolled back due to error: {str(exc)}"
        )


# ==============================================================================
# AI-Powered Clinical Structuring Execution Endpoint
# ==============================================================================

@router.post("/structure/{document_id}", status_code=status.HTTP_200_OK)
def structure_document_clinical_data(
    document_id: str,
    db: Session = Depends(get_db),
):
    """
    Trigger AI clinical structuring for a document using Gemini 3.8 Flash.
    Strictly enforces human-verification gate: unverified handwritten pages block structuring.
    Extracts 6 clinical categories, validates schema, and transactionally persists entities.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found."
        )

    # Evaluate source text eligibility and human-verification status
    is_eligible, source_text, block_reason = ClinicalExtractor.get_eligible_document_text(doc, db)
    if not is_eligible:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=block_reason,
        )

    # Perform AI extraction
    extractor = ClinicalExtractor()
    try:
        payload = extractor.extract_clinical_data(document_id, source_text)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(val_err),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    # Persist extracted entities atomically into SQLite
    try:
        persist_res = persist_structured_clinical_data(db, payload)
        return {
            "success": True,
            "document_id": document_id,
            "message": "Clinical entities successfully extracted and persisted.",
            "entities_saved": persist_res["entities_saved"],
            "patient_id": persist_res["patient_id"],
            "payload": payload.model_dump(),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database persistence failed: {str(exc)}",
        )


@router.get("/status/{document_id}")
def get_document_structuring_status(
    document_id: str,
    db: Session = Depends(get_db),
):
    """
    Check clinical structuring eligibility and counts of currently persisted records.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found."
        )

    is_eligible, _, block_reason = ClinicalExtractor.get_eligible_document_text(doc, db)

    counts = {
        "symptoms": len(doc.symptoms),
        "diagnoses": len(doc.diagnoses),
        "medications": len(doc.medications),
        "lab_results": len(doc.lab_results),
        "recommendations": len(doc.recommendations),
    }
    total_entities = sum(counts.values()) + (1 if doc.patient else 0)

    return {
        "document_id": doc.id,
        "filename": doc.filename,
        "document_type": doc.document_type,
        "handwriting_detected": doc.handwriting_detected,
        "processing_status": doc.processing_status,
        "is_eligible_for_structuring": is_eligible,
        "block_reason": block_reason,
        "patient": doc.patient.name if doc.patient else None,
        "entity_counts": counts,
        "total_entities_saved": total_entities,
        "is_structured": total_entities > 0,
    }
