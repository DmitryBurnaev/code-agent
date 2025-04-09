import logging.config

import uvicorn
from fastapi import FastAPI, Depends

from app.settings import get_settings, AppSettings
from app.routers import system_router
from app.dependencies.auth import verify_api_token

logger = logging.getLogger("app.main")


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

    app = CodeAgentAPI(
        title="System Info API",
        description="API for retrieving system information",
        docs_url="/api/docs/" if settings.docs_enabled else None,
        redoc_url="/api/redoc/" if settings.docs_enabled else None,
        dependencies=[Depends(verify_api_token)],
    )
    app.set_settings(settings)
    app.include_router(system_router, prefix="/api")
    logger.debug("Application configured")
    return app


if __name__ == "__main__":
    app = make_app()
    uvicorn.run(
        app,
        host=app.settings.app_host,
        port=app.settings.app_port,
        log_config=app.settings.log_config,
    )
