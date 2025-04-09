import logging
import sys
from typing import Annotated
from functools import lru_cache

from pydantic import SecretStr, BaseModel, StringConstraints, Field
from pydantic_core import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["get_settings", "AppSettings"]

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
    def log_config(self) -> dict:
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
                "app": {"handlers": ["console"], "level": self.log_level, "propagate": False},
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
        app_settings: AppSettings = AppSettings()
    except ValidationError as exc:
        logging.error(
            "Unable to prepare settings (caught Validation Error): \n %s",
            exc.errors(include_url=False, include_input=False),
        )
        sys.exit(1)

    return app_settings
