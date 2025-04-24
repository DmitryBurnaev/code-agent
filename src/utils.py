import asyncio
import functools
import logging
import time
from typing import (
    TypeVar,
    Generic,
    Callable,
    Awaitable,
    Any,
    ParamSpec,
    overload,
    Protocol,
    runtime_checkable,
)

from src.exceptions import ProviderRequestError

logger = logging.getLogger(__name__)
T = TypeVar("T")
RT = TypeVar("RT", covariant=True)
P = ParamSpec("P")


class Cache(Generic[T]):
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

        return self._data[key]

    def set(self, key: str, value: T) -> None:
        """Set new cache value for key and update timestamp.

        Args:
            key: Cache key to store value under
            value: Value to cache
        """
        self._data[key] = value
        self._last_update[key] = time.monotonic()

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


class ProviderError(Exception):
    """Custom exception raised when all retry attempts fail."""

    pass


def decohints(decorator: Callable[..., Any]) -> Callable[..., Any]:
    """
    Small helper which helps to say IDE: "decorated method has the same params and return types"
    """
    return decorator


@runtime_checkable
class AsyncCallable(Protocol[P, RT]):
    """Protocol for async callable that helps with type inference."""

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Awaitable[RT]: ...


@overload
def retry_with_timeout(
    func: AsyncCallable[P, RT],
) -> AsyncCallable[P, RT]: ...


@overload
def retry_with_timeout(
    func: None = None,
    *,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> Callable[[AsyncCallable[P, RT]], AsyncCallable[P, RT]]: ...


@decohints
def retry_with_timeout(
    func: AsyncCallable[P, RT] | None = None,
    *,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> Callable[[AsyncCallable[P, RT]], AsyncCallable[P, RT]] | AsyncCallable[P, RT]:
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
        ProviderRequestError: If all retry attempts fail
        TypeError: If the decorated function is not async or has wrong return type
    """

    def decorator(func: AsyncCallable[P, RT]) -> AsyncCallable[P, RT]:
        if not asyncio.iscoroutinefunction(func):
            raise TypeError(f"Function {func!r} must be async")

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

            raise ProviderRequestError(
                f"All {max_retries} attempts failed for {func.__name__}"
            ) from last_exception

        return wrapper

    if func is not None:
        return decorator(func)

    return decorator
