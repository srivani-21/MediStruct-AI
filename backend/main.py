import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.config import settings, BASE_DIR
from backend.database import init_db, SessionLocal
from backend.models.document import Document
from backend.models.patient import Patient
from backend.models.clinical_records import (
    Symptom,
    Diagnosis,
    Medication,
    LabResult,
    Recommendation,
)
from backend.models.page_extraction import PageExtraction
from backend.routers import (
    documents_router,
    records_router,
    analytics_router,
    export_router,
    rag_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan managing database table verification and resources."""
    # Initialize SQLite database schema safely without dropping existing data
    init_db()
    yield


app = FastAPI(
    title=settings.PROJECT_TITLE,
    description=(
        "Backend REST API for MediStruct AI: A Smart Healthcare Dataset "
        "Generation and Clinical Knowledge Discovery Framework from Unstructured Medical Documents."
    ),
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(documents_router)
app.include_router(records_router)
app.include_router(analytics_router)
app.include_router(export_router)
app.include_router(rag_router)


@app.get("/", tags=["Root"])
def root():
    """Project metadata endpoint with complete academic title."""
    return {
        "project": settings.PROJECT_TITLE,
        "app_name": settings.APP_NAME,
        "version": settings.VERSION,
        "status": "online",
        "documentation": "/docs",
        "disclaimer": (
            "Academic Research and Clinical Knowledge Discovery Prototype. "
            "Extracted insights and AI-generated responses are for informational "
            "purposes only and do not constitute verified medical advice."
        ),
    }


@app.get("/api/health", tags=["Health"])
def health_check():
    """System health check and dependency availability report."""
    tesseract_available = os.path.exists(settings.TESSERACT_CMD)
    poppler_configured = bool(settings.POPPLER_PATH and os.path.exists(settings.POPPLER_PATH))
    gemini_configured = settings.is_gemini_configured

    # Check database connectivity
    db_status = "error"
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_status = "connected"
    except Exception as exc:
        db_status = f"error: {str(exc)}"

    # Check Ollama health (fast probe, no inference)
    from backend.services.ollama_service import OllamaService
    ollama_health = OllamaService().check_health()

    return {
        "status": "healthy",
        "version": settings.VERSION,
        "database": db_status,
        "database_url": settings.DATABASE_URL.split("///")[-1],
        "environment": {
            "active_provider": settings.effective_provider,
            "tesseract_path": settings.TESSERACT_CMD,
            "tesseract_detected": tesseract_available,
            "poppler_path": settings.POPPLER_PATH,
            "poppler_configured": poppler_configured,
            "ollama": {
                "base_url": settings.effective_ollama_base_url,
                "model": settings.effective_ollama_model,
                "server_online": ollama_health["server_online"],
                "model_available": ollama_health["model_available"],
                "capabilities": ollama_health.get("model_capabilities", []),
            },
            "gemini_api_key_set": gemini_configured,
            "gemini_model": settings.GEMINI_MODEL,
        },
    }


@app.get("/api/health/diagnostics", tags=["Health"])
def health_diagnostics():
    """Safe configuration diagnostics reporting readiness without exposing sensitive secrets."""
    env_path = BASE_DIR / ".env"
    db_connected = False
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_connected = True
    except Exception:
        db_connected = False

    from backend.services.ollama_service import OllamaService
    ollama_health = OllamaService().check_health()

    return {
        "env_file_exists": env_path.exists(),
        "active_provider": settings.effective_provider,
        "gemini_configured": settings.is_gemini_configured,
        "gemini_model": settings.GEMINI_MODEL,
        "ollama": {
            "configured": ollama_health["server_online"] and ollama_health["model_available"],
            "server_online": ollama_health["server_online"],
            "model_available": ollama_health["model_available"],
            "base_url": settings.effective_ollama_base_url,
            "model": settings.effective_ollama_model,
            "capabilities": ollama_health.get("model_capabilities", []),
            "error": ollama_health.get("error"),
        },
        "gemini": {
            "configured": settings.is_gemini_configured,
            "model": settings.GEMINI_MODEL,
        },
        "tesseract_detected": os.path.exists(settings.TESSERACT_CMD),
        "database_connected": db_connected,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
