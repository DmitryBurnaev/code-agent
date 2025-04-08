import logging.config

import uvicorn
from fastapi import FastAPI, Depends

from app.settings import get_settings, AppSettings
from app.routers import system_router
from app.dependencies.auth import verify_api_token

logger = logging.getLogger("app.main")


def make_app(settings: AppSettings | None = None) -> FastAPI:
    """Forming Application instance with required settings and dependencies"""

    if settings is None:
        settings = get_settings()

    logging.config.dictConfig(settings.log_config)
    logging.captureWarnings(capture=True)

    app = FastAPI(
        title="System Info API",
        description="API for retrieving system information",
        docs_url="/api/docs/" if settings.docs_enabled else None,
        redoc_url="/api/redoc/" if settings.docs_enabled else None,
        dependencies=[Depends(verify_api_token)],
    )
    # Store settings in app state
    app.state.settings = settings
    app.include_router(system_router, prefix="/api")
    logger.debug("Application configured")
    return app


app = make_app()


if __name__ == "__main__":
    app_settings: AppSettings = app.state.settings
    uvicorn.run(
        app,
        host=app_settings.app_host,
        port=app_settings.app_port,
        log_config=app_settings.log_config,
    )
