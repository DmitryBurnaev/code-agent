from typing import Annotated

from fastapi import Depends

from src.settings import AppSettings, get_app_settings
from src.modules.auth.tokens import verify_api_token

__all__ = (
    "SettingsDep",
    "verify_api_token",
)


def _app_settings() -> AppSettings:
    """Simple access to settings from controllers"""
    return get_app_settings()


SettingsDep = Annotated[AppSettings, Depends(_app_settings)]
