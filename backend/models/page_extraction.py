from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from backend.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class PageExtraction(Base):
    """
    Page-level extraction details for medical documents.
    Preserves original OCR, Gemini multimodal transcriptions, human corrections,
    unclear marker counts, and verification lifecycle states.
    """
    __tablename__ = "page_extractions"

    id = Column(String(64), primary_key=True, index=True)
    document_id = Column(String(64), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)

    # Classification: 'digital', 'printed_ocr', 'handwritten', 'uncertain'
    page_classification = Column(String(50), nullable=False, default="unknown")
    # Method: 'pdfplumber', 'tesseract_ocr', 'gemini_vision', 'gemini_vision_fallback_tesseract'
    extraction_method = Column(String(50), nullable=False, default="pending")

    # Raw layers
    ocr_text = Column(Text, nullable=True)
    ocr_confidence = Column(Float, nullable=True)
    gemini_text = Column(Text, nullable=True)

    # Final combined / corrected text
    final_text = Column(Text, nullable=True)
    human_corrected_text = Column(Text, nullable=True)

    # Verification lifecycle: 'pending', 'verified', 'needs_review', 'skipped'
    verification_status = Column(String(30), nullable=False, default="pending", index=True)
    unclear_count = Column(Integer, nullable=False, default=0)

    # Rendered page image for human verification display
    image_stored_path = Column(String(500), nullable=True)

    # Fallback tracking
    gemini_fallback_used = Column(Boolean, nullable=False, default=False)
    gemini_error = Column(Text, nullable=True)

    # Timestamps
    human_verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    # Relationship back to parent Document
    document = relationship("Document", back_populates="page_extractions")

    __table_args__ = (
        UniqueConstraint("document_id", "page_number", name="uq_doc_page"),
        Index("idx_page_doc_num", "document_id", "page_number"),
    )
