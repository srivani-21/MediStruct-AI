from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship
from backend.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Patient(Base):
    """
    Patient table for clinical demographics extracted from medical documents.
    """
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_identifier = Column(String(100), nullable=True, index=True)
    name = Column(String(255), nullable=True)
    age = Column(Integer, nullable=True, index=True)
    gender = Column(String(50), nullable=True, index=True)
    demographic_notes = Column(Text, nullable=True)

    # Association to the originating document
    document_id = Column(
        String(64),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    # Relationships
    document = relationship("Document", back_populates="patient")
    symptoms = relationship("Symptom", back_populates="patient")
    diagnoses = relationship("Diagnosis", back_populates="patient")
    medications = relationship("Medication", back_populates="patient")
    lab_results = relationship("LabResult", back_populates="patient")
    recommendations = relationship("Recommendation", back_populates="patient")

    __table_args__ = (
        Index("idx_patient_doc_identifier", "document_id", "patient_identifier"),
    )
