from enum import StrEnum


__all__ = (
    "Vendor",
    "PROVIDER_URLS",
    "DEFAULT_PROVIDER_TIMEOUT",
    "LOG_LEVELS",
)

from typing import Self


class StingEnum(StrEnum):
    @classmethod
    def from_string(cls, value: str) -> Self:
        return cls[value.upper()]


class Vendor(StingEnum):
    """Available LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    DEEPSEEK = "deepseek"
    CUSTOM = "custom"
    LOCAL = "local"


# Mapping of provider to their base URLs
PROVIDER_URLS: dict[Vendor, str] = {
    Vendor.OPENAI: "https://api.openai.com/v1",
    Vendor.ANTHROPIC: "https://api.anthropic.com/v1",
    Vendor.GOOGLE: "https://generativelanguage.googleapis.com/v1",
    Vendor.DEEPSEEK: "https://api.deepseek.com/v1",
    Vendor.CUSTOM: "https://custom-provider/v1",
    Vendor.LOCAL: "http://localhost:1234/v1",
}
DEFAULT_PROVIDER_TIMEOUT = 30
LOG_LEVELS = "DEBUG|INFO|WARNING|ERROR|CRITICAL"
