import logging.config

import uvicorn
from fastapi import FastAPI

from app.settings import app_settings
from app.routers import system_router

logger = logging.getLogger("app.main")


def make_app() -> FastAPI:
    logging.config.dictConfig(app_settings.log_config)
    logging.captureWarnings(capture=True)
    app = FastAPI(
        title="System Info API",
        description="API for retrieving system information",
        docs_url="/api/docs/" if app_settings.docs_enabled else None,
        redoc_url="/api/redoc/" if app_settings.docs_enabled else None,
    )
    app.include_router(system_router, prefix="/api")
    logger.debug("App configured")
    return app


app = make_app()


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=app_settings.app_host,
        port=app_settings.app_port,
        log_config=app_settings.log_config,
    )
