import asyncio
import functools
import logging
import time
from typing import (
    TypeVar,
    Generic,
    Dict,
    Optional,
    Callable,
    Awaitable,
    Any,
    ParamSpec,
    cast,
    overload,
)

from src.exceptions import ProviderRequestError

T = TypeVar("T")
logger = logging.getLogger(__name__)


class Cache(Generic[T]):
    """Simple in-memory cache with TTL per key."""

    def __init__(self, ttl: float):
        self._ttl = ttl
        self._data: Dict[str, T] = {}
        self._last_update: Dict[str, float] = {}

    def get(self, key: str) -> Optional[T]:
        """Get cached value for key if not expired.

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

        return self._data[key]

    def set(self, key: str, value: T) -> None:
        """Set new cache value for key and update timestamp.

        Args:
            key: Cache key to store value under
            value: Value to cache
        """
        self._data[key] = value
        self._last_update[key] = time.monotonic()

    def invalidate(self, key: Optional[str] = None) -> None:
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


P = ParamSpec("P")
RT = TypeVar("RT")
R = TypeVar("R", bound=Awaitable[Any])


class ProviderError(Exception):
    """Custom exception raised when all retry attempts fail."""

    pass


def decohints(decorator: Callable[..., Any]) -> Callable[..., Any]:
    """
    Small helper which helps to say IDE: "decorated method has the same params and return types"
    """
    return decorator


@overload
def retry_with_timeout(
    func: Callable[P, Awaitable[T]],
) -> Callable[P, Awaitable[T]]: ...


@overload
def retry_with_timeout(
    *,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]: ...


# @decohints
def retry_with_timeout(
    func: Callable[P, Awaitable[T]] | None = None,
    *,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]] | Callable[P, Awaitable[T]]:
    """
    Decorator that retries an async function with timeout and logs each attempt.

    Args:
        func: Async function to decorate
        max_retries: Maximum number of retry attempts (default: 3)
        retry_delay: Base delay between retries in seconds (default: 1.0)
                    Will be multiplied by attempt number for backoff

    Returns:
        Decorated function that will retry on failure

    Raises:
        ProviderError: If all retry attempts fail
    """

    @decohints
    def decorator(func: Callable[P, Awaitable[RT]]) -> Callable[P, Awaitable[RT]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> RT:
            last_exception: Exception | None = None

            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    delay = retry_delay * attempt
                    logging.warning(
                        f"Attempt {attempt}/{max_retries} failed for {func.__name__}. "
                        f"Retrying in {delay} seconds. Error: {str(e)}"
                    )
                    if attempt < max_retries:
                        await asyncio.sleep(delay)

            raise ProviderError(
                f"All {max_retries} attempts failed for {func.__name__}"
            ) from last_exception

        # return cast(Callable[P, Awaitable[RT]], wrapper)
        return wrapper

    if func is not None:
        return decorator(func)

    return decorator


#
# def retry_with_timeout(
#     max_retries: int = 3, retry_delay: float = 1.0
# ) -> Callable[[...], Callable[[...], Awaitable[Any]]]:
#     """Decorator that retries a function with timeout and logs each attempt.
#
#     Args:
#         max_retries: Maximum number of retry attempts (default: 3)
#         retry_delay: Base delay between retries in seconds (default: 1.0)
#                     Will be multiplied by attempt number for backoff
#
#     Returns:
#         Decorated function that will retry on failure
#
#     Raises:
#         ProviderError: If all retry attempts fail
#     """
#
#     def decorator[RT, **P](func: Callable[P, Awaitable[RT]]) -> Callable[P, Awaitable[RT]]:
#
#         @functools.wraps(func)
#         async def wrapper(*args: P.args, **kwargs: P.kwargs) -> RT:
#             last_error = None
#
#             for attempt in range(max_retries + 1):
#                 try:
#                     logger.debug(
#                         f"Executing {func.__name__} (attempt {attempt + 1}/{max_retries + 1})"
#                     )
#                     return await func(*args, **kwargs)
#                 except Exception as exc:
#                     last_error = exc
#                     if attempt < max_retries:
#                         delay = retry_delay * (attempt + 1)
#                         logger.warning(
#                             f"{func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): "
#                             f"{exc!r}. "
#                             f"Retrying in {delay:.1f}s..."
#                         )
#                         await asyncio.sleep(delay)
#
#                     else:
#                         logger.error(
#                             f"{func.__name__} failed after {max_retries + 1} attempts: {exc!r}"
#                         )
#
#             # If we get here, all retries failed
#             raise ProviderRequestError(
#                 f"Operation failed after {max_retries + 1} attempts: {last_error}"
#             )
#
#         return wrapper
#
#     return decorator
