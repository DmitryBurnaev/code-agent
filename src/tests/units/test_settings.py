"""Tests for settings."""

import os
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from src.settings import AppSettings, get_app_settings
from src.constants import LOG_LEVELS


class TestAppSettings:
    """Tests for AppSettings class."""

    @patch.dict(os.environ, {"API_TOKEN": "test-token"})
    def test_default_settings(self) -> None:
        """Test default settings values."""
        get_app_settings.cache_clear()
        settings = AppSettings(_env_file=None)  # type: ignore
        assert settings.docs_enabled is False
        assert settings.api_token.get_secret_value() == "test-token"

    @pytest.mark.parametrize("log_level", LOG_LEVELS.split("|"))
    def test_valid_log_levels(self, log_level: str) -> None:
        """Test valid log levels."""
        settings = AppSettings(
            api_token=SecretStr("test-token"),
            log_level=log_level,
            http_proxy_url=None,
            vendor_custom_url=None,
        )
        assert settings.log_level == log_level.upper()

    def test_invalid_log_level(self) -> None:
        """Test invalid log level."""
        with pytest.raises(ValueError):
            AppSettings(
                api_token=SecretStr("test-token"),
                log_level="INVALID",
                http_proxy_url=None,
                vendor_custom_url=None,
            )

    def test_log_config(self) -> None:
        """Test log configuration."""
        settings = AppSettings(
            api_token=SecretStr("test-token"),
            log_level="DEBUG",
            http_proxy_url=None,
            vendor_custom_url=None,
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
    """Tests for get_app_settings function."""

    @patch.dict(
        os.environ,
        {
            "API_TOKEN": "test-token",
            "LOG_LEVEL": "DEBUG",
            "APP_HOST": "localhost",
            "APP_PORT": "8080",
            "HTTP_PROXY_URL": "socks5://127.0.0.1:8080",
        },
    )
    def test_get_app_settings_from_env(self) -> None:
        """Test getting settings from environment variables."""
        get_app_settings.cache_clear()
        settings = get_app_settings()
        assert settings.api_token.get_secret_value() == "test-token"
        assert settings.log_level == "DEBUG"
        assert settings.app_host == "localhost"
        assert settings.app_port == 8080
        assert settings.http_proxy_url == "socks5://127.0.0.1:8080"

    @patch.dict(os.environ, {"AUTH_API_TOKEN": "test-token", "LOG_LEVEL": "INVALID"})
    def test_get_app_settings_validation_error(self) -> None:
        """Test validation error when getting settings."""
        get_app_settings.cache_clear()
        with pytest.raises(Exception):
            get_app_settings()

    @patch.dict(os.environ, {"API_TOKEN": "test-token"})
    def test_get_app_settings_caching(self) -> None:
        """Test settings caching."""
        get_app_settings.cache_clear()
        settings1 = get_app_settings()
        settings2 = get_app_settings()
        assert settings1 is settings2  # Same object due to caching
