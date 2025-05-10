import logging.config

import uvicorn
from fastapi import FastAPI, Depends

from src.settings import get_settings, AppSettings
from src.routers import system_router, proxy_router
from src.dependencies.auth import verify_api_token
from src.utils import setup_exception_handlers

logger = logging.getLogger("src.main")


class CodeAgentAPI(FastAPI):
    """Some extra fields above FastAPI Application"""

    _settings: AppSettings

    def set_settings(self, settings: AppSettings) -> None:
        self._settings = settings

    @property
    def settings(self) -> AppSettings:
        return self._settings


def make_app(settings: AppSettings | None = None) -> CodeAgentAPI:
    """Forming Application instance with required settings and dependencies"""

    if settings is None:
        settings = get_settings()

    logging.config.dictConfig(settings.log_config)
    logging.captureWarnings(capture=True)

    logger.debug("Setting up application...")
    app = CodeAgentAPI(
        title="System Info API",
        description="API for retrieving system information",
        docs_url="/api/docs/" if settings.docs_enabled else None,
        redoc_url="/api/redoc/" if settings.docs_enabled else None,
        dependencies=[Depends(verify_api_token)],
    )
    app.set_settings(settings)

    logger.debug("Setting up routers...")
    app.include_router(system_router, prefix="/api")
    app.include_router(proxy_router, prefix="/api")

    logger.debug("Setting up exception handlers...")
    setup_exception_handlers(app)

    logger.info("Application configured")
    return app


def run_app() -> None:
    """Prepares App and run uvicorn instance"""
    app = make_app()
    uvicorn.run(
        app,
        host=app.settings.app_host,
        port=app.settings.app_port,
        log_config=app.settings.log_config,
    )


if __name__ == "__main__":
    run_app()
