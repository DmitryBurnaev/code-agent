import logging.config
import sys

import uvicorn
from fastapi import FastAPI, Depends

from src.modules.admin.app import make_admin
from src.exceptions import AppSettingsError
from src.settings import get_app_settings, AppSettings
from src.api import system_router, proxy_router
from src.dependencies import verify_api_token

logger = logging.getLogger("src.main")


class CodeAgentAPP(FastAPI):
    """Some extra fields above FastAPI Application"""

    _settings: AppSettings

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

    logger.debug("Setting up application...")
    app = CodeAgentAPP(
        title="Code Agent API",
        description="API for retrieving system information",
        docs_url="/api/docs/" if settings.docs_enabled else None,
        redoc_url="/api/redoc/" if settings.docs_enabled else None,
    )
    app.set_settings(settings)

    logger.debug("Setting up api...")
    app.include_router(system_router, prefix="/api", dependencies=[Depends(verify_api_token)])
    app.include_router(proxy_router, prefix="/api", dependencies=[Depends(verify_api_token)])

    logger.info("Application configured")
    return app


def run_app() -> None:
    """Prepares App and run uvicorn instance"""
    app = make_app()
    make_admin(app)
    uvicorn.run(
        app,
        host=app.settings.app_host,
        port=app.settings.app_port,
        log_config=app.settings.log_config,
    )


if __name__ == "__main__":
    run_app()
