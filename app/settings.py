import logging
import sys
from typing import Annotated

from pydantic import SecretStr, BaseModel, StringConstraints
from pydantic_core import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["app_settings"]

UpperCasedString = Annotated[str, StringConstraints(to_upper=True)]


class LLMProvider(BaseModel):
    api_provider: str
    api_key: SecretStr


class AppSettings(BaseSettings):
    """Application settings which are loaded from environment variables"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    docs_enabled: bool = True
    service_api_key: SecretStr
    service_providers: list[LLMProvider]
    app_host: str = "0.0.0.0"
    app_port: int = 8003
    log_level: UpperCasedString = "INFO"

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


try:
    app_settings: AppSettings = AppSettings()
except ValidationError as exc:
    logging.error(
        "Unable to prepare settings (caught Validation Error): \n %s",
        exc.errors(include_url=False, include_input=False),
    )
    sys.exit(1)
else:
    logging.warning("Settings preparation successful: \n %s", app_settings.model_dump_json())
