import datetime
import logging
from typing import TypeVar, Callable, ParamSpec, Any, TYPE_CHECKING

import markupsafe
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from src.exceptions import BaseApplicationError
from src.models import ErrorResponse

if TYPE_CHECKING:
    from src.db.models import BaseModel

__all__ = ("singleton", "universal_exception_handler")
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


async def universal_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Universal exception handler that handles all types of exceptions"""

    log_data: dict[str, str] = {
        "error": "Internal server error",
        "detail": str(exc),
        "path": request.url.path,
        "method": request.method,
    }
    log_level = logging.ERROR
    status_code: int = 500

    if isinstance(exc, BaseApplicationError):
        log_level = exc.log_level
        log_message = f"{exc.log_message}: {exc.message}"
        status_code = exc.status_code
        log_data |= {"error": exc.log_message, "detail": str(exc.message)}

    elif isinstance(exc, (RequestValidationError, ValidationError)):
        log_level = logging.WARNING
        log_message = f"Validation error: {str(exc)}"
        status_code = 422
        log_data |= {"error": log_message}

    else:
        log_message = f"Internal server error: {exc}"

    exc_info = exc if logger.isEnabledFor(logging.DEBUG) else None
    # Log the error
    logger.log(log_level, log_message, extra=log_data, exc_info=exc_info)

    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse.model_validate(log_data).model_dump(),
    )


def utcnow(skip_tz: bool = True) -> datetime.datetime:
    """Just a simple wrapper for deprecated datetime.utcnow"""
    dt = datetime.datetime.now(datetime.UTC)
    if skip_tz:
        dt = dt.replace(tzinfo=None)
    return dt


def decohints(decorator: Callable[..., Any]) -> Callable[..., Any]:
    """
    Small helper which helps to say IDE: "decorated method has the same params and return types"
    """
    return decorator


def admin_get_link(instance: "BaseModel", url_name: str | None = None) -> str:
    """
    Simple helper function to generate a link to an instance
    (required for building items in admin's list view)

    :param instance: Some model's instance for link's building
    :param url_name: Part of url (admin path)
    :return: HTML-safe tag with a generated link
    """
    name = url_name or instance.__class__.__name__.lower()
    return markupsafe.Markup(
        f'<a href="/admin/{name}/edit/{instance.id}">[#{instance.id}] {instance}</a>'
    )


def simple_slugify(value: str) -> str:
    """
    Simple helper function to generate a slugified version of a string
    """
    return value.lower().strip().replace(" ", "-")
