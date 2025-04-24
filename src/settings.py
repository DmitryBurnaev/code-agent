import logging
from functools import lru_cache
from enum import StrEnum
from typing import Annotated, Any, Optional, List

from pydantic import SecretStr, BaseModel, StringConstraints, Field
from pydantic_core import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["get_settings", "AppSettings", "Provider"]

from src.exceptions import AppSettingsError


class Provider(StrEnum):
    """Available LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    DEEPSEEK = "deepseek"


# Mapping of provider to their base URLs
PROVIDER_URLS: dict[Provider, str] = {
    Provider.OPENAI: "https://api.openai.com/v1",
    Provider.ANTHROPIC: "https://api.anthropic.com/v1",
    Provider.GOOGLE: "https://generativelanguage.googleapis.com/v1",
    Provider.DEEPSEEK: "https://api.deepseek.com/v1",
}

DEFAULT_PROVIDER_TIMEOUT = 30
LOG_LEVELS = "DEBUG|INFO|WARNING|ERROR|CRITICAL"
LogLevelString = Annotated[str, StringConstraints(to_upper=True, pattern=rf"^(?i:{LOG_LEVELS})$")]


class LLMProvider(BaseModel):
    """Provider configuration with API key."""

    vendor: Provider
    api_key: SecretStr
    auth_type: str = "Bearer"
    timeout: int = DEFAULT_PROVIDER_TIMEOUT

    @property
    def base_url(self) -> str:
        """Get base URL for provider."""
        return PROVIDER_URLS[self.vendor]

    def __repr__(self) -> str:
        return f"LLMProvider(vendor={self.vendor}, api_key={self.api_key})"

    def __str__(self) -> str:
        return f"Provider {self.vendor}"


class ProxyRoute(BaseModel):
    """Proxy route configuration."""

    source_path: str = Field(..., description="Source path to match")
    target_url: str = Field(..., description="Target URL to proxy to")
    timeout: float = Field(DEFAULT_PROVIDER_TIMEOUT, description="Request timeout in seconds")
    auth_token: Optional[SecretStr] = Field(
        None, description="Authorization token for target service"
    )
    auth_type: str = Field("Bearer", description="Authorization type (Bearer, Basic, etc)")

    @classmethod
    def from_provider(cls, provider: LLMProvider) -> "ProxyRoute":
        """Create proxy route from provider configuration."""
        return cls(
            source_path=f"/proxy/{provider.vendor}",
            target_url=provider.base_url,
            strip_path=True,
            auth_token=provider.api_key,
            auth_type="Bearer",  # Most providers use Bearer auth
        )


class AppSettings(BaseSettings):
    """Application settings which are loaded from environment variables"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    docs_enabled: bool = True
    auth_api_token: SecretStr = Field(description="API token")
    providers: list[LLMProvider] = Field(default_factory=list, description="List of LLM providers")
    app_host: str = "0.0.0.0"
    app_port: int = 8003
    log_level: LogLevelString = "INFO"
    proxy_routes: List[ProxyRoute]
    models_cache_ttl: float = 300.0  # Cache TTL in seconds, default 5 minutes

    @property
    def proxy_routes(self) -> list[ProxyRoute]:
        """Generate proxy routes from providers."""
        return [ProxyRoute.from_provider(provider) for provider in self.providers]

    @property
    def proxy_by_provider_name(self) -> dict[str, ProxyRoute]:
        """
        Generate proxy info with provider's name linking
        (just mapping: provider-name -> ProxyRoute())
        """
        return {provider.name: ProxyRoute.from_provider(provider) for provider in self.providers}

    # @property
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
            error_message += f"\n\t[{'|'.join(map(str, error['loc']))}] {error['msg']}"

        raise AppSettingsError(error_message) from exc

    except Exception as exc:
        logging.error("Unable to prepare settings (caught unexpected): \n %r", exc)
        raise AppSettingsError(f"Unable to prepare settings: {exc}") from exc

    return app_settings
