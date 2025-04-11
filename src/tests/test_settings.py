import pytest
from pydantic import SecretStr

from src.exceptions import AppSettingsError
from src.settings import LLMProvider, get_settings


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that settings have correct default values."""
    get_settings.cache_clear()
    monkeypatch.setenv("AUTH_API_TOKEN", "test_token")
    monkeypatch.setenv("PROVIDERS", '[{"api_provider": "test", "api_key": "key"}]')
    monkeypatch.setenv("APP_HOST", "0.0.0.0")
    monkeypatch.setenv("LOG_LEVEL", "debug")

    settings = get_settings()
    assert settings.docs_enabled is True
    assert settings.app_host == "0.0.0.0"
    assert settings.app_port == 8003
    assert settings.log_level == "DEBUG"
    assert settings.providers == [
        LLMProvider(api_provider="test", api_key=SecretStr("key")),
    ]


def test_settings__invalid_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that invalid log level raises validation error."""
    get_settings.cache_clear()
    monkeypatch.setenv("LOG_LEVEL", "fake-log-level")
    with pytest.raises(AppSettingsError) as exc_info:
        get_settings()

    error_message = exc_info.value.args[0]
    assert "[log_level] String should match pattern" in error_message


def test_settings__invalid_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that invalid providers format raises validation error."""
    get_settings.cache_clear()
    monkeypatch.setenv("PROVIDERS", "invalid-json")
    with pytest.raises(AppSettingsError) as exc_info:
        get_settings()

    error_message = exc_info.value.args[0]
    assert 'error parsing value for field "providers"' in error_message


def test_llm_provider_model() -> None:
    """Test LLMProvider model validation."""
    provider = LLMProvider(api_provider="test", api_key=SecretStr("key"))
    assert provider.api_provider == "test"
    assert provider.api_key.get_secret_value() == "key"
