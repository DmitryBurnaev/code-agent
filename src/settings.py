import logging
from functools import lru_cache, cached_property
from typing import Annotated, Any

from pydantic import SecretStr, StringConstraints, Field
from pydantic_core import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.models import LLMProvider
from src.exceptions import AppSettingsError
from src.constants import LOG_LEVELS

__all__ = (
    "get_settings",
    "AppSettings",
)
LogLevelString = Annotated[str, StringConstraints(to_upper=True, pattern=rf"^(?i:{LOG_LEVELS})$")]


class AppSettings(BaseSettings):
    """Application settings which are loaded from environment variables"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    docs_enabled: bool = False
    auth_api_token: SecretStr = Field(description="API token")
    providers: list[LLMProvider] = Field(default_factory=list, description="List of LLM providers")
    app_host: str = "0.0.0.0"
    app_port: int = 8003
    log_level: LogLevelString = "INFO"
    models_cache_ttl: float = 300.0  # Cache TTL in seconds, default 5 minutes
    chat_completion_id_ttl: float = 3600 * 24 * 30
    http_proxy_url: str | None = Field(None, description="Socks5 URL to use")
    provider_default_timeout: int = 30
    provider_default_retries: int = 3
    provider_custom_url: str | None = Field(None, description="Custom provider URL")

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


@lru_cache
def get_settings() -> AppSettings:
    """Prepares settings from environment variables"""
    try:
        app_settings: AppSettings = AppSettings()  # type: ignore
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

    return app_settings
