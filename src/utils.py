import logging
import time
import traceback
from typing import TypeVar, Generic, Callable, ParamSpec, TYPE_CHECKING, cast

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from src.exceptions import BaseApplicationError
from src.models import ErrorResponse

if TYPE_CHECKING:
    from src.main import CodeAgentAPI


logger = logging.getLogger(__name__)
T = TypeVar("T")
C = TypeVar("C")
P = ParamSpec("P")


def singleton(cls: type[C]) -> Callable[P, C]:
    """Class decorator that implements the Singleton pattern.

    This decorator ensures that only one instance of a class exists.
    All later instantiations will return the same instance.
    """
    instances: dict[str, C] = {}

    def getinstance(*args: P.args, **kwargs: P.kwargs) -> C:
        if cls.__name__ not in instances:
            instances[cls.__name__] = cls(*args, **kwargs)

        return instances[cls.__name__]

    return getinstance


class Cache(Generic[T], metaclass=type):
    """Simple in-memory cache with TTL per key."""

    def __init__(self, ttl: float):
        self._ttl = ttl
        self._data: dict[str, T] = {}
        self._last_update: dict[str, float] = {}

    def get(self, key: str) -> T | None:
        """Get cached value for a key if not expired.

        Args:
            key: Cache key to look up

        Returns:
            Cached value if exists and not expired, None otherwise
        """
        if key not in self._data:
            return None

        if time.monotonic() - self._last_update[key] > self._ttl:
            del self._data[key]
            del self._last_update[key]
            return None

        logger.debug("Cache: got value for key %s", key)
        return self._data[key]

    def set(self, key: str, value: T) -> None:
        """Set new cache value for key and update timestamp.

        Args:
            key: Cache key to store value
            value: Value to cache
        """
        self._data[key] = value
        self._last_update[key] = time.monotonic()
        logger.debug("Cache: set value for key %s | value: %s", key, value)

    def invalidate(self, key: str | None = None) -> None:
        """Force cache invalidation.

        Args:
            key: Specific key to invalidate, if None - invalidate all cache
        """
        if key is None:
            self._data.clear()
            self._last_update.clear()
        elif key in self._data:
            del self._data[key]
            del self._last_update[key]


def setup_exception_handlers(app: "CodeAgentAPI") -> None:
    """Setup global exception handlers for the application"""

    @app.exception_handler(Exception)
    async def universal_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Universal exception handler that handles all types of exceptions"""
        # Match exception type and prepare response data
        log_data: dict[str, str | int] = {
            "status_code": 500,
            "error": "Internal server error",
            "path": request.url.path,
            "method": request.method,
        }
        match exc:
            case BaseApplicationError():
                # Our custom application exceptions
                # exc: BaseApplicationError
                log_level = exc.log_level
                log_message = f"{exc.log_message}: {exc.message}"
                log_data |= {
                    "error": repr(exc),
                    "status_code": exc.status_code,
                    "traceback": traceback.format_exc(),
                }

            case RequestValidationError() | ValidationError():
                # FastAPI and Pydantic validation errors
                log_level = logging.WARNING
                log_message = f"Validation error: {str(exc)}"
                log_data |= {
                    "error": log_message,
                    "status_code": 422,
                }

            case _:
                # Unknown exceptions
                log_message = f"Internal server error: {str(exc)}"
                log_level = logging.ERROR
                log_data |= {
                    "error": log_message,
                    "status_code": 500,
                    "traceback": traceback.format_exc(),
                }

        # Log the error
        logger.log(log_level, log_message, extra=log_data)

        return JSONResponse(
            status_code=log_data["status_code"],
            content=ErrorResponse(**log_data).model_dump(),
        )
