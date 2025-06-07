from typing import Annotated

from fastapi import Depends

from src.settings import AppSettings, get_app_settings


__all__ = ["SettingsDep"]


def _app_settings() -> AppSettings:
    """Simple access to settings from controllers"""
    return get_app_settings()


SettingsDep = Annotated[AppSettings, Depends(_app_settings)]
