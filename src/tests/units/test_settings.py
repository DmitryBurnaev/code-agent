"""Tests for settings."""

import os
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from src.settings import AppSettings, get_settings
from src.models import LLMProvider
from src.constants import Vendor, LOG_LEVELS


class TestAppSettings:
    """Tests for AppSettings class."""

    @patch.dict(os.environ, {"PROVIDERS": "[]"})
    def test_default_settings(self) -> None:
        """Test default settings values."""
        settings = AppSettings(
            auth_api_token=SecretStr("test-token"),
            http_proxy_url=None,
            provider_custom_url=None,
        )
        assert settings.docs_enabled is False
        assert settings.auth_api_token.get_secret_value() == "test-token"
        assert settings.providers == []

    @pytest.mark.parametrize("log_level", LOG_LEVELS.split("|"))
    def test_valid_log_levels(self, log_level: str) -> None:
        """Test valid log levels."""
        settings = AppSettings(
            auth_api_token=SecretStr("test-token"),
            log_level=log_level,
            http_proxy_url=None,
            provider_custom_url=None,
        )
        assert settings.log_level == log_level.upper()

    def test_invalid_log_level(self) -> None:
        """Test invalid log level."""
        with pytest.raises(ValueError):
            AppSettings(
                auth_api_token=SecretStr("test-token"),
                log_level="INVALID",
                http_proxy_url=None,
                provider_custom_url=None,
            )

    def test_providers(self) -> None:
        """Test providers configuration."""
        providers = [
            LLMProvider(vendor=Vendor.OPENAI, api_key=SecretStr("openai-key")),
            LLMProvider(vendor=Vendor.ANTHROPIC, api_key=SecretStr("anthropic-key")),
        ]
        settings = AppSettings(
            auth_api_token=SecretStr("test-token"),
            providers=providers,
            http_proxy_url=None,
            provider_custom_url=None,
        )
        assert settings.providers == providers
        assert settings.provider_by_vendor == {
            Vendor.OPENAI: providers[0],
            Vendor.ANTHROPIC: providers[1],
        }

    def test_log_config(self) -> None:
        """Test log configuration."""
        settings = AppSettings(
            auth_api_token=SecretStr("test-token"),
            log_level="DEBUG",
            http_proxy_url=None,
            provider_custom_url=None,
        )
        log_config = settings.log_config
        assert log_config["version"] == 1
        assert "standard" in log_config["formatters"]
        assert "console" in log_config["handlers"]
        assert all(
            logger in log_config["loggers"]
            for logger in ["src", "fastapi", "uvicorn.access", "uvicorn.error"]
        )
        assert all(
            log_config["loggers"][logger]["level"] == "DEBUG"
            for logger in ["src", "fastapi", "uvicorn.access", "uvicorn.error"]
        )


class TestGetSettings:
    """Tests for get_settings function."""

    @patch.dict(
        os.environ,
        {
            "AUTH_API_TOKEN": "test-token",
            "LOG_LEVEL": "DEBUG",
            "APP_HOST": "localhost",
            "APP_PORT": "8080",
            "HTTP_PROXY_URL": "socks5://127.0.0.1:8080",
            "PROVIDERS": '[{"vendor":"openai","api_key":"openai-key"}]',
        },
    )
    def test_get_settings_from_env(self) -> None:
        """Test getting settings from environment variables."""
        get_settings.cache_clear()
        settings = get_settings()
        assert settings.auth_api_token.get_secret_value() == "test-token"
        assert settings.log_level == "DEBUG"
        assert settings.app_host == "localhost"
        assert settings.app_port == 8080
        assert settings.http_proxy_url == "socks5://127.0.0.1:8080"
        assert settings.providers == [
            LLMProvider(vendor=Vendor.OPENAI, api_key=SecretStr("openai-key")),
        ]

    @patch.dict(os.environ, {"AUTH_API_TOKEN": "test-token", "LOG_LEVEL": "INVALID"})
    def test_get_settings_validation_error(self) -> None:
        """Test validation error when getting settings."""
        get_settings.cache_clear()
        with pytest.raises(Exception):
            get_settings()

    @patch.dict(os.environ, {"AUTH_API_TOKEN": "test-token"})
    def test_get_settings_caching(self) -> None:
        """Test settings caching."""
        get_settings.cache_clear()
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2  # Same object due to caching
