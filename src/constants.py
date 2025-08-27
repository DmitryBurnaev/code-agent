from enum import StrEnum
from pathlib import Path
from typing import Self

__all__ = (
    "VendorSlug",
    "VENDOR_URLS",
    "VENDOR_DEFAULT_TIMEOUT",
    "LOG_LEVELS",
)


class StingEnum(StrEnum):
    @classmethod
    def from_string(cls, value: str) -> Self:
        return cls[value.upper()]


class VendorSlug(StingEnum):
    """Preset of LLM vendors."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    DEEPSEEK = "deepseek"
    CUSTOM = "custom"
    LOCAL = "local"


class VendorAuthType(StingEnum):
    BEARER = "Bearer"


# Mapping of vendors to their base URLs
VENDOR_URLS: dict[str, str] = {
    VendorSlug.OPENAI: "https://api.openai.com/v1",
    VendorSlug.ANTHROPIC: "https://api.anthropic.com/v1",
    VendorSlug.GOOGLE: "https://generativelanguage.googleapis.com/v1",
    VendorSlug.DEEPSEEK: "https://api.deepseek.com/v1",
    VendorSlug.CUSTOM: "https://custom.vendor.com/v1",
    VendorSlug.LOCAL: "http://localhost:1234/v1",
}
VENDOR_DEFAULT_TIMEOUT = 30
LOG_LEVELS = "DEBUG|INFO|WARNING|ERROR|CRITICAL"
APP_DIR = Path(__file__).parent
RENDER_KW = {"class": "form-control"}
RENDER_KW_REQ = RENDER_KW | {"required": True}
VENDOR_ID_SEPARATOR = ":"
