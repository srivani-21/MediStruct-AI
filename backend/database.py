import os
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.config import settings

# SQLite connection URL
DATABASE_URL = settings.DATABASE_URL

# Create SQLAlchemy engine with sqlite thread checking disabled for FastAPI async workers
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

# Enforce foreign key constraints and enable Write-Ahead Logging (WAL) for SQLite
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base model class for declarative mapping
Base = declarative_base()


def get_db():
    """FastAPI dependency for managing database sessions per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Safely creates all tables defined in models if they do not exist.
    Will never drop, alter, or delete existing records.
    """
    # Import all models to ensure they are registered with Base metadata
    from backend.models.document import Document
    from backend.models.patient import Patient
    from backend.models.clinical_records import (
        Symptom,
        Diagnosis,
        Medication,
        LabResult,
        Recommendation,
    )
    Base.metadata.create_all(bind=engine)
