from enum import StrEnum

__all__ = (
    "Provider",
    "PROVIDER_URLS",
    "DEFAULT_PROVIDER_TIMEOUT",
    "LOG_LEVELS",
)


class Provider(StrEnum):
    """Available LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    DEEPSEEK = "deepseek"
    CUSTOM = "custom"


# Mapping of provider to their base URLs
PROVIDER_URLS: dict[Provider, str] = {
    Provider.OPENAI: "https://api.openai.com/v1",
    Provider.ANTHROPIC: "https://api.anthropic.com/v1",
    Provider.GOOGLE: "https://generativelanguage.googleapis.com/v1",
    Provider.DEEPSEEK: "https://api.deepseek.com/v1",
    Provider.CUSTOM: "https://custom-provider/v1",
}
DEFAULT_PROVIDER_TIMEOUT = 30
LOG_LEVELS = "DEBUG|INFO|WARNING|ERROR|CRITICAL"
