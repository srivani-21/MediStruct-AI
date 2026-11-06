import os
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings

client = TestClient(app)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

MANDATORY_TITLE = (
    "MediStruct AI: A Smart Healthcare Dataset Generation and Clinical "
    "Knowledge Discovery Framework from Unstructured Medical Documents"
)


def test_mandatory_project_title():
    """Verify exact mandatory title is preserved."""
    assert settings.PROJECT_TITLE == MANDATORY_TITLE
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["project"] == MANDATORY_TITLE
    assert data["app_name"] == "MediStruct AI"


def test_health_check_endpoint():
    """Verify health check returns expected status and environment fields."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "environment" in data
    assert "tesseract_path" in data["environment"]
    assert "gemini_model" in data["environment"]


def test_directory_structure_exists():
    """Verify all required folders exist."""
    required_dirs = [
        PROJECT_ROOT / "backend",
        PROJECT_ROOT / "backend" / "models",
        PROJECT_ROOT / "backend" / "routers",
        PROJECT_ROOT / "backend" / "services",
        PROJECT_ROOT / "backend" / "utils",
        PROJECT_ROOT / "frontend",
        PROJECT_ROOT / "frontend" / "src",
        PROJECT_ROOT / "data",
        PROJECT_ROOT / "data" / "uploads",
        PROJECT_ROOT / "data" / "database",
        PROJECT_ROOT / "data" / "exports",
        PROJECT_ROOT / "chroma_storage",
        PROJECT_ROOT / "tests",
    ]
    for d in required_dirs:
        assert d.exists(), f"Directory missing: {d}"
        assert d.is_dir(), f"Path is not a directory: {d}"


def test_critical_files_exist():
    """Verify critical setup files exist."""
    critical_files = [
        PROJECT_ROOT / ".gitignore",
        PROJECT_ROOT / ".env.example",
        PROJECT_ROOT / "packages.txt",
        PROJECT_ROOT / "requirements.txt",
        PROJECT_ROOT / "backend" / "requirements.txt",
        PROJECT_ROOT / "backend" / "main.py",
        PROJECT_ROOT / "backend" / "config.py",
        PROJECT_ROOT / "frontend" / "package.json",
        PROJECT_ROOT / "frontend" / "vite.config.js",
        PROJECT_ROOT / "frontend" / "tailwind.config.js",
        PROJECT_ROOT / "frontend" / "src" / "App.jsx",
        PROJECT_ROOT / "frontend" / "src" / "pages" / "Overview.jsx",
        PROJECT_ROOT / "frontend" / "src" / "pages" / "DocumentIngestion.jsx",
        PROJECT_ROOT / "frontend" / "src" / "pages" / "StructuredRecords.jsx",
        PROJECT_ROOT / "frontend" / "src" / "pages" / "ClinicalDiscovery.jsx",
        PROJECT_ROOT / "frontend" / "src" / "pages" / "DatasetExport.jsx",
        PROJECT_ROOT / "frontend" / "src" / "pages" / "ClinicalRAG.jsx",
    ]
    for f in critical_files:
        assert f.exists(), f"File missing: {f}"


def test_frontend_six_modules_configured():
    """Verify all six primary modules exist in App.jsx and page components."""
    app_jsx = (PROJECT_ROOT / "frontend" / "src" / "App.jsx").read_text(encoding="utf-8")
    assert "Overview" in app_jsx
    assert "Document Ingestion" in app_jsx
    assert "Structured Records" in app_jsx
    assert "Clinical Discovery" in app_jsx
    assert "Dataset Export" in app_jsx
    assert "Clinical RAG" in app_jsx
    assert "BrowserRouter" in app_jsx
    assert "Routes" in app_jsx
    assert "NavLink" in app_jsx


def test_gitignore_ignores_secrets_and_data():
    """Verify .gitignore properly excludes .env and data files."""
    gitignore_path = PROJECT_ROOT / ".gitignore"
    content = gitignore_path.read_text(encoding="utf-8")
    assert ".env" in content
    assert "venv/" in content
    assert "node_modules/" in content
    assert "data/database/*.db" in content
