"""Application type shared by the composition root and admin views."""

from typing import Any, Callable

from fastapi import FastAPI

from src.settings import AppSettings


class CodeAgentAPP(FastAPI):
    """FastAPI application with validated settings."""

    _settings: AppSettings
    dependency_overrides: dict[Any, Callable[[], Any]]

    def set_settings(self, settings: AppSettings) -> None:
        self._settings = settings

    @property
    def settings(self) -> AppSettings:
        return self._settings
