"""Tests for settings."""

import os
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from src.settings import AppSettings, get_app_settings
from src.constants import LOG_LEVELS

MINIMAL_ENV_VARS = {
    "SECRET_KEY": "test-key",
    "ADMIN_PASSWORD": "test-password",
    "VENDOR_ENCRYPTION_KEY": "test-encryption-key",
}


class TestAppSettings:
    """Tests for AppSettings class."""

    @patch.dict(os.environ, MINIMAL_ENV_VARS)
    def test_default_settings(self) -> None:
        get_app_settings.cache_clear()
        settings = AppSettings(_env_file=None)  # type: ignore
        assert settings.docs_enabled is False
        assert settings.app_host == "0.0.0.0"
        assert settings.app_port == 8003
        assert settings.secret_key.get_secret_value() == "test-key"
        assert settings.log_level == "INFO"
        assert settings.jwt_algorithm == "HS256"
        assert settings.http_proxy_url is None
        assert settings.vendor_default_timeout == 30
        assert settings.vendor_default_retries == 3
        assert settings.vendor_custom_url is None
        assert settings.admin_username == "admin"
        assert settings.admin_password.get_secret_value() == "test-password"
        assert settings.admin_session_expiration_time == 2 * 24 * 3600
        assert settings.offline_test_mode is False
        assert settings.vendor_encryption_key.get_secret_value() == "test-encryption-key"

    @pytest.mark.parametrize("log_level", LOG_LEVELS.split("|"))
    def test_valid_log_levels(self, log_level: str) -> None:
        settings = AppSettings(
            secret_key=SecretStr("test-token"),
            vendor_encryption_key=SecretStr("test-encryption-key"),
            admin_username="test-username",
            admin_password=SecretStr("test-password"),
            log_level=log_level,
            http_proxy_url=None,
            vendor_custom_url=None,
        )
        assert settings.log_level == log_level.upper()

    def test_invalid_log_level(self) -> None:
        with pytest.raises(ValueError):
            AppSettings(
                admin_username="test-username",
                admin_password=SecretStr("test-password"),
                secret_key=SecretStr("test-secret"),
                vendor_encryption_key=SecretStr("test-encryption-key"),
                log_level="INVALID",
                http_proxy_url=None,
                vendor_custom_url=None,
            )

    def test_log_config(self) -> None:
        """Test log configuration."""
        settings = AppSettings(
            secret_key=SecretStr("test-token"),
            admin_username="test-username",
            admin_password=SecretStr("test-password"),
            vendor_encryption_key=SecretStr("test-encryption-key"),
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
        MINIMAL_ENV_VARS
        | {
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
        assert settings.log_level == "DEBUG"
        assert settings.app_host == "localhost"
        assert settings.app_port == 8080
        assert settings.http_proxy_url == "socks5://127.0.0.1:8080"

    @patch.dict(os.environ, MINIMAL_ENV_VARS | {"LOG_LEVEL": "INVALID"})
    def test_get_app_settings_validation_error(self) -> None:
        """Test validation error when getting settings."""
        get_app_settings.cache_clear()
        with pytest.raises(Exception):
            get_app_settings()

    @patch.dict(os.environ, MINIMAL_ENV_VARS)
    def test_get_app_settings_caching(self) -> None:
        """Test settings caching."""
        get_app_settings.cache_clear()
        settings1 = get_app_settings()
        settings2 = get_app_settings()
        assert settings1 is settings2  # Same object due to caching
