import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError, SecretStr
from pydantic_settings import SettingsError

from app.settings import AppSettings, LLMProvider


def test_settings_defaults() -> None:
    """Test that settings have correct default values."""
    with patch.dict(os.environ, {
        "AUTH_API_TOKEN": "test-token",
        "PROVIDERS": '[{"api_provider": "test", "api_key": "key"}]',
        "APP_HOST": "0.0.0.0",
        "LOG_LEVEL": "debug",
    }):
        settings = AppSettings()
        assert settings.docs_enabled is True
        assert settings.app_host == "0.0.0.0"
        assert settings.app_port == 8003
        assert settings.log_level == "DEBUG"
        assert len(settings.providers) == 1
        assert isinstance(settings.providers[0], LLMProvider)
        assert settings.providers[0].api_provider == "test"
        assert settings.providers[0].api_key.get_secret_value() == "key"



def test_settings_invalid_log_level() -> None:
    """Test that invalid log level raises validation error."""
    with patch.dict(os.environ, {
        "AUTH_API_TOKEN": "test-token",
        "PROVIDERS": "[]",
        "LOG_LEVEL": "INVALID_LEVEL"
    }):
        with pytest.raises(ValidationError) as exc_info:
            AppSettings()
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("log_level",) for error in errors)


def test_settings_invalid_providers() -> None:
    """Test that invalid providers format raises validation error."""
    with patch.dict(os.environ, {
        "AUTH_API_TOKEN": "test-token",
        "PROVIDERS": "invalid-json"
    }):
        with pytest.raises(SettingsError):
            AppSettings()


def test_llm_provider_model() -> None:
    """Test LLMProvider model validation."""
    provider = LLMProvider(api_provider="test", api_key=SecretStr("key"))
    assert provider.api_provider == "test"
    assert provider.api_key.get_secret_value() == "key" 
