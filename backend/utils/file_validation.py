import os
import re
import uuid
from pathlib import Path
from fastapi import HTTPException, UploadFile
from backend.config import settings

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}


def sanitize_filename(filename: str) -> str:
    """Strip dangerous characters to make a safe storage filename."""
    name = Path(filename).name
    # Keep alphanumeric, underscores, hyphens, and dots
    safe_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name)
    return safe_name or f"document_{uuid.uuid4().hex[:8]}.pdf"


def validate_document_file(file: UploadFile) -> None:
    """
    Validate that uploaded file is an accepted medical document (PDF, JPG, JPEG, PNG)
    and does not exceed configured size limits.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is missing or empty.")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid file format: '{file.filename}'. "
                f"MediStruct AI requires PDF documents (.pdf) or image files (.jpg, .jpeg, .png)."
            ),
        )

    # Check file size if available directly in headers
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if file.size and file.size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File '{file.filename}' exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB.",
        )


# Backward-compatible alias
validate_pdf_file = validate_document_file


def generate_document_id() -> str:
    """Generate a clean, collision-free document identifier."""
    return f"doc_{uuid.uuid4().hex}"


def generate_page_extraction_id() -> str:
    """Generate a clean, collision-free page extraction identifier."""
    return f"pe_{uuid.uuid4().hex}"
