import logging
from functools import lru_cache

from typing import Annotated, Any

from pydantic import SecretStr, BaseModel, StringConstraints, Field
from pydantic_core import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["get_settings", "AppSettings"]

from src.exceptions import AppSettingsError

LOG_LEVELS = "DEBUG|INFO|WARNING|ERROR|CRITICAL"
LogLevelString = Annotated[str, StringConstraints(to_upper=True, pattern=rf"^(?i:{LOG_LEVELS})$")]


class LLMProvider(BaseModel):
    api_provider: str
    api_key: SecretStr


class AppSettings(BaseSettings):
    """Application settings which are loaded from environment variables"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    docs_enabled: bool = True
    auth_api_token: SecretStr = Field(description="API token")
    providers: list[LLMProvider] = Field(default_factory=list, description="List of LLM providers")
    app_host: str = "0.0.0.0"
    app_port: int = 8003
    log_level: LogLevelString = "INFO"

    @property
    def log_config(self) -> dict[str, Any]:
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
                "src": {"handlers": ["console"], "level": self.log_level, "propagate": False},
                "fastapi": {"handlers": ["console"], "level": self.log_level, "propagate": False},
                "uvicorn.access": {
                    "handlers": ["console"],
                    "level": self.log_level,
                    "propagate": False,
                },
                "uvicorn.error": {
                    "handlers": ["console"],
                    "level": self.log_level,
                    "propagate": False,
                },
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
            error_message += f"\n\t[{"|".join(map(str, error['loc']))}] {error['msg']}"

        raise AppSettingsError(error_message) from exc

    except Exception as exc:
        logging.error("Unable to prepare settings (caught unexpected): \n %r", exc)
        raise AppSettingsError(f"Unable to prepare settings: {exc}") from exc

    return app_settings
