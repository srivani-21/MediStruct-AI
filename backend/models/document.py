from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    Text,
    DateTime,
    Index,
)
from sqlalchemy.orm import relationship
from backend.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Document(Base):
    """
    Document table storing metadata, raw extraction text, processing status,
    and document classification (digital, scanned, handwritten, or mixed).
    """
    __tablename__ = "documents"

    id = Column(String(64), primary_key=True, index=True)
    filename = Column(String(255), nullable=False, index=True)
    stored_path = Column(String(500), nullable=False)
    file_size_bytes = Column(Integer, nullable=False, default=0)
    page_count = Column(Integer, nullable=False, default=0)

    # Document type & handwriting metadata architecture
    # Supported classifications: 'digital', 'scanned_printed', 'handwritten', 'mixed', 'unknown'
    document_type = Column(String(50), nullable=False, default="unknown", index=True)
    handwriting_detected = Column(Boolean, nullable=False, default=False)
    extraction_method = Column(String(50), nullable=False, default="pending")
    raw_text = Column(Text, nullable=True)
    character_count = Column(Integer, nullable=False, default=0)

    # Processing state
    # States: 'PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'
    processing_status = Column(String(30), nullable=False, default="PENDING", index=True)
    error_message = Column(Text, nullable=True)

    # Timestamps
    uploaded_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    processed_at = Column(DateTime, nullable=True)

    # Cascade relationships to structured clinical entities
    patient = relationship("Patient", back_populates="document", uselist=False, cascade="all, delete-orphan")
    symptoms = relationship("Symptom", back_populates="document", cascade="all, delete-orphan")
    diagnoses = relationship("Diagnosis", back_populates="document", cascade="all, delete-orphan")
    medications = relationship("Medication", back_populates="document", cascade="all, delete-orphan")
    lab_results = relationship("LabResult", back_populates="document", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="document", cascade="all, delete-orphan")
    page_extractions = relationship("PageExtraction", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_doc_status_uploaded", "processing_status", "uploaded_at"),
    )
