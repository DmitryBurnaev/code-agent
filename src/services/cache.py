import time
import logging
from typing import Protocol, Any, TypeAlias

from src.utils import singleton

logger = logging.getLogger("cache")
DEFAULT_CACHE_TTL: int = 3600
CacheValueType: TypeAlias = str | list[dict[str, Any]] | dict[str, Any]


class CacheProtocol(Protocol):

    def get(self, key: str) -> CacheValueType | None:
        pass

    def set(self, key: str, value: CacheValueType, ttl: int | None = None) -> None:
        pass

    def invalidate(self, key: str | None = None) -> None:
        pass


@singleton
class InMemoryCache(CacheProtocol):
    """Simple in-memory cache with TTL per key."""

    def __init__(self) -> None:
        self._ttl: float = DEFAULT_CACHE_TTL
        self._data: dict[str, CacheValueType] = {}
        self._last_update: dict[str, float] = {}

    def get(self, key: str) -> CacheValueType | None:
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

    def set(self, key: str, value: CacheValueType, ttl: int | None = None) -> None:
        """Set new cache value for key and update timestamp.

        Args:
            key: Cache key to store value
            value: Value to cache
            ttl: TTL to use
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
