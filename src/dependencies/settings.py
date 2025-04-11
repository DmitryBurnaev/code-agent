from typing import Annotated

from fastapi import Depends

from src.settings import AppSettings, get_settings


__all__ = ["SettingsDep"]


def get_app_settings() -> AppSettings:
    """Simple access to settings from controllers"""
    return get_settings()


SettingsDep = Annotated[AppSettings, Depends(get_app_settings)]
