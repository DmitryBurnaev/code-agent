import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.settings.utils import prepare_settings
from src.settings.log import LogSettings

__all__ = (
    "get_app_settings",
    "AppSettings",
)

APP_DIR = Path(__file__).parent.parent


def get_default_app_version() -> str:
    """Derive a display version from the deployment image when available."""
    image = os.getenv("DOCKER_IMAGE")
    if image is None:
        return "develop"

    image_name = image.rsplit("/", maxsplit=1)[-1]
    if ":" not in image_name:
        return "latest"

    return image_name.rsplit(":", maxsplit=1)[-1]


class FlagsSettings(BaseSettings):
    """Implements settings which are loaded from environment variables"""

    model_config = SettingsConfigDict(env_prefix="FLAG_")

    offline_mode: bool = False


class AdminSettings(BaseSettings):
    """Implements settings which are loaded from environment variables"""

    model_config = SettingsConfigDict(env_prefix="ADMIN_")

    username: str = Field(default_factory=lambda: "admin", description="Default admin username")
    password: SecretStr = Field(
        default_factory=lambda: SecretStr("code-admin!"),
        description="Default admin password",
    )
    session_expiration_time: int = 2 * 24 * 3600
    base_url: str = "/cadm"
    title: str = "CodeAgent"


class WebSettings(BaseSettings):
    """Settings for the browser-facing Code Agent application."""

    model_config = SettingsConfigDict(env_prefix="WEB_")

    session_cookie_name: str = "code_agent_web_session"
    session_expiration_time: int = 2 * 24 * 3600
    session_https_only: bool = True


class AppSettings(BaseSettings):
    """Application settings which are loaded from environment variables"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_docs_enabled: bool = False
    app_secret_key: SecretStr = Field(description="Application secret key")
    app_host: str = "localhost"
    app_port: int = 8003
    app_version: str = Field(default_factory=get_default_app_version)
    jwt_algorithm: str = "HS256"
    http_proxy_url: str | None = Field(default_factory=lambda: None, description="Socks5 Proxy URL")
    vendor_default_timeout: int = 30
    vendor_default_retries: int = 3
    vendor_encryption_key: SecretStr = Field(description="Secret key for vendor API key encryption")
    admin: AdminSettings = Field(default_factory=AdminSettings)
    web: WebSettings = Field(default_factory=WebSettings)
    flags: FlagsSettings = Field(default_factory=FlagsSettings)
    log: LogSettings = Field(default_factory=LogSettings)


@lru_cache
def get_app_settings() -> AppSettings:
    """Prepares application settings from environment variables"""
    return prepare_settings(AppSettings)


SettingsDep = Annotated[AppSettings, Depends(get_app_settings)]
