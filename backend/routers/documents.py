import os
import shutil
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.database import get_db
from backend.config import settings
from backend.models.document import Document
from backend.models.page_extraction import PageExtraction
from backend.models.schemas import (
    DocumentResponse,
    DocumentDetailResponse,
    PatientResponse,
    PageExtractionResponse,
    VerifyRequest,
)
from backend.utils.file_validation import (
    validate_document_file,
    sanitize_filename,
    generate_document_id,
)
from backend.services.document_processor import DocumentProcessor

router = APIRouter(prefix="/api/documents", tags=["Documents"])


@router.post("/upload", response_model=List[DocumentResponse], status_code=status.HTTP_201_CREATED)
async def upload_documents(
    files: List[UploadFile] = File(..., description="One or more medical documents (PDF, JPG, PNG)"),
    db: Session = Depends(get_db),
):
    """
    Upload one or multiple medical documents (PDFs or scanned images).
    Validates file formats, creates unique document IDs, saves files safely to disk,
    and initializes database records in PENDING status.
    Preserves successful documents even if an individual document has an error.
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided for upload."
        )

    upload_dir = Path(settings.UPLOAD_DIRECTORY)
    upload_dir.mkdir(parents=True, exist_ok=True)

    created_documents: List[Document] = []
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    for file in files:
        try:
            # Format and basic validation
            validate_document_file(file)

            doc_id = generate_document_id()
            safe_name = sanitize_filename(file.filename or "medical_document.pdf")
            saved_filename = f"{doc_id}_{safe_name}"
            target_path = upload_dir / saved_filename

            # Save uploaded bytes to storage
            bytes_written = 0
            with target_path.open("wb") as buffer:
                while chunk := await file.read(1024 * 1024):  # 1MB chunks
                    bytes_written += len(chunk)
                    if bytes_written > max_bytes:
                        buffer.close()
                        if target_path.exists():
                            target_path.unlink()
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"File '{file.filename}' exceeded {settings.MAX_UPLOAD_SIZE_MB}MB limit during upload."
                        )
                    buffer.write(chunk)

            # Persist document metadata in SQLite
            doc_record = Document(
                id=doc_id,
                filename=file.filename or safe_name,
                stored_path=str(target_path),
                file_size_bytes=bytes_written,
                page_count=0,
                document_type="unknown",
                handwriting_detected=False,
                extraction_method="pending",
                raw_text=None,
                character_count=0,
                processing_status="PENDING",
                error_message=None,
                uploaded_at=datetime.now(timezone.utc),
            )
            db.add(doc_record)
            db.commit()
            db.refresh(doc_record)
            created_documents.append(doc_record)

        except HTTPException:
            if len(files) == 1:
                raise
        except Exception as exc:
            db.rollback()
            if len(files) == 1:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to process '{file.filename}': {str(exc)}"
                )

    if not created_documents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="None of the uploaded files could be successfully validated and stored."
        )

    return created_documents


@router.get("", response_model=List[DocumentResponse])
def list_documents(
    search: Optional[str] = Query(None, description="Search by filename"),
    status: Optional[str] = Query(None, description="Filter by status: PENDING, PROCESSING, COMPLETED, FAILED"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    List uploaded medical documents with optional search, status filtering, and pagination.
    """
    query = db.query(Document)

    if search:
        query = query.filter(Document.filename.ilike(f"%{search}%"))

    if status:
        query = query.filter(Document.processing_status == status.upper())

    query = query.order_by(desc(Document.uploaded_at))
    documents = query.offset(offset).limit(limit).all()
    return documents


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document_detail(document_id: str, db: Session = Depends(get_db)):
    """
    Retrieve full details for a document including associated clinical entity counts.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found."
        )

    counts = {
        "symptoms": len(doc.symptoms),
        "diagnoses": len(doc.diagnoses),
        "medications": len(doc.medications),
        "lab_results": len(doc.lab_results),
        "recommendations": len(doc.recommendations),
    }

    patient_resp = PatientResponse.model_validate(doc.patient) if doc.patient else None

    return DocumentDetailResponse(
        id=doc.id,
        filename=doc.filename,
        file_size_bytes=doc.file_size_bytes,
        page_count=doc.page_count,
        document_type=doc.document_type,
        handwriting_detected=doc.handwriting_detected,
        extraction_method=doc.extraction_method,
        processing_status=doc.processing_status,
        character_count=doc.character_count,
        error_message=doc.error_message,
        uploaded_at=doc.uploaded_at,
        processed_at=doc.processed_at,
        raw_text=doc.raw_text,
        patient=patient_resp,
        record_counts=counts,
    )


@router.get("/{document_id}/status")
def get_document_status(document_id: str, db: Session = Depends(get_db)):
    """
    Quick status polling endpoint for tracking document extraction progress.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found."
        )

    return {
        "id": doc.id,
        "filename": doc.filename,
        "status": doc.processing_status,
        "document_type": doc.document_type,
        "handwriting_detected": doc.handwriting_detected,
        "page_count": doc.page_count,
        "character_count": doc.character_count,
        "error_message": doc.error_message,
        "processed_at": doc.processed_at,
    }


@router.post("/{document_id}/process", status_code=status.HTTP_200_OK)
def process_document(
    document_id: str,
    force_ocr: bool = Query(False, description="Force Tesseract OCR across all pages regardless of digital text"),
    db: Session = Depends(get_db),
):
    """
    Trigger digital text extraction, scanned OCR, and handwriting recognition pipeline.
    """
    processor = DocumentProcessor()
    try:
        result = processor.process_document(document_id=document_id, db=db, force_ocr=force_ocr)
        return result
    except FileNotFoundError as fnf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(fnf)
        )
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(val_err)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extraction failed: {str(exc)}"
        )


@router.post("/{document_id}/structure", status_code=status.HTTP_200_OK)
def structure_document(document_id: str, db: Session = Depends(get_db)):
    """
    Trigger clinical entity structuring for a document using Gemini AI.
    Respects human-verification rules for handwritten pages.
    """
    from backend.services.clinical_extractor import ClinicalExtractor
    from backend.services.clinical_persistence import persist_structured_clinical_data

    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found."
        )

    is_eligible, source_text, block_reason = ClinicalExtractor.get_eligible_document_text(doc, db)
    if not is_eligible:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=block_reason,
        )

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

    try:
        persist_res = persist_structured_clinical_data(db, payload)
        return {
            "success": True,
            "document_id": document_id,
            "message": "Clinical entities successfully structured and persisted.",
            "entities_saved": persist_res["entities_saved"],
            "patient_id": persist_res["patient_id"],
            "payload": payload.model_dump(),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database persistence failed: {str(exc)}",
        )


@router.get("/{document_id}/pages", response_model=List[PageExtractionResponse])
def get_document_pages(document_id: str, db: Session = Depends(get_db)):
    """
    Retrieve per-page extraction records and verification status for a document.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found."
        )

    pages = (
        db.query(PageExtraction)
        .filter(PageExtraction.document_id == document_id)
        .order_by(PageExtraction.page_number.asc())
        .all()
    )

    results = []
    for p in pages:
        has_img = bool(p.image_stored_path and os.path.exists(p.image_stored_path))
        results.append(
            PageExtractionResponse(
                id=p.id,
                document_id=p.document_id,
                page_number=p.page_number,
                page_classification=p.page_classification,
                extraction_method=p.extraction_method,
                ocr_text=p.ocr_text,
                ocr_confidence=p.ocr_confidence,
                gemini_text=p.gemini_text,
                final_text=p.final_text,
                human_corrected_text=p.human_corrected_text,
                verification_status=p.verification_status,
                unclear_count=p.unclear_count,
                has_unclear_markers=p.unclear_count > 0,
                image_available=has_img,
                gemini_fallback_used=p.gemini_fallback_used,
                gemini_error=p.gemini_error,
                human_verified_at=p.human_verified_at,
                created_at=p.created_at,
            )
        )
    return results


@router.get("/{document_id}/pages/{page_num}/image")
def get_page_image(document_id: str, page_num: int, db: Session = Depends(get_db)):
    """
    Retrieve rendered PNG image for human review of a specific page.
    """
    page = (
        db.query(PageExtraction)
        .filter(PageExtraction.document_id == document_id, PageExtraction.page_number == page_num)
        .first()
    )
    if not page or not page.image_stored_path or not os.path.exists(page.image_stored_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rendered image for document '{document_id}' page {page_num} not found.",
        )

    return FileResponse(page.image_stored_path, media_type="image/png")


@router.post("/{document_id}/pages/{page_num}/verify", response_model=PageExtractionResponse)
def verify_page_extraction(
    document_id: str,
    page_num: int,
    payload: VerifyRequest,
    db: Session = Depends(get_db),
):
    """
    Save human correction for a page and mark verification status as 'verified'.
    Original gemini_text and ocr_text are strictly preserved and never overwritten.
    """
    page = (
        db.query(PageExtraction)
        .filter(PageExtraction.document_id == document_id, PageExtraction.page_number == page_num)
        .first()
    )
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Page {page_num} of document '{document_id}' not found.",
        )

    page.human_corrected_text = payload.human_corrected_text
    page.final_text = payload.human_corrected_text
    page.verification_status = "verified"
    page.human_verified_at = datetime.now(timezone.utc)

    # Re-assemble document combined raw text with verified page updates
    all_pages = (
        db.query(PageExtraction)
        .filter(PageExtraction.document_id == document_id)
        .order_by(PageExtraction.page_number.asc())
        .all()
    )

    combined_blocks = []
    total_chars = 0
    for p in all_pages:
        txt = p.final_text or ""
        total_chars += len(txt)
        combined_blocks.append(f"--- [PAGE {p.page_number}] ---\n{txt}\n")

    doc = db.query(Document).filter(Document.id == document_id).first()
    if doc:
        doc.raw_text = "\n".join(combined_blocks).strip()
        doc.character_count = total_chars

    db.commit()
    db.refresh(page)

    has_img = bool(page.image_stored_path and os.path.exists(page.image_stored_path))
    return PageExtractionResponse(
        id=page.id,
        document_id=page.document_id,
        page_number=page.page_number,
        page_classification=page.page_classification,
        extraction_method=page.extraction_method,
        ocr_text=page.ocr_text,
        ocr_confidence=page.ocr_confidence,
        gemini_text=page.gemini_text,
        final_text=page.final_text,
        human_corrected_text=page.human_corrected_text,
        verification_status=page.verification_status,
        unclear_count=page.unclear_count,
        has_unclear_markers=page.unclear_count > 0,
        image_available=has_img,
        gemini_fallback_used=page.gemini_fallback_used,
        gemini_error=page.gemini_error,
        human_verified_at=page.human_verified_at,
        created_at=page.created_at,
    )


@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
def delete_document(document_id: str, db: Session = Depends(get_db)):
    """
    Delete a document and all associated structured records via cascading foreign keys.
    Also securely removes the physical document file and rendered page images from disk.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found."
        )

    # 1. Safely delete stored original file
    if doc.stored_path:
        try:
            path_obj = Path(doc.stored_path)
            if path_obj.exists() and path_obj.is_file():
                path_obj.unlink()
        except Exception:
            pass

    # 2. Safely delete preprocessed rendered page images directory
    page_img_dir = Path("data/page_images") / document_id
    if page_img_dir.exists():
        try:
            shutil.rmtree(page_img_dir, ignore_errors=True)
        except Exception:
            pass

    filename = doc.filename
    db.delete(doc)
    db.commit()

    return {
        "success": True,
        "message": f"Document '{filename}' ({document_id}) and all associated clinical entities were permanently deleted."
    }
