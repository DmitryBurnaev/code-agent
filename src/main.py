import logging.config
from typing import Awaitable, Callable

import uvicorn
from fastapi import FastAPI, Depends, Request, Response

from src.settings import get_settings, AppSettings
from src.routers import system_router, proxy_router, proxy_cors_router
from src.dependencies.auth import verify_api_token

logger = logging.getLogger("src.main")


class CodeAgentAPI(FastAPI):
    """Some extra fields above FastAPI Application"""

    _settings: AppSettings

    def set_settings(self, settings: AppSettings) -> None:
        self._settings = settings

    @property
    def settings(self) -> AppSettings:
        return self._settings


class AIAgentMiddleware:
    """Middleware for adding standard headers for AI agent communication"""

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    async def __call__(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """
        Call next middleware in the chain and add standard headers
        Provide standard headers for AI agent communication
        """
        response: Response = await call_next(request)

        # Add CORS headers
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Max-Age"] = "86400"

        return response


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
    )
    app.set_settings(settings)

    # Add AI Agent middleware
    app.add_middleware(AIAgentMiddleware)

    logger.debug("Setting up routers...")
    app.include_router(system_router, prefix="/api", dependencies=[Depends(verify_api_token)])
    app.include_router(proxy_router, prefix="/api", dependencies=[Depends(verify_api_token)])
    app.include_router(proxy_cors_router, prefix="/api")

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
