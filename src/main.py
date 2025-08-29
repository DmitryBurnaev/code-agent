import logging.config
import sys
from contextlib import asynccontextmanager
from typing import Any, Callable

import uvicorn
from fastapi import FastAPI, Depends

from src.modules.auth.dependencies import verify_api_token
from src.modules.admin.app import make_admin
from src.exceptions import AppSettingsError
from src.settings import get_app_settings, AppSettings
from src.modules.api import system_router, proxy_router
from src.db.session import initialize_database, close_database

logger = logging.getLogger("src.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown events."""
    # Startup: Initialize resources
    logger.info("Starting up application...")
    try:
        await initialize_database()
        logger.info("Application startup completed successfully")
    except Exception as e:
        logger.error("Failed to initialize application: %s", str(e))
        raise

    yield

    # Shutdown: Cleanup resources
    logger.info("Shutting down application...")
    try:
        await close_database()
        logger.info("Application shutdown completed successfully")
    except Exception as e:
        logger.error("Error during application shutdown: %s", str(e))


class CodeAgentAPP(FastAPI):
    """Some extra fields above FastAPI Application"""

    _settings: AppSettings
    dependency_overrides: dict[Any, Callable[[], Any]]

    def set_settings(self, settings: AppSettings) -> None:
        self._settings = settings

    @property
    def settings(self) -> AppSettings:
        return self._settings


def make_app(settings: AppSettings | None = None) -> CodeAgentAPP:
    """Forming Application instance with required settings and dependencies"""

    if settings is None:
        try:
            settings = get_app_settings()
        except AppSettingsError as exc:
            logger.error("Unable to get settings from environment: %r", exc)
            sys.exit(1)

    logging.config.dictConfig(settings.log_config)
    logging.captureWarnings(capture=True)

    logger.info("Setting up application...")
    app = CodeAgentAPP(
        title="Code Agent API",
        description="API for retrieving system information",
        docs_url="/api/docs/" if settings.api_docs_enabled else None,
        redoc_url="/api/redoc/" if settings.api_docs_enabled else None,
        lifespan=lifespan,
    )
    logger.info("Setting up application settings...")
    app.set_settings(settings)

    logger.info("Setting up routes...")
    app.include_router(system_router, prefix="/api", dependencies=[Depends(verify_api_token)])
    app.include_router(proxy_router, prefix="/api", dependencies=[Depends(verify_api_token)])

    logger.info("Setting up admin application...")
    make_admin(app)

    logger.info("Application configured!")
    return app


if __name__ == "__main__":
    """Prepares App and run uvicorn instance"""
    app: CodeAgentAPP = make_app()
    uvicorn.run(
        app,
        host=app.settings.app_host,
        port=app.settings.app_port,
        log_config=app.settings.log_config,
        proxy_headers=True,
    )
