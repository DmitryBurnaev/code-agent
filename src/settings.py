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


class AppSettings(BaseSettings):
    """Application settings which are loaded from environment variables"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    docs_enabled: bool = False
    api_token: SecretStr = Field(description="API token")
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

    # Database settings
    # TODO: replace with separately: pg-host, pg-port, pg-user, pg-pass
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/code_agent",
        description="Database URL",
    )
    database_pool_size: int = Field(default=5, description="Database connection pool size")
    database_max_overflow: int = Field(default=10, description="Database max overflow")
    database_echo: bool = Field(default=False, description="Database echo mode")

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
    """

        Implements
        DATABASE = {
        "driver": "postgresql+asyncpg",
        "host": config("DB_HOST", default=None),
        "port": config("DB_PORT", cast=int, default=None),
        "username": config("DB_USERNAME", default=None),
        "password": config("DB_PASSWORD", cast=Secret, default=None),
        "database": DB_NAME,
        "pool_min_size": config("DB_POOL_MIN_SIZE", cast=int, default=1),
        "pool_max_size": config("DB_POOL_MAX_SIZE", cast=int, default=16),
        "ssl": config("DB_SSL", default=None),
        "use_connection_for_request": config("DB_USE_CONNECTION_FOR_REQUEST", cast=bool, default=True),
        "retry_limit": config("DB_RETRY_LIMIT", cast=int, default=1),
        "retry_interval": config("DB_RETRY_INTERVAL", cast=int, default=1),
    }
    DATABASE_DSN = config(
        "DB_DSN",
        cast=str,
        default="{driver}://{username}:{password}@{host}:{port}/{database}".format(**DATABASE),
    )

    """

    driver: str = "postgresql+asyncpg"
    host: str = Field(None, description="Database Host", env="DB_HOST")
    port: int = Field(default=None, description="Database Port", env="DB_PORT")
    username: str = Field(default=None, description="Database Username", env="DB_USERNAME")
    password: str = Field(default=None, description="Database Password", env="DB_PASSWORD")
    database: str = Field(default=None, description="Database Name", env="DB_NAME")
    pool_min_size: int = Field(
        default=None, description="Database Pool Min Size", env="DB_POOL_MIN_SIZE"
    )
    pool_max_size: int = Field(
        default=None, description="Database Pool Max Size", env="DB_POOL_MAX_SIZE"
    )
    ssl: bool = Field(default=None, description="Database SSL", env="DB_SSL")
    use_connection_for_request: bool = Field(
        default=None,
        description="Database Use Connection For Request",
        env="DB_USE_CONNECTION_FOR_REQUEST",
    )
    retry_limit: int = Field(default=None, description="Database Retry Limit", env="DB_RETRY_LIMIT")
    retry_interval: int = Field(
        default=None, description="Database Retry Interval", env="DB_RETRY_INTERVAL"
    )

    @cached_property
    def database_dsn(self) -> str:
        return f"{self.driver}://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"

    @cached_property
    def alembic_dsn(self) -> str:
        return (
            f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        )


TypeSettings = TypeVar("TypeSettings", bound=BaseSettings)


@lru_cache
def _get_settings(settings_class: type[TypeSettings]) -> TypeSettings:
    """Prepares settings from environment variables"""
    try:
        settings: BaseSettings = settings_class()  # type: ignore
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


def get_app_settings() -> AppSettings:
    """Prepares application settings from environment variables"""
    return _get_settings(AppSettings)


def get_db_settings() -> DBSettings:
    """Prepares database settings from environment variables"""
    return _get_settings(DBSettings)
