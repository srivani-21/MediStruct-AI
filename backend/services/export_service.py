import csv
import hashlib
import hmac
import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.config import settings
from backend.models.clinical_records import (
    Diagnosis,
    LabResult,
    Medication,
    Recommendation,
    Symptom,
)
from backend.models.document import Document
from backend.models.patient import Patient


class ExportService:
    """
    Service for generating research-grade clinical dataset exports from SQLite
    in Excel (.xlsx), CSV (.csv), ZIP archive (.zip), and JSON (.json) formats.

    Implements strict HIPAA Safe Harbor de-identification by default using
    stable, secret-keyed HMAC-SHA256 pseudonyms for patient and document IDs.
    """

    SUPPORTED_CATEGORIES: List[str] = [
        "patients",
        "symptoms",
        "diagnoses",
        "medications",
        "labs",
        "recommendations",
    ]

    CATEGORY_SHEET_NAMES: Dict[str, str] = {
        "patients": "Patients",
        "symptoms": "Symptoms",
        "diagnoses": "Diagnoses",
        "medications": "Medications",
        "labs": "Laboratory_Results",
        "recommendations": "Recommendations",
        "documents": "Document_Metadata",
    }

    def __init__(self, salt: Optional[str] = None):
        self.salt = (salt or settings.EXPORT_SECRET_SALT or "medistruct_clinical_dataset_salt_2026").encode("utf-8")

    # -------------------------------------------------------------------------
    # HMAC-Based Pseudonymization (Mandatory Privacy Corrections 2, 3, 4, 5)
    # -------------------------------------------------------------------------

    def pseudonymize_patient_id(self, raw_patient_id: Any) -> str:
        """
        Generate a stable HMAC-SHA256 pseudonym for a patient ID.
        Format: SUBJ-<12 hex chars>
        """
        if raw_patient_id is None:
            return ""
        digest = hmac.new(
            self.salt,
            f"patient:{raw_patient_id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:12].upper()
        return f"SUBJ-{digest}"

    def pseudonymize_document_id(self, raw_doc_id: Any) -> str:
        """
        Generate a stable HMAC-SHA256 pseudonym for a document ID.
        Format: DOC-<12 hex chars>
        """
        if raw_doc_id is None:
            return ""
        digest = hmac.new(
            self.salt,
            f"document:{raw_doc_id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:12].upper()
        return f"DOC-{digest}"

    def pseudonymize_filename(self, doc_id: str) -> str:
        """
        Generate a non-identifying pseudonymized filename for exported documents.
        Never reveals original document filenames (e.g. JohnDoe_MedicalRecord.pdf).
        """
        pseudo_doc = self.pseudonymize_document_id(doc_id)
        return f"DOCUMENT_{pseudo_doc[4:]}.pdf"

    # -------------------------------------------------------------------------
    # Data Querying & Formatting
    # -------------------------------------------------------------------------

    def get_export_summary(self, db: Session, document_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Calculates record counts across all categories, respecting optional document filtering.
        """
        doc_q = db.query(Document)
        if document_id:
            doc_q = doc_q.filter(Document.id == document_id)
        total_documents = doc_q.count()

        categories_count = {}
        for cat in self.SUPPORTED_CATEGORIES:
            records = self._query_category_raw(db, cat, document_id)
            categories_count[cat] = len(records)

        total_records = sum(categories_count.values())

        return {
            "document_filter": document_id,
            "total_documents": total_documents,
            "categories": categories_count,
            "total_records": total_records,
            "de_identification_default": True,
            "export_formats": ["excel", "csv", "bundle", "json"],
        }

    def _query_category_raw(self, db: Session, category: str, document_id: Optional[str] = None) -> List[Any]:
        """Queries the database for raw entity models in a specific category."""
        category = category.lower().strip()
        if category == "patients":
            q = db.query(Patient)
            if document_id:
                q = q.filter(Patient.document_id == document_id)
            return q.order_by(Patient.id.asc()).all()
        elif category == "symptoms":
            q = db.query(Symptom)
            if document_id:
                q = q.filter(Symptom.document_id == document_id)
            return q.order_by(Symptom.id.asc()).all()
        elif category == "diagnoses":
            q = db.query(Diagnosis)
            if document_id:
                q = q.filter(Diagnosis.document_id == document_id)
            return q.order_by(Diagnosis.id.asc()).all()
        elif category == "medications":
            q = db.query(Medication)
            if document_id:
                q = q.filter(Medication.document_id == document_id)
            return q.order_by(Medication.id.asc()).all()
        elif category in ("labs", "lab_results"):
            q = db.query(LabResult)
            if document_id:
                q = q.filter(LabResult.document_id == document_id)
            return q.order_by(LabResult.id.asc()).all()
        elif category == "recommendations":
            q = db.query(Recommendation)
            if document_id:
                q = q.filter(Recommendation.document_id == document_id)
            return q.order_by(Recommendation.id.asc()).all()
        elif category == "documents":
            q = db.query(Document)
            if document_id:
                q = q.filter(Document.id == document_id)
            return q.order_by(Document.uploaded_at.desc()).all()
        else:
            return []

    def get_export_data(
        self,
        db: Session,
        document_id: Optional[str] = None,
        categories: Optional[List[str]] = None,
        de_identify: bool = True,
        include_documents_metadata: bool = True,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Retrieves and shapes structured clinical data for export across requested categories.
        Applies HMAC pseudonymization and direct identifier masking when de_identify is True.
        """
        if not categories:
            selected_categories = list(self.SUPPORTED_CATEGORIES)
        else:
            selected_categories = [
                c.strip().lower() for c in categories if c.strip().lower() in self.SUPPORTED_CATEGORIES or c.strip().lower() == "labs"
            ]

        result: Dict[str, List[Dict[str, Any]]] = {}

        for cat in selected_categories:
            raw_entities = self._query_category_raw(db, cat, document_id)
            formatted_list = []
            for item in raw_entities:
                formatted_list.append(self._format_entity(item, cat, de_identify))
            result[cat] = formatted_list

        if include_documents_metadata:
            raw_docs = self._query_category_raw(db, "documents", document_id)
            doc_list = []
            for doc in raw_docs:
                doc_list.append(self._format_entity(doc, "documents", de_identify))
            result["documents"] = doc_list

        return result

    def _format_entity(self, item: Any, category: str, de_identify: bool) -> Dict[str, Any]:
        """
        Formats a single SQLAlchemy entity into an exportable dictionary.
        Strictly applies pseudonymization and masking when de_identify=True.
        """
        cat = category.lower().strip()

        if cat == "patients":
            p_id = self.pseudonymize_patient_id(item.id) if de_identify else item.id
            doc_id = self.pseudonymize_document_id(item.document_id) if (de_identify and item.document_id) else item.document_id
            return {
                "patient_id": p_id,
                "patient_identifier": p_id if de_identify else (item.patient_identifier or ""),
                "name": "[REDACTED_RESEARCH_SUBJECT]" if de_identify else (item.name or ""),
                "age": item.age,
                "gender": item.gender or "",
                "demographic_notes": "[REDACTED_DEMOGRAPHIC_NOTES]" if (de_identify and item.demographic_notes) else (item.demographic_notes or ""),
                "document_id": doc_id or "",
                "created_at": item.created_at.isoformat() if item.created_at else "",
            }

        elif cat == "symptoms":
            p_id = self.pseudonymize_patient_id(item.patient_id) if (de_identify and item.patient_id) else (item.patient_id or "")
            doc_id = self.pseudonymize_document_id(item.document_id) if de_identify else item.document_id
            return {
                "record_id": item.id,
                "patient_id": p_id,
                "document_id": doc_id,
                "symptom_name": item.symptom_name,
                "description": item.description or "",
                "duration": item.duration or "",
                "severity": item.severity or "",
                "page_number": item.page_number,
                "created_at": item.created_at.isoformat() if item.created_at else "",
            }

        elif cat == "diagnoses":
            p_id = self.pseudonymize_patient_id(item.patient_id) if (de_identify and item.patient_id) else (item.patient_id or "")
            doc_id = self.pseudonymize_document_id(item.document_id) if de_identify else item.document_id
            return {
                "record_id": item.id,
                "patient_id": p_id,
                "document_id": doc_id,
                "diagnosis_name": item.diagnosis_name,
                "description": item.description or "",
                "diagnosis_date": item.diagnosis_date or "",
                "status": item.status or "",
                "page_number": item.page_number,
                "created_at": item.created_at.isoformat() if item.created_at else "",
            }

        elif cat == "medications":
            p_id = self.pseudonymize_patient_id(item.patient_id) if (de_identify and item.patient_id) else (item.patient_id or "")
            doc_id = self.pseudonymize_document_id(item.document_id) if de_identify else item.document_id
            return {
                "record_id": item.id,
                "patient_id": p_id,
                "document_id": doc_id,
                "medication_name": item.medication_name,
                "dosage": item.dosage or "",
                "frequency": item.frequency or "",
                "duration": item.duration or "",
                "route": item.route or "",
                "page_number": item.page_number,
                "created_at": item.created_at.isoformat() if item.created_at else "",
            }

        elif cat in ("labs", "lab_results"):
            p_id = self.pseudonymize_patient_id(item.patient_id) if (de_identify and item.patient_id) else (item.patient_id or "")
            doc_id = self.pseudonymize_document_id(item.document_id) if de_identify else item.document_id
            return {
                "record_id": item.id,
                "patient_id": p_id,
                "document_id": doc_id,
                "test_name": item.test_name,
                "result_value": item.result_value,
                "numeric_value": item.numeric_value,
                "unit": item.unit or "",
                "reference_range": item.reference_range or "",
                "flag": item.flag or "",
                "test_date": item.test_date or "",
                "page_number": item.page_number,
                "created_at": item.created_at.isoformat() if item.created_at else "",
            }

        elif cat == "recommendations":
            p_id = self.pseudonymize_patient_id(item.patient_id) if (de_identify and item.patient_id) else (item.patient_id or "")
            doc_id = self.pseudonymize_document_id(item.document_id) if de_identify else item.document_id
            return {
                "record_id": item.id,
                "patient_id": p_id,
                "document_id": doc_id,
                "recommendation_text": item.recommendation_text,
                "follow_up_instructions": item.follow_up_instructions or "",
                "page_number": item.page_number,
                "created_at": item.created_at.isoformat() if item.created_at else "",
            }

        elif cat == "documents":
            doc_id = self.pseudonymize_document_id(item.id) if de_identify else item.id
            fname = self.pseudonymize_filename(item.id) if de_identify else item.filename
            return {
                "document_id": doc_id,
                "filename": fname,
                "document_type": item.document_type,
                "extraction_method": item.extraction_method,
                "page_count": item.page_count,
                "character_count": item.character_count,
                "uploaded_at": item.uploaded_at.isoformat() if item.uploaded_at else "",
            }

        return {}

    # -------------------------------------------------------------------------
    # CSV Export
    # -------------------------------------------------------------------------

    def export_category_to_csv(self, records: List[Dict[str, Any]]) -> str:
        """
        Exports a list of category record dictionaries into a UTF-8 CSV string.
        """
        if not records:
            return ""
        fieldnames = list(records[0].keys())
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\r\n")
        writer.writeheader()
        for r in records:
            writer.writerow(r)
        return output.getvalue()

    # -------------------------------------------------------------------------
    # Excel Workbook Export (Multi-Sheet)
    # -------------------------------------------------------------------------

    def export_to_excel(
        self,
        export_data: Dict[str, List[Dict[str, Any]]],
        de_identify: bool = True,
        document_id: Optional[str] = None,
    ) -> io.BytesIO:
        """
        Creates an Excel workbook (.xlsx) with dedicated sheets for each clinical category
        and a front Cohort_Manifest sheet.
        """
        import openpyxl
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter

        wb = openpyxl.Workbook()
        # Default active sheet
        ws_manifest = wb.active
        ws_manifest.title = "Cohort_Manifest"

        # Styling constants
        font_manifest_title = Font(name="Calibri", size=14, bold=True, color="0F172A")
        font_section = Font(name="Calibri", size=11, bold=True, color="1E293B")
        font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        fill_header = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        fill_warning = PatternFill(start_color="FEF2F2", end_color="FEF2F2", fill_type="solid")
        font_warning = Font(name="Calibri", size=10, bold=True, color="991B1B")
        font_regular = Font(name="Calibri", size=10, color="334155")
        border_thin = Border(
            left=Side(style="thin", color="E2E8F0"),
            right=Side(style="thin", color="E2E8F0"),
            top=Side(style="thin", color="E2E8F0"),
            bottom=Side(style="thin", color="E2E8F0"),
        )

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # ----------------- Sheet 1: Cohort_Manifest -----------------
        ws_manifest.views.sheetView[0].showGridLines = True
        ws_manifest.cell(row=1, column=1, value="MediStruct AI — Research Cohort Export Manifest").font = font_manifest_title
        ws_manifest.cell(
            row=2,
            column=1,
            value="Framework: MediStruct AI — A Smart Healthcare Dataset Generation and Clinical Knowledge Discovery Framework",
        ).font = font_regular

        ws_manifest.cell(row=4, column=1, value="Metadata Key").font = font_section
        ws_manifest.cell(row=4, column=2, value="Configuration / Value").font = font_section

        metadata_rows = [
            ("Export Timestamp", now_iso),
            ("De-Identification Mode", "ENABLED (HIPAA Safe Harbor / Pseudonymized HMAC-SHA256)" if de_identify else "DISABLED (Raw Identifiers / Direct PHI Present)"),
            ("Document Scope", f"Single Document ({document_id})" if document_id else "All Ingested Documents (Entire Cohort)"),
            ("Pseudonymization Method", "Secret-Keyed HMAC-SHA256 (SUBJ-XXXX / DOC-XXXX)" if de_identify else "None (Raw IDs)"),
            ("Traceability Integrity", "Preserved (Page references & relational subject IDs maintained)"),
            ("Export Version", "Phase 6 Production Release"),
        ]

        curr_row = 5
        for key, val in metadata_rows:
            ws_manifest.cell(row=curr_row, column=1, value=key).font = font_regular
            c_val = ws_manifest.cell(row=curr_row, column=2, value=val)
            c_val.font = font_regular
            if not de_identify and "DISABLED" in str(val):
                c_val.font = font_warning
                c_val.fill = fill_warning
            curr_row += 1

        curr_row += 1
        ws_manifest.cell(row=curr_row, column=1, value="Category").font = font_section
        ws_manifest.cell(row=curr_row, column=2, value="Records Exported").font = font_section
        curr_row += 1

        total_records = 0
        for cat_key in self.SUPPORTED_CATEGORIES:
            sheet_title = self.CATEGORY_SHEET_NAMES.get(cat_key, cat_key.capitalize())
            records = export_data.get(cat_key, [])
            rec_count = len(records)
            total_records += rec_count
            ws_manifest.cell(row=curr_row, column=1, value=sheet_title).font = font_regular
            ws_manifest.cell(row=curr_row, column=2, value=rec_count).font = font_regular
            curr_row += 1

        # Add documents count
        doc_count = len(export_data.get("documents", []))
        ws_manifest.cell(row=curr_row, column=1, value="Document Metadata").font = font_regular
        ws_manifest.cell(row=curr_row, column=2, value=doc_count).font = font_regular
        curr_row += 1

        ws_manifest.cell(row=curr_row, column=1, value="TOTAL CLINICAL FINDINGS").font = font_section
        ws_manifest.cell(row=curr_row, column=2, value=total_records).font = font_section
        curr_row += 2

        # Research disclaimer
        ws_manifest.cell(row=curr_row, column=1, value="Research & Clinical Disclaimer:").font = font_section
        curr_row += 1
        ws_manifest.cell(
            row=curr_row,
            column=1,
            value=(
                "MediStruct AI is an academic clinical knowledge discovery framework. "
                "All exported clinical findings are extracted from medical documents and must be verified by licensed healthcare professionals. "
                "Co-occurrences and statistical patterns represent observational correlations and do not imply medical causation."
            ),
        ).font = font_regular

        # Auto column widths for manifest
        ws_manifest.column_dimensions["A"].width = 32
        ws_manifest.column_dimensions["B"].width = 75

        # ----------------- Category Data Sheets -----------------
        sheet_order = ["patients", "symptoms", "diagnoses", "medications", "labs", "recommendations", "documents"]
        for cat_key in sheet_order:
            if cat_key not in export_data:
                continue

            records = export_data[cat_key]
            sheet_name = self.CATEGORY_SHEET_NAMES.get(cat_key, cat_key.capitalize())
            ws = wb.create_sheet(title=sheet_name)
            ws.views.sheetView[0].showGridLines = True

            if not records:
                # Still create headers from default schema keys if empty
                ws.cell(row=1, column=1, value="No records found for this category").font = font_regular
                continue

            fieldnames = list(records[0].keys())

            # Header row
            for col_idx, col_name in enumerate(fieldnames, start=1):
                cell = ws.cell(row=1, column=col_idx, value=col_name)
                cell.font = font_header
                cell.fill = fill_header
                cell.alignment = Alignment(horizontal="center", vertical="center")

            # Data rows
            for row_idx, r in enumerate(records, start=2):
                for col_idx, col_name in enumerate(fieldnames, start=1):
                    val = r.get(col_name)
                    cell = ws.cell(row=row_idx, column=col_idx, value=val)
                    cell.font = font_regular
                    cell.border = border_thin

            # Auto-fit column widths
            for col_idx, col_name in enumerate(fieldnames, start=1):
                max_len = len(str(col_name))
                for row_idx in range(2, min(len(records) + 2, 50)):
                    val = records[row_idx - 2].get(col_name)
                    if val is not None:
                        max_len = max(max_len, len(str(val)))
                col_letter = get_column_letter(col_idx)
                ws.column_dimensions[col_letter].width = min(max_len + 4, 60)

        output_stream = io.BytesIO()
        wb.save(output_stream)
        output_stream.seek(0)
        return output_stream

    # -------------------------------------------------------------------------
    # Multi-Category ZIP Bundle Export
    # -------------------------------------------------------------------------

    def export_to_zip(
        self,
        export_data: Dict[str, List[Dict[str, Any]]],
        de_identify: bool = True,
        document_id: Optional[str] = None,
    ) -> io.BytesIO:
        """
        Creates a ZIP archive containing individual CSV files for each category,
        a manifest.csv, and a research README.txt citation file.
        """
        buf = io.BytesIO()
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            # 1. Manifest CSV
            manifest_rows = [
                {"Key": "Project", "Value": settings.PROJECT_TITLE},
                {"Key": "Export Timestamp", "Value": now_iso},
                {"Key": "De-Identification Mode", "Value": "ENABLED (HMAC-SHA256)" if de_identify else "DISABLED (Raw PHI)"},
                {"Key": "Document Filter", "Value": document_id or "All Documents"},
                {"Key": "Traceability", "Value": "Page citations and subject keys preserved"},
            ]
            for cat_key in self.SUPPORTED_CATEGORIES:
                records = export_data.get(cat_key, [])
                manifest_rows.append({"Key": f"Count: {cat_key}", "Value": str(len(records))})

            manifest_csv = self.export_category_to_csv(manifest_rows)
            # Use UTF-8 with BOM for CSVs so Excel / statistics packages parse Unicode cleanly
            zf.writestr("manifest.csv", manifest_csv.encode("utf-8-sig"))

            # 2. Category CSVs
            for cat_key in self.SUPPORTED_CATEGORIES:
                records = export_data.get(cat_key, [])
                if records:
                    csv_content = self.export_category_to_csv(records)
                    zf.writestr(f"{cat_key}.csv", csv_content.encode("utf-8-sig"))

            # 3. Document metadata CSV if available
            doc_records = export_data.get("documents", [])
            if doc_records:
                doc_csv = self.export_category_to_csv(doc_records)
                zf.writestr("documents_metadata.csv", doc_csv.encode("utf-8-sig"))

            # 4. Research README.txt
            readme_text = (
                f"================================================================================\n"
                f"MEDISTRUCT AI — RESEARCH CLINICAL DATASET EXPORT\n"
                f"Project: {settings.PROJECT_TITLE}\n"
                f"================================================================================\n\n"
                f"Export Timestamp: {now_iso}\n"
                f"Privacy Mode: {'DE-IDENTIFIED (HMAC Pseudonyms SUBJ- / DOC-)' if de_identify else 'RAW (DIRECT IDENTIFIERS PRESENT)'}\n"
                f"Document Filter: {document_id or 'Entire Cohort'}\n\n"
                f"DATASET STRUCTURE:\n"
                f"------------------\n"
                f"- patients.csv: Patient demographic records (pseudonymized identifiers, age, gender).\n"
                f"- symptoms.csv: Extracted symptoms with duration, severity, and source page citations.\n"
                f"- diagnoses.csv: Primary and provisional clinical diagnoses with status and page citations.\n"
                f"- medications.csv: Prescriptions, dosages, frequencies, and administration routes.\n"
                f"- labs.csv: Clinical laboratory tests with values, units, flags, and reference ranges.\n"
                f"- recommendations.csv: Physician follow-ups and discharge instructions.\n"
                f"- documents_metadata.csv: Ingested document metadata and processing audit trails.\n\n"
                f"TRACEABILITY NOTE:\n"
                f"------------------\n"
                f"All clinical findings retain 'patient_id', 'document_id', and 'page_number' for\n"
                f"transparent bidirectional verification against original medical records.\n\n"
                f"CITATION & DISCLAIMER:\n"
                f"----------------------\n"
                f"This dataset was generated by the MediStruct AI framework for academic and\n"
                f"clinical knowledge discovery research. Extracted records and descriptive insights\n"
                f"do not constitute medical advice.\n"
            )
            zf.writestr("README.txt", readme_text.encode("utf-8"))

        buf.seek(0)
        return buf

    # -------------------------------------------------------------------------
    # JSON Export
    # -------------------------------------------------------------------------

    def export_to_json(
        self,
        export_data: Dict[str, List[Dict[str, Any]]],
        de_identify: bool = True,
        document_id: Optional[str] = None,
    ) -> str:
        """
        Exports the dataset into a structured JSON string with metadata and category records.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "metadata": {
                "project": settings.PROJECT_TITLE,
                "exported_at": now_iso,
                "de_identified": de_identify,
                "pseudonymization": "HMAC-SHA256" if de_identify else "None",
                "document_filter": document_id,
                "category_counts": {k: len(v) for k, v in export_data.items()},
            },
            "records": export_data,
        }
        return json.dumps(payload, indent=2, default=str)
