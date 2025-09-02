from functools import lru_cache
import logging
from typing import Annotated

from pydantic import StringConstraints
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.settings.utils import prepare_settings

LOG_LEVELS_PATTERN = "DEBUG|INFO|WARNING|ERROR|CRITICAL"
LogLevelString = Annotated[
    str, StringConstraints(to_upper=True, pattern=rf"^(?i:{LOG_LEVELS_PATTERN})$")
]


class LoggingRequestForStaticsFilter(logging.Filter):
    """
    Simple filter for logging records: skip access to static files (like CSS/JS for admin panel)
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter out static access logs"""
        return "statics" not in record.getMessage().lower()


class LogSettings(BaseSettings):
    """Implements settings which are loaded from environment variables"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="LOG_")

    level: LogLevelString = "INFO"
    skip_static_access: bool = False
    format: str = "[%(asctime)s] %(levelname)s [%(filename)s:%(lineno)s] %(message)s"
    datefmt: str = "%d.%m.%Y %H:%M:%S"

    @property
    def log_config(self) -> dict[str, dict[str, str | bool | list[str]]]:
        filters: list[logging.Filter] = []
        if self.skip_static_access:
            filters.append(LoggingRequestForStaticsFilter("skip-static-access"))

        return {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": self.format,
                    "datefmt": self.datefmt,
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "filters": filters,
                }
            },
            "loggers": {
                "src": {"handlers": ["console"], "level": self.level, "propagate": False},
                "fastapi": {"handlers": ["console"], "level": self.level, "propagate": False},
                "uvicorn.access": {
                    "handlers": ["console"],
                    "level": self.level,
                    "propagate": False,
                },
                "uvicorn.error": {"handlers": ["console"], "level": self.level, "propagate": False},
            },
        }


@lru_cache
def get_log_settings() -> LogSettings:
    """Prepares logging settings from environment variables"""
    return prepare_settings(LogSettings)
