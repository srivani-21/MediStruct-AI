import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DATABASE_DIR = DATA_DIR / "database"
EXPORT_DIR = DATA_DIR / "exports"
PAGE_IMAGE_DIR = DATA_DIR / "page_images"
CHROMA_DIR = BASE_DIR / "chroma_storage"

# Ensure runtime directories exist
for directory in [UPLOAD_DIR, DATABASE_DIR, EXPORT_DIR, PAGE_IMAGE_DIR, CHROMA_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Explicitly load .env from project root into os.environ
load_dotenv(BASE_DIR / ".env", override=False)


class Settings(BaseSettings):
    # Mandatory Project Title
    PROJECT_TITLE: str = (
        "MediStruct AI: A Smart Healthcare Dataset Generation and Clinical "
        "Knowledge Discovery Framework from Unstructured Medical Documents"
    )
    APP_NAME: str = "MediStruct AI"
    VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Gemini API Configuration (supports standard GEMINI_API_KEY and GOOGLE_API_KEY aliases)
    GEMINI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.8-flash"

    # Ollama Local AI Provider Configuration
    # Set LLM_PROVIDER=ollama (default) or LLM_PROVIDER=gemini in .env.
    # Changing this value requires a backend restart to take effect reliably,
    # although the effective_provider property also does a live .env re-read
    # so provider switching is reflected without restart in most cases.
    LLM_PROVIDER: str = "ollama"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3.5:2b"
    # Timeout in seconds for Ollama inference requests.
    # Cold-start (first request after model is loaded) may take 60-120 s on CPU.
    OLLAMA_TIMEOUT_SECONDS: float = 180.0
    OLLAMA_MAX_RETRIES: int = 2

    # Database and Storage
    DATABASE_URL: str = f"sqlite:///{DATABASE_DIR / 'medistruct.db'}"
    CHROMA_PERSIST_DIRECTORY: str = str(CHROMA_DIR)
    UPLOAD_DIRECTORY: str = str(UPLOAD_DIR)
    EXPORT_DIRECTORY: str = str(EXPORT_DIR)
    EXPORT_SECRET_SALT: str = "medistruct_clinical_dataset_salt_2026"
    MAX_UPLOAD_SIZE_MB: int = 50

    # OCR Paths (Windows default paths supported)
    TESSERACT_CMD: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    POPPLER_PATH: str = ""

    # RAG Settings
    RAG_CHUNK_SIZE: int = 500
    RAG_CHUNK_OVERLAP: int = 50
    RAG_TOP_K: int = 4

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def effective_provider(self) -> str:
        """
        Dynamically resolves the active LLM provider from Settings, os.environ,
        or live .env file so that toggling LLM_PROVIDER in .env is reflected
        without a full process restart in most cases.
        Valid values: "ollama" (default), "gemini".
        """
        # 1. Direct setting
        val = self.LLM_PROVIDER.strip().lower()
        if val in ("ollama", "gemini"):
            return val
        # 2. os.environ
        env_val = os.environ.get("LLM_PROVIDER", "").strip().lower()
        if env_val in ("ollama", "gemini"):
            return env_val
        # 3. Live .env re-read
        env_path = BASE_DIR / ".env"
        if env_path.exists():
            try:
                from dotenv import dotenv_values
                live_val = (dotenv_values(str(env_path)).get("LLM_PROVIDER") or "").strip().lower()
                if live_val in ("ollama", "gemini"):
                    return live_val
            except Exception:
                pass
        return "ollama"  # safe default

    @property
    def effective_ollama_base_url(self) -> str:
        """Dynamically resolve Ollama base URL from settings or live .env."""
        url = self.OLLAMA_BASE_URL.strip()
        if url:
            return url
        env_path = BASE_DIR / ".env"
        if env_path.exists():
            try:
                from dotenv import dotenv_values
                live = (dotenv_values(str(env_path)).get("OLLAMA_BASE_URL") or "").strip()
                if live:
                    return live
            except Exception:
                pass
        return "http://localhost:11434"

    @property
    def effective_ollama_model(self) -> str:
        """Dynamically resolve Ollama model name from settings or live .env."""
        m = self.OLLAMA_MODEL.strip()
        if m:
            return m
        env_path = BASE_DIR / ".env"
        if env_path.exists():
            try:
                from dotenv import dotenv_values
                live = (dotenv_values(str(env_path)).get("OLLAMA_MODEL") or "").strip()
                if live:
                    return live
            except Exception:
                pass
        return "qwen3.5:2b"

    @property
    def effective_gemini_api_key(self) -> str:
        """
        Safely resolves Gemini API key from Settings, os.environ, or live .env.
        Supports GEMINI_API_KEY and GOOGLE_API_KEY aliases.
        Strips surrounding quotes and whitespace.
        Never logs or exposes the value.
        """
        # 1. Direct setting from GEMINI_API_KEY
        if self.GEMINI_API_KEY and len(self.GEMINI_API_KEY.strip()) > 5:
            return self._sanitize_key(self.GEMINI_API_KEY)

        # 2. Direct setting from GOOGLE_API_KEY
        if self.GOOGLE_API_KEY and len(self.GOOGLE_API_KEY.strip()) > 5:
            return self._sanitize_key(self.GOOGLE_API_KEY)

        # 3. Check os.environ for runtime additions
        for var_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_API_KEY"):
            val = os.environ.get(var_name, "").strip()
            if val and len(val) > 5:
                return self._sanitize_key(val)

        # 4. Dynamic on-the-fly re-read of .env in case user updated file while server was running
        env_path = BASE_DIR / ".env"
        if env_path.exists():
            try:
                from dotenv import dotenv_values
                vals = dotenv_values(str(env_path))
                for var_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_API_KEY"):
                    val = (vals.get(var_name) or "").strip()
                    if val and len(val) > 5:
                        return self._sanitize_key(val)
            except Exception:
                pass

        return ""

    @property
    def is_gemini_configured(self) -> bool:
        """Safe boolean diagnostic indicating configuration readiness without exposing key."""
        return bool(self.effective_gemini_api_key)

    @staticmethod
    def _sanitize_key(key: str) -> str:
        """Strip surrounding single/double quotes and whitespace."""
        cleaned = key.strip()
        if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
            cleaned = cleaned[1:-1].strip()
        return cleaned

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
