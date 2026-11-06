import os
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, timezone
from PIL import Image
from sqlalchemy.orm import Session

from backend.models.document import Document
from backend.models.page_extraction import PageExtraction
from backend.services.pdf_extractor import DigitalPDFExtractor, DIGITAL_TEXT_THRESHOLD_CHARS
from backend.services.ocr_extractor import OCRExtractor
from backend.services.handwriting_evaluator import HandwritingEvaluator
from backend.services.handwriting_service import HandwritingService
from backend.utils.file_validation import generate_page_extraction_id


class DocumentProcessor:
    """
    Unified extraction engine coordinating:
    - Digital PDF parsing via pdfplumber/pypdf
    - Scanned printed document OCR via Tesseract and PDFium
    - Medical handwriting recognition via Google GenAI (Gemini 3.8 Flash)
    - 4-class page classification (digital, printed_ocr, handwritten, uncertain)
    - Human-verification lifecycle tracking in page_extractions
    - Isolated page image rendering for side-by-side verification preview
    """

    def __init__(self):
        self.digital_extractor = DigitalPDFExtractor()
        self.ocr_extractor = OCRExtractor()
        self.handwriting_evaluator = HandwritingEvaluator()
        self.handwriting_service = HandwritingService()

    def process_document(
        self,
        document_id: str,
        db: Session,
        force_ocr: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes text extraction, scanned OCR, and handwriting recognition for a document.
        Persists page-level extractions and updates parent document metadata.
        """
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError(f"Document with ID '{document_id}' not found in database.")

        file_path = doc.stored_path
        if not os.path.exists(file_path):
            doc.processing_status = "FAILED"
            doc.error_message = f"Physical file missing on server: {file_path}"
            db.commit()
            raise FileNotFoundError(doc.error_message)

        # Mark document as PROCESSING
        doc.processing_status = "PROCESSING"
        doc.error_message = None
        db.commit()

        try:
            ext = Path(file_path).suffix.lower()
            is_image_file = ext in (".jpg", ".jpeg", ".png")

            # Dedicated directory for rendered page images
            page_image_dir = Path("data/page_images") / doc.id
            page_image_dir.mkdir(parents=True, exist_ok=True)

            page_results: List[Dict[str, Any]] = []
            digital_page_count = 0
            ocr_page_count = 0
            handwriting_found = False

            if is_image_file:
                # -------------------------------------------------------------
                # Single-page Image Upload (.jpg, .jpeg, .png)
                # -------------------------------------------------------------
                total_pages = 1
                page_img = Image.open(file_path)
                img_dest = page_image_dir / "page_1.png"
                page_img.save(str(img_dest), "PNG")

                ocr_res = self.ocr_extractor.extract_text_from_image(page_img)
                ocr_text = ocr_res["text"]
                ocr_conf = ocr_res["confidence"]
                ocr_page_count += 1

                cls_res = self.handwriting_evaluator.classify_page(
                    filename=doc.filename,
                    ocr_confidence=ocr_conf,
                    extracted_text=ocr_text,
                    char_count=len(ocr_text),
                    is_digital=False,
                )

                if cls_res["classification"] in ("handwritten", "uncertain"):
                    handwriting_found = True
                    hw_res = self.handwriting_service.recognize_page(
                        page_img, tesseract_fallback_text=ocr_text
                    )
                    final_text = hw_res["text"] if hw_res["text"] else ocr_text
                    gemini_text = hw_res["text"] if not hw_res["fallback_used"] else None
                    method = hw_res["recognition_method"]
                    verif_status = "needs_review" if hw_res["fallback_used"] else "pending"
                    unclear_count = hw_res["unclear_count"]
                    fb_used = hw_res["fallback_used"]
                    gemini_err = hw_res["error"]
                else:
                    final_text = ocr_text
                    gemini_text = None
                    method = "tesseract_ocr"
                    verif_status = "verified"
                    unclear_count = 0
                    fb_used = False
                    gemini_err = None

                page_results.append({
                    "page_number": 1,
                    "classification": cls_res["classification"],
                    "method": method,
                    "ocr_text": ocr_text,
                    "ocr_confidence": ocr_conf,
                    "gemini_text": gemini_text,
                    "final_text": final_text,
                    "verification_status": verif_status,
                    "unclear_count": unclear_count,
                    "image_stored_path": str(img_dest),
                    "gemini_fallback_used": fb_used,
                    "gemini_error": gemini_err,
                    "char_count": len(final_text),
                    "handwriting": handwriting_found,
                })

            else:
                # -------------------------------------------------------------
                # Standard PDF Document Processing
                # -------------------------------------------------------------
                digital_pages = self.digital_extractor.extract_text_by_pages(file_path)
                total_pages = len(digital_pages)

                if total_pages == 0:
                    raise ValueError("The uploaded PDF document contains 0 pages.")

                for page_info in digital_pages:
                    page_num = page_info["page_number"]
                    is_digital = page_info["is_digital"] and not force_ocr

                    img_dest = page_image_dir / f"page_{page_num}.png"
                    # Try rendering page image for preview
                    try:
                        rendered_img = self.ocr_extractor.render_pdf_page_to_image(file_path, page_num)
                        rendered_img.save(str(img_dest), "PNG")
                    except Exception:
                        rendered_img = None

                    if is_digital:
                        text = page_info["text"]
                        method = "digital_pdfplumber"
                        conf = 100.0
                        cls_name = "digital"
                        verif_status = "verified"
                        digital_page_count += 1
                        gemini_text = None
                        unclear_count = 0
                        fb_used = False
                        gemini_err = None
                        final_text = text
                        ocr_text = None

                    else:
                        ocr_page_count += 1
                        if rendered_img:
                            ocr_res = self.ocr_extractor.extract_text_from_image(rendered_img)
                        else:
                            ocr_res = self.ocr_extractor.ocr_single_page(file_path, page_num)

                        ocr_text = ocr_res["text"]
                        conf = ocr_res["confidence"]

                        cls_res = self.handwriting_evaluator.classify_page(
                            filename=doc.filename,
                            ocr_confidence=conf,
                            extracted_text=ocr_text,
                            char_count=len(ocr_text),
                            is_digital=False,
                        )
                        cls_name = cls_res["classification"]

                        if cls_name in ("handwritten", "uncertain"):
                            handwriting_found = True
                            if rendered_img is not None:
                                hw_res = self.handwriting_service.recognize_page(
                                    rendered_img, tesseract_fallback_text=ocr_text
                                )
                                final_text = hw_res["text"] if hw_res["text"] else ocr_text
                                gemini_text = hw_res["text"] if not hw_res["fallback_used"] else None
                                method = hw_res["recognition_method"]
                                verif_status = "needs_review" if hw_res["fallback_used"] else "pending"
                                unclear_count = hw_res["unclear_count"]
                                fb_used = hw_res["fallback_used"]
                                gemini_err = hw_res["error"]
                            else:
                                final_text = ocr_text
                                gemini_text = None
                                method = "tesseract_ocr"
                                verif_status = "needs_review"
                                unclear_count = 0
                                fb_used = True
                                gemini_err = "Could not render page image for Gemini Vision"
                        else:
                            final_text = ocr_text
                            gemini_text = None
                            method = "force_tesseract_ocr" if force_ocr else "tesseract_ocr"
                            verif_status = "verified"
                            unclear_count = 0
                            fb_used = False
                            gemini_err = None

                    page_results.append({
                        "page_number": page_num,
                        "classification": cls_name,
                        "method": method,
                        "ocr_text": ocr_text,
                        "ocr_confidence": conf if not is_digital else None,
                        "gemini_text": gemini_text,
                        "final_text": final_text,
                        "verification_status": verif_status,
                        "unclear_count": unclear_count,
                        "image_stored_path": str(img_dest) if img_dest.exists() else None,
                        "gemini_fallback_used": fb_used,
                        "gemini_error": gemini_err,
                        "char_count": len(final_text),
                        "handwriting": cls_name in ("handwritten", "uncertain"),
                    })

            # -----------------------------------------------------------------
            # Assemble combined document text with page markers
            # -----------------------------------------------------------------
            combined_text_blocks = []
            total_chars = 0
            for pr in page_results:
                total_chars += pr["char_count"]
                combined_text_blocks.append(
                    f"--- [PAGE {pr['page_number']}] ---\n{pr['final_text']}\n"
                )

            final_raw_text = "\n".join(combined_text_blocks).strip()

            # Strict Check: Never label a zero-character document as successfully extracted
            if total_chars == 0:
                raise ValueError(
                    "No legible text could be extracted from this document. "
                    "The document appears completely blank, unreadable, or corrupted."
                )

            # Document-level classification
            if handwriting_found:
                doc_type = "handwritten" if ocr_page_count == total_pages or is_image_file else "mixed"
            elif ocr_page_count == total_pages:
                doc_type = "scanned_printed"
            elif digital_page_count == total_pages:
                doc_type = "digital"
            else:
                doc_type = "mixed"

            if force_ocr:
                ext_method = "force_tesseract_ocr"
            elif handwriting_found:
                ext_method = "gemini_multimodal" if not any(p["gemini_fallback_used"] for p in page_results if p["handwriting"]) else "hybrid_gemini_ocr"
            elif ocr_page_count == 0:
                ext_method = "pdfplumber_digital"
            elif digital_page_count == 0:
                ext_method = "tesseract_ocr"
            else:
                ext_method = "hybrid_digital_ocr"

            # -----------------------------------------------------------------
            # Persist PageExtractions into SQLite
            # -----------------------------------------------------------------
            # Remove any previous page extractions for this document
            db.query(PageExtraction).filter(PageExtraction.document_id == doc.id).delete()

            for pr in page_results:
                pe = PageExtraction(
                    id=generate_page_extraction_id(),
                    document_id=doc.id,
                    page_number=pr["page_number"],
                    page_classification=pr["classification"],
                    extraction_method=pr["method"],
                    ocr_text=pr["ocr_text"],
                    ocr_confidence=pr["ocr_confidence"],
                    gemini_text=pr["gemini_text"],
                    final_text=pr["final_text"],
                    human_corrected_text=None,
                    verification_status=pr["verification_status"],
                    unclear_count=pr["unclear_count"],
                    image_stored_path=pr["image_stored_path"],
                    gemini_fallback_used=pr["gemini_fallback_used"],
                    gemini_error=pr["gemini_error"],
                    human_verified_at=None,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(pe)

            # Update Document record
            doc.page_count = total_pages
            doc.raw_text = final_raw_text
            doc.character_count = total_chars
            doc.document_type = doc_type
            doc.handwriting_detected = handwriting_found
            doc.extraction_method = ext_method
            doc.processing_status = "COMPLETED"
            doc.processed_at = datetime.now(timezone.utc)
            doc.error_message = None

            db.commit()
            db.refresh(doc)

            return {
                "success": True,
                "document_id": doc.id,
                "filename": doc.filename,
                "page_count": total_pages,
                "character_count": total_chars,
                "document_type": doc_type,
                "handwriting_detected": handwriting_found,
                "extraction_method": ext_method,
                "processing_status": "COMPLETED",
                "preview": final_raw_text[:500] + ("..." if len(final_raw_text) > 500 else ""),
            }

        except Exception as exc:
            db.rollback()
            doc.processing_status = "FAILED"
            doc.error_message = str(exc)
            db.commit()
            raise RuntimeError(f"Document processing failed: {str(exc)}")
