import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.config import Settings, BASE_DIR
from backend.main import app

client = TestClient(app)


def test_effective_gemini_api_key_resolution_and_sanitization():
    """Verify key resolution, quote stripping, alias support, and safe length checks."""
    # 1. Direct setting with quotes
    s1 = Settings(GEMINI_API_KEY='"AIzaSyTestKeyDirectQuotes"')
    assert s1.effective_gemini_api_key == "AIzaSyTestKeyDirectQuotes"
    assert s1.is_gemini_configured is True

    # 2. Single quotes
    s2 = Settings(GEMINI_API_KEY="'AIzaSyTestKeySingleQuotes'")
    assert s2.effective_gemini_api_key == "AIzaSyTestKeySingleQuotes"
    assert s2.is_gemini_configured is True

    # 3. Google API Key alias
    s3 = Settings(GEMINI_API_KEY="", GOOGLE_API_KEY="AIzaSyGoogleAliasKey")
    assert s3.effective_gemini_api_key == "AIzaSyGoogleAliasKey"
    assert s3.is_gemini_configured is True

    # 4. Empty or short keys (< 6 chars) treated as unconfigured
    with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": "", "GOOGLE_GENAI_API_KEY": ""}):
        with patch("dotenv.dotenv_values", return_value={}):
            s4 = Settings(GEMINI_API_KEY="   ", GOOGLE_API_KEY="")
            assert s4.effective_gemini_api_key == ""
            assert s4.is_gemini_configured is False


def test_health_check_does_not_expose_key():
    """Verify /api/health and /api/health/diagnostics report boolean status and never secrets."""
    mock_tags = MagicMock()
    mock_tags.status_code = 200
    mock_tags.json.return_value = {"models": [{"name": "qwen3.5:2b", "capabilities": ["vision"]}]}

    with patch("httpx.get", return_value=mock_tags):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "environment" in data
        assert "gemini_api_key_set" in data["environment"]
        assert isinstance(data["environment"]["gemini_api_key_set"], bool)
        # Ensure no secret key appears anywhere in the serialized response text
        for key in ("AIzaSy", "GEMINI_API_KEY="):
            assert key not in response.text

        diag_resp = client.get("/api/health/diagnostics")
        assert diag_resp.status_code == 200
        diag_data = diag_resp.json()
        assert "env_file_exists" in diag_data
        assert "gemini_configured" in diag_data
        assert "gemini_model" in diag_data
        assert isinstance(diag_data["gemini_configured"], bool)
        assert isinstance(diag_data["env_file_exists"], bool)
