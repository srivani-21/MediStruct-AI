from typing import Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.models.document import Document
from backend.models.patient import Patient
from backend.models.clinical_records import (
    Symptom,
    Diagnosis,
    Medication,
    LabResult,
    Recommendation,
)
from backend.models.schemas import StructuredClinicalPayload


def persist_structured_clinical_data(
    db: Session,
    payload: StructuredClinicalPayload,
) -> Dict[str, Any]:
    """
    Atomically persist a complete set of extracted clinical entities for a document.
    Ensures transactional safety: if any insertion fails, the entire transaction is rolled back.
    Preserves exact document ID and page number references for clinical research traceability.
    Prevents duplicate entity records for the same document and page.
    """
    # 1. Verify parent document exists
    doc = db.query(Document).filter(Document.id == payload.document_id).first()
    if not doc:
        raise ValueError(f"Parent document '{payload.document_id}' not found in database.")

    try:
        # 2. Patient record handling
        patient_id = None
        if payload.patient and (payload.patient.name or payload.patient.patient_identifier or payload.patient.age is not None):
            # Check if patient already associated with this document
            patient_rec = db.query(Patient).filter(Patient.document_id == payload.document_id).first()
            if not patient_rec:
                patient_rec = Patient(
                    document_id=payload.document_id,
                    patient_identifier=payload.patient.patient_identifier,
                    name=payload.patient.name,
                    age=payload.patient.age,
                    gender=payload.patient.gender,
                    demographic_notes=payload.patient.demographic_notes,
                )
                db.add(patient_rec)
                db.flush()  # Populate patient_rec.id
            else:
                # Update existing fields without overwriting with null
                if payload.patient.patient_identifier:
                    patient_rec.patient_identifier = payload.patient.patient_identifier
                if payload.patient.name:
                    patient_rec.name = payload.patient.name
                if payload.patient.age is not None:
                    patient_rec.age = payload.patient.age
                if payload.patient.gender:
                    patient_rec.gender = payload.patient.gender
                if payload.patient.demographic_notes:
                    patient_rec.demographic_notes = payload.patient.demographic_notes
                db.flush()

            patient_id = patient_rec.id

        # 3. Symptoms
        symptom_count = 0
        for s in payload.symptoms:
            if s.symptom_name and s.symptom_name.strip():
                exists = db.query(Symptom).filter(
                    Symptom.document_id == payload.document_id,
                    Symptom.symptom_name == s.symptom_name.strip(),
                    Symptom.page_number == s.page_number,
                ).first()
                if not exists:
                    db.add(Symptom(
                        document_id=payload.document_id,
                        patient_id=patient_id,
                        symptom_name=s.symptom_name.strip(),
                        description=s.description,
                        duration=s.duration,
                        severity=s.severity,
                        page_number=s.page_number,
                    ))
                    symptom_count += 1

        # 4. Diagnoses
        diagnosis_count = 0
        for d in payload.diagnoses:
            if d.diagnosis_name and d.diagnosis_name.strip():
                exists = db.query(Diagnosis).filter(
                    Diagnosis.document_id == payload.document_id,
                    Diagnosis.diagnosis_name == d.diagnosis_name.strip(),
                    Diagnosis.page_number == d.page_number,
                ).first()
                if not exists:
                    db.add(Diagnosis(
                        document_id=payload.document_id,
                        patient_id=patient_id,
                        diagnosis_name=d.diagnosis_name.strip(),
                        description=d.description,
                        diagnosis_date=d.diagnosis_date,
                        status=d.status,
                        page_number=d.page_number,
                    ))
                    diagnosis_count += 1

        # 5. Medications
        medication_count = 0
        for m in payload.medications:
            if m.medication_name and m.medication_name.strip():
                exists = db.query(Medication).filter(
                    Medication.document_id == payload.document_id,
                    Medication.medication_name == m.medication_name.strip(),
                    Medication.page_number == m.page_number,
                ).first()
                if not exists:
                    db.add(Medication(
                        document_id=payload.document_id,
                        patient_id=patient_id,
                        medication_name=m.medication_name.strip(),
                        dosage=m.dosage,
                        frequency=m.frequency,
                        duration=m.duration,
                        route=m.route,
                        page_number=m.page_number,
                    ))
                    medication_count += 1

        # 6. Lab Results
        lab_count = 0
        for l in payload.lab_results:
            if l.test_name and l.test_name.strip():
                exists = db.query(LabResult).filter(
                    LabResult.document_id == payload.document_id,
                    LabResult.test_name == l.test_name.strip(),
                    LabResult.page_number == l.page_number,
                ).first()
                if not exists:
                    num_val = l.numeric_value
                    if num_val is None and l.result_value:
                        try:
                            clean_str = "".join([c for c in l.result_value if c.isdigit() or c == "."])
                            if clean_str:
                                num_val = float(clean_str)
                        except Exception:
                            num_val = None

                    db.add(LabResult(
                        document_id=payload.document_id,
                        patient_id=patient_id,
                        test_name=l.test_name.strip(),
                        result_value=l.result_value.strip(),
                        numeric_value=num_val,
                        unit=l.unit,
                        reference_range=l.reference_range,
                        flag=l.flag,
                        test_date=l.test_date,
                        page_number=l.page_number,
                    ))
                    lab_count += 1

        # 7. Recommendations
        rec_count = 0
        for r in payload.recommendations:
            if r.recommendation_text and r.recommendation_text.strip():
                exists = db.query(Recommendation).filter(
                    Recommendation.document_id == payload.document_id,
                    Recommendation.recommendation_text == r.recommendation_text.strip(),
                    Recommendation.page_number == r.page_number,
                ).first()
                if not exists:
                    db.add(Recommendation(
                        document_id=payload.document_id,
                        patient_id=patient_id,
                        recommendation_text=r.recommendation_text.strip(),
                        follow_up_instructions=r.follow_up_instructions,
                        page_number=r.page_number,
                    ))
                    rec_count += 1

        # 8. Mark document completed
        doc.processing_status = "COMPLETED"
        doc.processed_at = datetime.now(timezone.utc)
        doc.error_message = None

        db.commit()

        return {
            "success": True,
            "document_id": payload.document_id,
            "patient_id": patient_id,
            "entities_saved": {
                "symptoms": symptom_count,
                "diagnoses": diagnosis_count,
                "medications": medication_count,
                "lab_results": lab_count,
                "recommendations": rec_count,
            },
        }

    except Exception:
        db.rollback()
        raise
