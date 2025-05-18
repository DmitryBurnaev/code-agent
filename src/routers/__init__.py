from .base import ErrorHandlingBaseRoute
from .system import router as system_router
from .proxy import router as proxy_router, cors_router as proxy_cors_router

__all__ = (
    "system_router",
    "proxy_router",
    "proxy_cors_router",
    "ErrorHandlingBaseRoute",
)
