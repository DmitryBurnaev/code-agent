import datetime
import logging
from typing import TypeVar, Callable, ParamSpec, Any, TYPE_CHECKING, Literal

import markupsafe
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException

from src.models import ErrorResponse
from src.settings import get_app_settings
from src.exceptions import BaseApplicationError
from src.db.diagnostics import failure_details

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
        "detail": "An internal error has been detected. We apologize for the inconvenience.",
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

    elif isinstance(exc, HTTPException):
        log_level = logging.WARNING
        status_code = exc.status_code
        log_message = "Auth problem" if status_code == 401 else "Some http-related error"
        log_message = f"{log_message}: {exc.detail}"
        log_data |= {"error": log_message}

    else:
        log_message = "Internal server error"
        log_data |= {
            "detail": "An internal error has been detected. We apologize for the inconvenience."
        }

    logger.log(
        log_level,
        "[%s %s] %s; failure=%s",
        request.method,
        request.url.path,
        log_message,
        failure_details(exc),
        extra=log_data,
    )

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


def admin_get_link(
    instance: "BaseModel",
    url_name: str | None = None,
    target: Literal["edit", "details"] = "edit",
) -> str:
    """
    Simple helper function to generate a link to an instance
    (required for building items in admin's list view)

    :param instance: Some model's instance for link's building
    :param url_name: Part of url (admin path)
    :param target: Link target (edit / link)
    :return: HTML-safe tag with a generated link
    """
    settings = get_app_settings()
    base_url = settings.admin.base_url
    name = url_name or instance.__class__.__name__.lower()
    return markupsafe.Markup('<a href="{}/{}/{}/{}">[#{}] {}</a>').format(
        base_url, name, target, instance.id, instance.id, str(instance)
    )


def simple_slugify(value: str) -> str:
    """
    Simple helper function to generate a slugified version of a string
    """
    return value.lower().strip().replace(" ", "-")


def cut_string(value: str, max_length: int = 128, placeholder: str = "...") -> str:
    """
    Simple helper function to cut a string with placeholder

    :param value: String to cut
    :param max_length: Maximum length of the string
    :param placeholder: Placeholder to add if the string is cut
    :return: Cut string

    >>> cut_string("Hello, world!")
    'Hello, world!'

    >>> cut_string("Hello, world!", max_length=5)
    'Hello...'

    >>> cut_string("Hello, world!", max_length=5, placeholder="")
    'Hello'

    """
    if not value:
        return value

    return value[:max_length] + placeholder if len(value) > max_length else value
