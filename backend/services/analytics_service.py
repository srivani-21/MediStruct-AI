"""
backend/services/analytics_service.py

Pure SQLAlchemy analytics and clinical knowledge discovery service for MediStruct AI.

Design guarantees:
  1. All metrics and statistical distributions are derived deterministically
     from verified SQLite records — ZERO hardcoded or simulated values.
  2. Co-occurrences use distinct (document_id, entity_a, entity_b) subqueries
     to avoid duplicate join multiplication.
  3. Laboratory tests are grouped strictly by (test_name, unit) to prevent
     comparing or averaging incompatible units.
  4. Null numeric values in lab findings are handled safely without dropping
     qualitative test records.
  5. Recommendation analysis uses ONLY existing database columns (recommendation_text,
     follow_up_instructions, page_number) without inventing categories.
  6. Patient count uses distinct patient IDs to avoid double-counting documents.
  7. No statistical association is ever interpreted or claimed as clinical causation.
"""

from typing import Any, Dict, List, Optional
from sqlalchemy import func, distinct, desc, or_, and_
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


class AnalyticsService:
    """Service layer executing aggregation queries for Phase 5 Clinical Analytics."""

    # -------------------------------------------------------------------------
    # 1. Summary Statistics & Category Distribution
    # -------------------------------------------------------------------------
    @staticmethod
    def get_clinical_summary(
        db: Session,
        document_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calculates exact SQLite counts for all seven core entities:
          - Total Patients (distinct patient IDs)
          - Total Documents
          - Total Symptoms
          - Total Diagnoses
          - Total Medications
          - Total Laboratory Results
          - Total Recommendations
        Also calculates the cohort entity distribution across all 6 clinical categories.
        """
        # Document filtering queries
        doc_q = db.query(func.count(distinct(Document.id)))
        pat_q = db.query(func.count(distinct(Patient.id)))
        sym_q = db.query(func.count(Symptom.id))
        dia_q = db.query(func.count(Diagnosis.id))
        med_q = db.query(func.count(Medication.id))
        lab_q = db.query(func.count(LabResult.id))
        rec_q = db.query(func.count(Recommendation.id))

        if document_id:
            doc_q = doc_q.filter(Document.id == document_id)
            pat_q = pat_q.filter(Patient.document_id == document_id)
            sym_q = sym_q.filter(Symptom.document_id == document_id)
            dia_q = dia_q.filter(Diagnosis.document_id == document_id)
            med_q = med_q.filter(Medication.document_id == document_id)
            lab_q = lab_q.filter(LabResult.document_id == document_id)
            rec_q = rec_q.filter(Recommendation.document_id == document_id)

        total_docs = doc_q.scalar() or 0
        total_patients = pat_q.scalar() or 0
        total_symptoms = sym_q.scalar() or 0
        total_diagnoses = dia_q.scalar() or 0
        total_medications = med_q.scalar() or 0
        total_labs = lab_q.scalar() or 0
        total_recommendations = rec_q.scalar() or 0

        # Category distribution
        total_entities = (
            total_patients
            + total_symptoms
            + total_diagnoses
            + total_medications
            + total_labs
            + total_recommendations
        )

        categories = [
            {"category": "Patients", "count": total_patients},
            {"category": "Symptoms", "count": total_symptoms},
            {"category": "Diagnoses", "count": total_diagnoses},
            {"category": "Medications", "count": total_medications},
            {"category": "Lab Results", "count": total_labs},
            {"category": "Recommendations", "count": total_recommendations},
        ]

        category_distribution = []
        for cat in categories:
            cnt = cat["count"]
            pct = round((cnt / total_entities * 100), 1) if total_entities > 0 else 0.0
            category_distribution.append({
                "category": cat["category"],
                "count": cnt,
                "percentage": pct,
            })

        return {
            "total_documents": total_docs,
            "total_patients": total_patients,
            "total_symptoms": total_symptoms,
            "total_diagnoses": total_diagnoses,
            "total_medications": total_medications,
            "total_lab_results": total_labs,
            "total_recommendations": total_recommendations,
            "total_clinical_entities": total_entities,
            "category_distribution": category_distribution,
        }

    # -------------------------------------------------------------------------
    # 2. Symptom Frequency & Severity Analysis
    # -------------------------------------------------------------------------
    @staticmethod
    def get_symptom_frequencies(
        db: Session,
        document_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Computes symptom frequencies, distinct document appearances,
        severity distributions, and source page citations.
        """
        # Base query for top symptom names
        q = db.query(
            Symptom.symptom_name,
            func.count(Symptom.id).label("total_count"),
            func.count(distinct(Symptom.document_id)).label("document_count"),
        )
        if document_id:
            q = q.filter(Symptom.document_id == document_id)

        top_symptoms = (
            q.group_by(Symptom.symptom_name)
            .order_by(desc("total_count"), Symptom.symptom_name)
            .limit(limit)
            .all()
        )

        if not top_symptoms:
            return []

        results = []
        for name, count, doc_count in top_symptoms:
            # Fetch severity distribution for this symptom
            sev_q = db.query(
                Symptom.severity,
                func.count(Symptom.id),
            ).filter(Symptom.symptom_name == name)
            if document_id:
                sev_q = sev_q.filter(Symptom.document_id == document_id)

            sev_rows = sev_q.group_by(Symptom.severity).all()
            severity_breakdown = {}
            for sev, scnt in sev_rows:
                key = sev.strip().capitalize() if sev and sev.strip() else "Unspecified"
                severity_breakdown[key] = severity_breakdown.get(key, 0) + scnt

            # Fetch distinct page citations
            page_q = db.query(Symptom.page_number).distinct().filter(
                Symptom.symptom_name == name,
                Symptom.page_number.isnot(None),
            )
            if document_id:
                page_q = page_q.filter(Symptom.document_id == document_id)
            pages = sorted([p[0] for p in page_q.all() if p[0] is not None])

            # Fetch sample document IDs for auditability
            docs_q = db.query(Symptom.document_id).distinct().filter(
                Symptom.symptom_name == name
            )
            if document_id:
                docs_q = docs_q.filter(Symptom.document_id == document_id)
            supporting_docs = [d[0] for d in docs_q.limit(5).all()]

            results.append({
                "symptom_name": name,
                "count": count,
                "document_count": doc_count,
                "severity_breakdown": severity_breakdown,
                "supporting_pages": pages,
                "supporting_documents": supporting_docs,
            })

        return results

    # -------------------------------------------------------------------------
    # 3. Diagnosis Frequency & Status Analysis
    # -------------------------------------------------------------------------
    @staticmethod
    def get_diagnosis_frequencies(
        db: Session,
        document_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Computes diagnosis frequencies, distinct document appearances,
        clinical status distributions, and source page citations.
        """
        q = db.query(
            Diagnosis.diagnosis_name,
            func.count(Diagnosis.id).label("total_count"),
            func.count(distinct(Diagnosis.document_id)).label("document_count"),
        )
        if document_id:
            q = q.filter(Diagnosis.document_id == document_id)

        top_diagnoses = (
            q.group_by(Diagnosis.diagnosis_name)
            .order_by(desc("total_count"), Diagnosis.diagnosis_name)
            .limit(limit)
            .all()
        )

        if not top_diagnoses:
            return []

        results = []
        for name, count, doc_count in top_diagnoses:
            # Fetch status distribution for this diagnosis
            stat_q = db.query(
                Diagnosis.status,
                func.count(Diagnosis.id),
            ).filter(Diagnosis.diagnosis_name == name)
            if document_id:
                stat_q = stat_q.filter(Diagnosis.document_id == document_id)

            stat_rows = stat_q.group_by(Diagnosis.status).all()
            status_breakdown = {}
            for stat, scnt in stat_rows:
                key = stat.strip().capitalize() if stat and stat.strip() else "Unspecified"
                status_breakdown[key] = status_breakdown.get(key, 0) + scnt

            # Distinct page citations
            page_q = db.query(Diagnosis.page_number).distinct().filter(
                Diagnosis.diagnosis_name == name,
                Diagnosis.page_number.isnot(None),
            )
            if document_id:
                page_q = page_q.filter(Diagnosis.document_id == document_id)
            pages = sorted([p[0] for p in page_q.all() if p[0] is not None])

            docs_q = db.query(Diagnosis.document_id).distinct().filter(
                Diagnosis.diagnosis_name == name
            )
            if document_id:
                docs_q = docs_q.filter(Diagnosis.document_id == document_id)
            supporting_docs = [d[0] for d in docs_q.limit(5).all()]

            results.append({
                "diagnosis_name": name,
                "count": count,
                "document_count": doc_count,
                "status_breakdown": status_breakdown,
                "supporting_pages": pages,
                "supporting_documents": supporting_docs,
            })

        return results

    # -------------------------------------------------------------------------
    # 4. Medication Frequency & Route Distribution
    # -------------------------------------------------------------------------
    @staticmethod
    def get_medication_frequencies(
        db: Session,
        document_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Computes medication frequencies, administration routes, sample dosages,
        and supporting page citations.
        """
        q = db.query(
            Medication.medication_name,
            func.count(Medication.id).label("total_count"),
            func.count(distinct(Medication.document_id)).label("document_count"),
        )
        if document_id:
            q = q.filter(Medication.document_id == document_id)

        top_meds = (
            q.group_by(Medication.medication_name)
            .order_by(desc("total_count"), Medication.medication_name)
            .limit(limit)
            .all()
        )

        if not top_meds:
            return []

        results = []
        for name, count, doc_count in top_meds:
            # Route breakdown
            route_q = db.query(
                Medication.route,
                func.count(Medication.id),
            ).filter(Medication.medication_name == name)
            if document_id:
                route_q = route_q.filter(Medication.document_id == document_id)

            route_rows = route_q.group_by(Medication.route).all()
            route_breakdown = {}
            for r, rcnt in route_rows:
                key = r.strip().capitalize() if r and r.strip() else "Unspecified"
                route_breakdown[key] = route_breakdown.get(key, 0) + rcnt

            # Sample dosages (unique, non-null, limit 3)
            dosage_q = db.query(Medication.dosage).distinct().filter(
                Medication.medication_name == name,
                Medication.dosage.isnot(None),
            )
            if document_id:
                dosage_q = dosage_q.filter(Medication.document_id == document_id)
            sample_dosages = [d[0] for d in dosage_q.limit(3).all() if d[0]]

            # Distinct page citations
            page_q = db.query(Medication.page_number).distinct().filter(
                Medication.medication_name == name,
                Medication.page_number.isnot(None),
            )
            if document_id:
                page_q = page_q.filter(Medication.document_id == document_id)
            pages = sorted([p[0] for p in page_q.all() if p[0] is not None])

            docs_q = db.query(Medication.document_id).distinct().filter(
                Medication.medication_name == name
            )
            if document_id:
                docs_q = docs_q.filter(Medication.document_id == document_id)
            supporting_docs = [d[0] for d in docs_q.limit(5).all()]

            results.append({
                "medication_name": name,
                "count": count,
                "document_count": doc_count,
                "route_breakdown": route_breakdown,
                "sample_dosages": sample_dosages,
                "supporting_pages": pages,
                "supporting_documents": supporting_docs,
            })

        return results

    # -------------------------------------------------------------------------
    # 5. Symptom-Diagnosis Co-Occurrence Analysis
    # -------------------------------------------------------------------------
    @staticmethod
    def get_symptom_diagnosis_co_occurrences(
        db: Session,
        document_id: Optional[str] = None,
        min_count: int = 1,
        limit: int = 15,
    ) -> List[Dict[str, Any]]:
        """
        Analyzes documented co-occurrences of symptoms and diagnoses
        within the same medical document.

        Uses a DISTINCT subquery over (document_id, symptom_name, diagnosis_name)
        to prevent duplicate join multiplication when multiple instances exist.
        Never implies or claims clinical causation.
        """
        # Subquery: Distinct pairs per document to eliminate cartesian join inflation
        subq = db.query(
            Symptom.document_id.label("doc_id"),
            Symptom.symptom_name.label("sym_name"),
            Diagnosis.diagnosis_name.label("dia_name"),
            Symptom.page_number.label("sym_page"),
            Diagnosis.page_number.label("dia_page"),
        ).join(
            Diagnosis,
            Symptom.document_id == Diagnosis.document_id,
        )

        if document_id:
            subq = subq.filter(Symptom.document_id == document_id)

        # Build distinct subquery alias
        pair_alias = subq.distinct().subquery("distinct_sym_dia")

        # Aggregate counts across documents
        results_q = (
            db.query(
                pair_alias.c.sym_name,
                pair_alias.c.dia_name,
                func.count(distinct(pair_alias.c.doc_id)).label("co_occurrence_count"),
            )
            .group_by(pair_alias.c.sym_name, pair_alias.c.dia_name)
            .having(func.count(distinct(pair_alias.c.doc_id)) >= min_count)
            .order_by(desc("co_occurrence_count"), pair_alias.c.sym_name)
            .limit(limit)
            .all()
        )

        if not results_q:
            return []

        co_occurrences = []
        for sym, dia, count in results_q:
            # Supporting document IDs
            doc_ids = [
                r[0]
                for r in db.query(pair_alias.c.doc_id).distinct()
                .filter(
                    pair_alias.c.sym_name == sym,
                    pair_alias.c.dia_name == dia,
                )
                .limit(5)
                .all()
            ]

            # Collect source page references
            pages_sym = [
                r[0]
                for r in db.query(pair_alias.c.sym_page).distinct()
                .filter(
                    pair_alias.c.sym_name == sym,
                    pair_alias.c.dia_name == dia,
                    pair_alias.c.sym_page.isnot(None),
                )
                .all()
                if r[0] is not None
            ]
            pages_dia = [
                r[0]
                for r in db.query(pair_alias.c.dia_page).distinct()
                .filter(
                    pair_alias.c.sym_name == sym,
                    pair_alias.c.dia_name == dia,
                    pair_alias.c.dia_page.isnot(None),
                )
                .all()
                if r[0] is not None
            ]
            all_pages = sorted(list(set(pages_sym + pages_dia)))

            co_occurrences.append({
                "symptom_name": sym,
                "diagnosis_name": dia,
                "co_occurrence_count": count,
                "supporting_documents": doc_ids,
                "supporting_pages": all_pages,
                "statistical_association_only": True,
                "clinical_causation_claimed": False,
            })

        return co_occurrences

    # -------------------------------------------------------------------------
    # 6. Medication-Diagnosis Co-Occurrence Analysis
    # -------------------------------------------------------------------------
    @staticmethod
    def get_medication_diagnosis_co_occurrences(
        db: Session,
        document_id: Optional[str] = None,
        min_count: int = 1,
        limit: int = 15,
    ) -> List[Dict[str, Any]]:
        """
        Analyzes documented co-prescriptions/co-occurrences of medications
        and diagnoses within the same medical document.
        """
        subq = db.query(
            Medication.document_id.label("doc_id"),
            Medication.medication_name.label("med_name"),
            Diagnosis.diagnosis_name.label("dia_name"),
            Medication.page_number.label("med_page"),
            Diagnosis.page_number.label("dia_page"),
        ).join(
            Diagnosis,
            Medication.document_id == Diagnosis.document_id,
        )

        if document_id:
            subq = subq.filter(Medication.document_id == document_id)

        pair_alias = subq.distinct().subquery("distinct_med_dia")

        results_q = (
            db.query(
                pair_alias.c.med_name,
                pair_alias.c.dia_name,
                func.count(distinct(pair_alias.c.doc_id)).label("co_occurrence_count"),
            )
            .group_by(pair_alias.c.med_name, pair_alias.c.dia_name)
            .having(func.count(distinct(pair_alias.c.doc_id)) >= min_count)
            .order_by(desc("co_occurrence_count"), pair_alias.c.med_name)
            .limit(limit)
            .all()
        )

        if not results_q:
            return []

        co_occurrences = []
        for med, dia, count in results_q:
            doc_ids = [
                r[0]
                for r in db.query(pair_alias.c.doc_id).distinct()
                .filter(
                    pair_alias.c.med_name == med,
                    pair_alias.c.dia_name == dia,
                )
                .limit(5)
                .all()
            ]

            pages_med = [
                r[0]
                for r in db.query(pair_alias.c.med_page).distinct()
                .filter(
                    pair_alias.c.med_name == med,
                    pair_alias.c.dia_name == dia,
                    pair_alias.c.med_page.isnot(None),
                )
                .all()
                if r[0] is not None
            ]
            pages_dia = [
                r[0]
                for r in db.query(pair_alias.c.dia_page).distinct()
                .filter(
                    pair_alias.c.med_name == med,
                    pair_alias.c.dia_name == dia,
                    pair_alias.c.dia_page.isnot(None),
                )
                .all()
                if r[0] is not None
            ]
            all_pages = sorted(list(set(pages_med + pages_dia)))

            co_occurrences.append({
                "medication_name": med,
                "diagnosis_name": dia,
                "co_occurrence_count": count,
                "supporting_documents": doc_ids,
                "supporting_pages": all_pages,
                "statistical_association_only": True,
                "clinical_causation_claimed": False,
            })

        return co_occurrences

    # -------------------------------------------------------------------------
    # 7. Laboratory Results Analysis (Unit-Isolated)
    # -------------------------------------------------------------------------
    @staticmethod
    def get_lab_analytics(
        db: Session,
        document_id: Optional[str] = None,
        test_name: Optional[str] = None,
        limit: int = 15,
    ) -> List[Dict[str, Any]]:
        """
        Analyzes laboratory test findings strictly grouped by (test_name, unit).

        Guarantees:
          - Incompatible units are NEVER aggregated or averaged together.
          - Null numeric values are safely omitted from min/max/avg calculations
            while qualitative test records remain counted.
          - Reference ranges and flags are pulled directly from documented records.
        """
        # First discover top (test_name, unit) combinations
        q = db.query(
            LabResult.test_name,
            LabResult.unit,
            func.count(LabResult.id).label("total_count"),
            func.count(distinct(LabResult.document_id)).label("document_count"),
        )
        if document_id:
            q = q.filter(LabResult.document_id == document_id)
        if test_name:
            q = q.filter(LabResult.test_name.ilike(f"%{test_name}%"))

        top_tests = (
            q.group_by(LabResult.test_name, LabResult.unit)
            .order_by(desc("total_count"), LabResult.test_name)
            .limit(limit)
            .all()
        )

        if not top_tests:
            return []

        results = []
        for tname, tunit, count, doc_count in top_tests:
            clean_unit = tunit.strip() if tunit and tunit.strip() else "Unspecified"

            # Filter for this specific (test_name, unit) pair
            pair_q = db.query(LabResult).filter(LabResult.test_name == tname)
            if tunit:
                pair_q = pair_q.filter(LabResult.unit == tunit)
            else:
                pair_q = pair_q.filter(
                    or_(LabResult.unit.is_(None), LabResult.unit == "")
                )
            if document_id:
                pair_q = pair_q.filter(LabResult.document_id == document_id)

            lab_records = pair_q.all()

            # Numeric values calculation (safe handling of nulls)
            numeric_vals = [
                r.numeric_value
                for r in lab_records
                if r.numeric_value is not None
            ]

            if numeric_vals:
                min_val = round(float(min(numeric_vals)), 2)
                max_val = round(float(max(numeric_vals)), 2)
                avg_val = round(float(sum(numeric_vals) / len(numeric_vals)), 2)
                numeric_count = len(numeric_vals)
            else:
                min_val = None
                max_val = None
                avg_val = None
                numeric_count = 0

            # Diagnostic flag distribution (Normal, High, Low, Critical, etc.)
            flag_breakdown = {}
            for r in lab_records:
                flag_str = r.flag.strip().capitalize() if r.flag and r.flag.strip() else "Unspecified"
                flag_breakdown[flag_str] = flag_breakdown.get(flag_str, 0) + 1

            # Documented reference ranges (unique non-null strings)
            ref_ranges = sorted(list(set(
                r.reference_range.strip()
                for r in lab_records
                if r.reference_range and r.reference_range.strip()
            )))

            # Sample qualitative values if numeric_count == 0
            sample_values = [
                r.result_value
                for r in lab_records[:3]
                if r.result_value
            ]

            # Supporting pages
            pages = sorted(list(set(
                r.page_number
                for r in lab_records
                if r.page_number is not None
            )))

            # Supporting document IDs
            doc_ids = sorted(list(set(r.document_id for r in lab_records)))[:5]

            results.append({
                "test_name": tname,
                "unit": clean_unit,
                "total_records": count,
                "document_count": doc_count,
                "numeric_record_count": numeric_count,
                "min_value": min_val,
                "max_value": max_val,
                "avg_value": avg_val,
                "flag_breakdown": flag_breakdown,
                "documented_reference_ranges": ref_ranges,
                "sample_values": sample_values,
                "supporting_pages": pages,
                "supporting_documents": doc_ids,
            })

        return results

    # -------------------------------------------------------------------------
    # 8. Recommendation Analysis (Using ONLY Existing Database Columns)
    # -------------------------------------------------------------------------
    @staticmethod
    def get_recommendation_analytics(
        db: Session,
        document_id: Optional[str] = None,
        limit: int = 15,
    ) -> Dict[str, Any]:
        """
        Analyzes documented clinical recommendations.
        Uses ONLY actual existing database fields:
          - recommendation_text
          - follow_up_instructions
          - page_number
          - document_id
        Does not invent clinical recommendation categories.
        """
        q = db.query(Recommendation)
        if document_id:
            q = q.filter(Recommendation.document_id == document_id)

        total_recs = q.count()

        # Count how many records document specific follow-up instructions
        follow_up_q = q.filter(
            Recommendation.follow_up_instructions.isnot(None),
            Recommendation.follow_up_instructions != "",
        )
        follow_up_count = follow_up_q.count()

        # Retrieve recent recommendations with page citations
        records = (
            q.order_by(desc(Recommendation.created_at))
            .limit(limit)
            .all()
        )

        items = []
        for r in records:
            items.append({
                "id": r.id,
                "recommendation_text": r.recommendation_text,
                "follow_up_instructions": r.follow_up_instructions,
                "page_number": r.page_number,
                "document_id": r.document_id,
            })

        return {
            "total_recommendations": total_recs,
            "with_follow_up_instructions_count": follow_up_count,
            "without_follow_up_count": total_recs - follow_up_count,
            "recommendation_records": items,
        }

    # -------------------------------------------------------------------------
    # 9. Descriptive Knowledge Insights (Evidence-Based with Record Counts)
    # -------------------------------------------------------------------------
    @staticmethod
    def get_descriptive_insights(
        db: Session,
        document_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Compiles simple, deterministic, evidence-based clinical observations
        from stored SQLite records.
        Each insight explicitly states its supporting record count.
        Returns an empty list if data is insufficient, preventing hallucinations.
        """
        insights = []

        # 1. Top Symptom insight
        sym_q = db.query(
            Symptom.symptom_name,
            func.count(Symptom.id).label("cnt"),
            func.count(distinct(Symptom.document_id)).label("dcnt"),
        )
        if document_id:
            sym_q = sym_q.filter(Symptom.document_id == document_id)
        top_sym = (
            sym_q.group_by(Symptom.symptom_name)
            .order_by(desc("cnt"))
            .first()
        )
        if top_sym and top_sym[1] > 0:
            insights.append({
                "title": "Most Documented Symptom",
                "category": "symptom",
                "observation": (
                    f"'{top_sym[0]}' is the most frequently recorded symptom, "
                    f"documented {top_sym[1]} time(s) across {top_sym[2]} patient file(s)."
                ),
                "supporting_count": top_sym[1],
                "document_count": top_sym[2],
            })

        # 2. Top Diagnosis insight
        dia_q = db.query(
            Diagnosis.diagnosis_name,
            func.count(Diagnosis.id).label("cnt"),
            func.count(distinct(Diagnosis.document_id)).label("dcnt"),
        )
        if document_id:
            dia_q = dia_q.filter(Diagnosis.document_id == document_id)
        top_dia = (
            dia_q.group_by(Diagnosis.diagnosis_name)
            .order_by(desc("cnt"))
            .first()
        )
        if top_dia and top_dia[1] > 0:
            insights.append({
                "title": "Leading Documented Diagnosis",
                "category": "diagnosis",
                "observation": (
                    f"'{top_dia[0]}' is the primary documented clinical condition, "
                    f"appearing {top_dia[1]} time(s) across {top_dia[2]} file(s)."
                ),
                "supporting_count": top_dia[1],
                "document_count": top_dia[2],
            })

        # 3. Top Medication insight
        med_q = db.query(
            Medication.medication_name,
            func.count(Medication.id).label("cnt"),
            func.count(distinct(Medication.document_id)).label("dcnt"),
        )
        if document_id:
            med_q = med_q.filter(Medication.document_id == document_id)
        top_med = (
            med_q.group_by(Medication.medication_name)
            .order_by(desc("cnt"))
            .first()
        )
        if top_med and top_med[1] > 0:
            insights.append({
                "title": "Primary Documented Medication",
                "category": "medication",
                "observation": (
                    f"'{top_med[0]}' is the most frequently prescribed pharmaceutical, "
                    f"documented {top_med[1]} time(s) across {top_med[2]} patient record(s)."
                ),
                "supporting_count": top_med[1],
                "document_count": top_med[2],
            })

        # 4. Leading Co-Occurrence insight
        co_pairs = AnalyticsService.get_symptom_diagnosis_co_occurrences(
            db=db, document_id=document_id, min_count=1, limit=1
        )
        if co_pairs:
            top_pair = co_pairs[0]
            insights.append({
                "title": "Documented Clinical Co-Occurrence",
                "category": "co_occurrence",
                "observation": (
                    f"Symptom '{top_pair['symptom_name']}' and diagnosis '{top_pair['diagnosis_name']}' "
                    f"were co-documented in {top_pair['co_occurrence_count']} patient file(s). "
                    "(Note: Statistical co-occurrence represents concurrent documentation, not medical causation)."
                ),
                "supporting_count": top_pair["co_occurrence_count"],
                "document_count": len(top_pair.get("supporting_documents", [])),
            })

        # 5. Lab Finding insight
        labs = AnalyticsService.get_lab_analytics(
            db=db, document_id=document_id, limit=1
        )
        if labs:
            top_lab = labs[0]
            val_clause = (
                f"with an average observed value of {top_lab['avg_value']} {top_lab['unit']}"
                if top_lab['avg_value'] is not None
                else "with qualitative or categorical findings"
            )
            insights.append({
                "title": "Most Frequent Diagnostic Test",
                "category": "lab",
                "observation": (
                    f"'{top_lab['test_name']}' is the most frequently performed laboratory assessment "
                    f"({top_lab['total_records']} record(s)), {val_clause}."
                ),
                "supporting_count": top_lab["total_records"],
                "document_count": top_lab["document_count"],
            })

        return insights
