import logging
from functools import lru_cache, cached_property
from typing import Annotated, Any, TypeVar

from pydantic import SecretStr, StringConstraints, Field
from pydantic_core import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.models import LLMProvider
from src.exceptions import AppSettingsError
from src.constants import LOG_LEVELS

__all__ = (
    "get_app_settings",
    "AppSettings",
)

LogLevelString = Annotated[str, StringConstraints(to_upper=True, pattern=rf"^(?i:{LOG_LEVELS})$")]
TypeSettings = TypeVar("TypeSettings", bound=BaseSettings)


class AppSettings(BaseSettings):
    """Application settings which are loaded from environment variables"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    docs_enabled: bool = False
    api_token: SecretStr = Field(description="API token")
    secret_key: SecretStr = Field(description="Secret key", alias="APP_SECRET_KEY")
    providers: list[LLMProvider] = Field(default_factory=list, description="List of LLM providers")
    app_host: str = "0.0.0.0"
    app_port: int = 8003
    log_level: LogLevelString = "INFO"
    http_proxy_url: str | None = Field(default_factory=lambda: None, description="Socks5 Proxy URL")
    provider_default_timeout: int = 30
    provider_default_retries: int = 3
    provider_custom_url: str | None = Field(
        default_factory=lambda: None, description="API URL for 'custom' vendor"
    )
    admin_username: str = Field(
        default_factory=lambda: "admin", description="Default admin username"
    )
    admin_password: SecretStr = Field(description="Default admin password")
    offline_test_mode: bool = False

    @cached_property
    def provider_by_vendor(self) -> dict[str, LLMProvider]:
        return {provider.vendor: provider for provider in self.providers}

    @property
    def log_config(self) -> dict[str, Any]:
        level = self.log_level
        return {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "[%(asctime)s] %(levelname)s [%(filename)s:%(lineno)s] %(message)s",
                    "datefmt": "%d.%m.%Y %H:%M:%S",
                },
            },
            "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "standard"}},
            "loggers": {
                "src": {"handlers": ["console"], "level": level, "propagate": False},
                "fastapi": {"handlers": ["console"], "level": level, "propagate": False},
                "uvicorn.access": {"handlers": ["console"], "level": level, "propagate": False},
                "uvicorn.error": {"handlers": ["console"], "level": level, "propagate": False},
            },
        }


class DBSettings(BaseSettings):
    """Implements settings which are loaded from environment variables"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="DB_")

    driver: str = "postgresql+asyncpg"
    host: str = "localhost"
    port: int = 5432
    username: str = "postgres"
    password: str = "postgres"
    database: str = "code_agent"
    pool_min_size: int | None = Field(default_factory=lambda: None, description="Pool Min Size")
    pool_max_size: int | None = Field(default_factory=lambda: None, description="Pool Max Size")
    echo: bool = False

    @cached_property
    def database_dsn(self) -> str:
        return f"{self.driver}://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


def _get_settings(settings_class: type[TypeSettings]) -> TypeSettings:
    """Prepares settings from environment variables"""
    try:
        settings: TypeSettings = settings_class()
    except ValidationError as exc:
        message = str(exc.errors(include_url=False, include_input=False))
        logging.debug("Unable to validate settings (caught Validation Error): \n %s", message)
        error_message = "Unable to validate settings: "
        for error in exc.errors():
            error_message += f"\n\t[{'|'.join(map(str, error['loc']))}] {error['msg']}"
        raise AppSettingsError(error_message) from exc

    except Exception as exc:
        logging.error("Unable to prepare settings (caught unexpected): \n %r", exc)
        raise AppSettingsError(f"Unable to prepare settings: {exc}") from exc

    return settings


@lru_cache
def get_app_settings() -> AppSettings:
    """Prepares application settings from environment variables"""
    return _get_settings(AppSettings)


@lru_cache
def get_db_settings() -> DBSettings:
    """Prepares database settings from environment variables"""
    return _get_settings(DBSettings)
