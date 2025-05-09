import logging
import time
from typing import TypeVar, Generic, Callable, ParamSpec

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
