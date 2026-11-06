from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Text,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship
from backend.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Symptom(Base):
    """
    Symptom table storing clinical symptoms with duration, severity, and page citation.
    """
    __tablename__ = "symptoms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        String(64),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_id = Column(
        Integer,
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    symptom_name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    duration = Column(String(100), nullable=True)
    severity = Column(String(50), nullable=True, index=True)
    page_number = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    # Relationships
    document = relationship("Document", back_populates="symptoms")
    patient = relationship("Patient", back_populates="symptoms")

    __table_args__ = (
        Index("idx_symptom_doc_page", "document_id", "page_number"),
    )


class Diagnosis(Base):
    """
    Diagnosis table storing primary and differential clinical diagnoses.
    """
    __tablename__ = "diagnoses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        String(64),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_id = Column(
        Integer,
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    diagnosis_name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    diagnosis_date = Column(String(100), nullable=True)
    status = Column(String(50), nullable=True)  # e.g., 'Confirmed', 'Provisional', 'History of'
    page_number = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    # Relationships
    document = relationship("Document", back_populates="diagnoses")
    patient = relationship("Patient", back_populates="diagnoses")

    __table_args__ = (
        Index("idx_diagnosis_doc_page", "document_id", "page_number"),
    )


class Medication(Base):
    """
    Medication table storing pharmaceutical prescriptions, dosages, and routes.
    """
    __tablename__ = "medications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        String(64),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_id = Column(
        Integer,
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    medication_name = Column(String(255), nullable=False, index=True)
    dosage = Column(String(100), nullable=True)
    frequency = Column(String(100), nullable=True)
    duration = Column(String(100), nullable=True)
    route = Column(String(50), nullable=True)  # e.g., 'Oral', 'IV', 'Inhalation'
    page_number = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    # Relationships
    document = relationship("Document", back_populates="medications")
    patient = relationship("Patient", back_populates="medications")

    __table_args__ = (
        Index("idx_medication_doc_page", "document_id", "page_number"),
    )


class LabResult(Base):
    """
    LabResult table storing clinical laboratory and diagnostic test findings.
    """
    __tablename__ = "lab_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        String(64),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_id = Column(
        Integer,
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    test_name = Column(String(255), nullable=False, index=True)
    result_value = Column(String(100), nullable=False)
    numeric_value = Column(Float, nullable=True, index=True)  # For numeric analytics in Phase 6
    unit = Column(String(50), nullable=True)
    reference_range = Column(String(100), nullable=True)
    flag = Column(String(30), nullable=True)  # e.g., 'Normal', 'High', 'Low', 'Critical'
    test_date = Column(String(100), nullable=True)
    page_number = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    # Relationships
    document = relationship("Document", back_populates="lab_results")
    patient = relationship("Patient", back_populates="lab_results")

    __table_args__ = (
        Index("idx_lab_doc_test", "document_id", "test_name"),
    )


class Recommendation(Base):
    """
    Recommendation table storing physician follow-ups, advice, and discharge plans.
    """
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        String(64),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_id = Column(
        Integer,
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    recommendation_text = Column(Text, nullable=False)
    follow_up_instructions = Column(Text, nullable=True)
    page_number = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    # Relationships
    document = relationship("Document", back_populates="recommendations")
    patient = relationship("Patient", back_populates="recommendations")

    __table_args__ = (
        Index("idx_recommendation_doc_page", "document_id", "page_number"),
    )
