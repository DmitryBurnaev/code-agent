import time

import pytest

from src.services.cache import InMemoryCache


class TestCache:

    @pytest.fixture
    def cache(self) -> InMemoryCache:
        return InMemoryCache()

    def test_get_set(self, cache: InMemoryCache) -> None:
        # Test setting and getting value
        cache.set("test", "value")
        assert cache.get("test") == "value"

        # Test getting non-existent key
        assert cache.get("non-existent") is None

    def test_ttl_expiration(self, cache: InMemoryCache, monkeypatch) -> None:  # type: ignore
        old_ttl = cache._ttl
        cache._ttl = 0.1
        cache.set("test", "value")
        assert cache.get("test") == "value"

        # Verify value is gone
        time.sleep(0.2)
        assert cache.get("test") is None
        cache._ttl = old_ttl

    def test_invalidate(self, cache: InMemoryCache) -> None:
        # Set multiple values
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        # Invalidate specific key
        cache.invalidate("key1")
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"

        # Invalidate all
        cache.invalidate()
        assert cache.get("key1") is None
        assert cache.get("key2") is None
