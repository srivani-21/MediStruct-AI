from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.schemas import ExportSummaryResponse
from backend.services.export_service import ExportService

router = APIRouter(prefix="/api/export", tags=["Dataset Export"])


def get_export_service() -> ExportService:
    return ExportService()


@router.get("/summary", response_model=ExportSummaryResponse)
def get_export_summary(
    document_id: Optional[str] = Query(None, description="Optional document ID to scope export preview"),
    db: Session = Depends(get_db),
    export_svc: ExportService = Depends(get_export_service),
):
    """
    Returns record counts per clinical category and cohort summary for the export preview panel.
    """
    try:
        return export_svc.get_export_summary(db, document_id=document_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate export summary: {str(exc)}")


@router.get("/excel")
def export_excel_dataset(
    document_id: Optional[str] = Query(None, description="Optional document ID to scope export"),
    categories: Optional[str] = Query(None, description="Comma-separated category names to export"),
    de_identify: bool = Query(True, description="Strict HIPAA Safe Harbor pseudonymization (default: True)"),
    db: Session = Depends(get_db),
    export_svc: ExportService = Depends(get_export_service),
):
    """
    Exports structured clinical findings into a multi-sheet research Excel workbook (.xlsx).
    Includes Cohort_Manifest and individual sheets for selected categories.
    """
    try:
        cat_list = [c.strip() for c in categories.split(",")] if categories else None
        export_data = export_svc.get_export_data(
            db=db,
            document_id=document_id,
            categories=cat_list,
            de_identify=de_identify,
            include_documents_metadata=True,
        )

        excel_stream = export_svc.export_to_excel(
            export_data=export_data,
            de_identify=de_identify,
            document_id=document_id,
        )

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        mode = "deidentified" if de_identify else "identified"
        filename = f"medistruct_clinical_dataset_{ts}_{mode}.xlsx"

        return Response(
            content=excel_stream.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate Excel export: {str(exc)}")


@router.get("/csv/{category}")
def export_single_category_csv(
    category: str,
    document_id: Optional[str] = Query(None, description="Optional document ID to scope export"),
    de_identify: bool = Query(True, description="Strict HIPAA Safe Harbor pseudonymization (default: True)"),
    db: Session = Depends(get_db),
    export_svc: ExportService = Depends(get_export_service),
):
    """
    Exports a single clinical category as a flat UTF-8 CSV table for statistical analysis.
    """
    valid_categories = export_svc.SUPPORTED_CATEGORIES + ["documents", "lab_results"]
    cat_normalized = category.lower().strip()
    if cat_normalized not in valid_categories:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category '{category}'. Valid categories are: {', '.join(export_svc.SUPPORTED_CATEGORIES + ['documents'])}",
        )

    try:
        export_data = export_svc.get_export_data(
            db=db,
            document_id=document_id,
            categories=[cat_normalized],
            de_identify=de_identify,
            include_documents_metadata=(cat_normalized == "documents"),
        )

        records = export_data.get(cat_normalized, [])
        csv_text = export_svc.export_category_to_csv(records)
        csv_bytes = csv_text.encode("utf-8-sig")

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        mode = "deidentified" if de_identify else "identified"
        filename = f"medistruct_{cat_normalized}_{ts}_{mode}.csv"

        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate CSV export: {str(exc)}")


@router.get("/bundle")
def export_zip_bundle(
    document_id: Optional[str] = Query(None, description="Optional document ID to scope export"),
    categories: Optional[str] = Query(None, description="Comma-separated category names to export"),
    de_identify: bool = Query(True, description="Strict HIPAA Safe Harbor pseudonymization (default: True)"),
    db: Session = Depends(get_db),
    export_svc: ExportService = Depends(get_export_service),
):
    """
    Exports selected clinical categories as a multi-CSV ZIP archive bundle
    including manifest.csv and README.txt.
    """
    try:
        cat_list = [c.strip() for c in categories.split(",")] if categories else None
        export_data = export_svc.get_export_data(
            db=db,
            document_id=document_id,
            categories=cat_list,
            de_identify=de_identify,
            include_documents_metadata=True,
        )

        zip_stream = export_svc.export_to_zip(
            export_data=export_data,
            de_identify=de_identify,
            document_id=document_id,
        )

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        mode = "deidentified" if de_identify else "identified"
        filename = f"medistruct_dataset_bundle_{ts}_{mode}.zip"

        return Response(
            content=zip_stream.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate ZIP bundle: {str(exc)}")


@router.get("/json")
def export_json_dataset(
    document_id: Optional[str] = Query(None, description="Optional document ID to scope export"),
    categories: Optional[str] = Query(None, description="Comma-separated category names to export"),
    de_identify: bool = Query(True, description="Strict HIPAA Safe Harbor pseudonymization (default: True)"),
    db: Session = Depends(get_db),
    export_svc: ExportService = Depends(get_export_service),
):
    """
    Exports structured findings in hierarchical JSON format with dataset metadata.
    """
    try:
        cat_list = [c.strip() for c in categories.split(",")] if categories else None
        export_data = export_svc.get_export_data(
            db=db,
            document_id=document_id,
            categories=cat_list,
            de_identify=de_identify,
            include_documents_metadata=True,
        )

        json_str = export_svc.export_to_json(
            export_data=export_data,
            de_identify=de_identify,
            document_id=document_id,
        )

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        mode = "deidentified" if de_identify else "identified"
        filename = f"medistruct_clinical_dataset_{ts}_{mode}.json"

        return Response(
            content=json_str.encode("utf-8"),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate JSON export: {str(exc)}")
