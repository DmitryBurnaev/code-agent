import time
from typing import TypeVar, Generic, Dict, Optional

T = TypeVar("T")


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
