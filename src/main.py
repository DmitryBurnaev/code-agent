import sys
import logging.config
from contextlib import asynccontextmanager
from typing import Any, Callable, AsyncGenerator

import uvicorn
from fastapi import FastAPI, Depends

from src.modules.auth.dependencies import verify_api_token
from src.modules.admin.app import make_admin
from src.exceptions import AppSettingsError, StartupError
from src.settings import get_app_settings, AppSettings
from src.modules.api import system_router, proxy_router
from src.db.session import initialize_database, close_database

logger = logging.getLogger("src.main")


class CodeAgentAPP(FastAPI):
    """Some extra fields above FastAPI Application"""

    _settings: AppSettings
    dependency_overrides: dict[Any, Callable[[], Any]]

    def set_settings(self, settings: AppSettings) -> None:
        self._settings = settings

    @property
    def settings(self) -> AppSettings:
        return self._settings


@asynccontextmanager
async def lifespan(app: CodeAgentAPP) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown events."""
    logger.info("Starting up application...")
    try:
        await initialize_database()
        logger.info("Application startup completed successfully")
    except Exception as exc:
        raise StartupError("Failed to initialize DB connection") from exc

    logger.info("Setting up admin application...")
    make_admin(app)

    yield

    logger.info("===== shutdown ====")
    logger.info("Shutting down this application...")
    try:
        await close_database()
    except Exception as exc:
        logger.error("Error during application shutdown: %r", exc)
    else:
        logger.info("Application shutdown completed successfully")

    logger.info("=====")


def make_app(settings: AppSettings | None = None) -> CodeAgentAPP:
    """Forming Application instance with required settings and dependencies"""

    if settings is None:
        try:
            settings = get_app_settings()
        except AppSettingsError as exc:
            logger.error("Unable to get settings from environment: %r", exc)
            sys.exit(1)

    logging.config.dictConfig(settings.log.dict_config_any)
    logging.captureWarnings(capture=True)

    logger.info("Setting up application...")
    app = CodeAgentAPP(
        title="Code Agent API",
        description="API for retrieving system information",
        docs_url="/api/docs/" if settings.api_docs_enabled else None,
        redoc_url="/api/redoc/" if settings.api_docs_enabled else None,
        lifespan=lifespan,
    )
    app.set_settings(settings)

    logger.info("Setting up routes...")
    app.include_router(system_router, prefix="/api", dependencies=[Depends(verify_api_token)])
    app.include_router(proxy_router, prefix="/api", dependencies=[Depends(verify_api_token)])

    logger.info("Application configured!")
    return app


if __name__ == "__main__":
    """Prepares App and run uvicorn instance"""
    app: CodeAgentAPP = make_app()
    uvicorn.run(
        app,
        host=app.settings.app_host,
        port=app.settings.app_port,
        log_config=app.settings.log.dict_config_any,
        proxy_headers=True,
    )
