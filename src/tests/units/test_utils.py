"""Tests for utils."""

import time
from typing import TypeVar

import pytest

from src.utils import Cache

T = TypeVar("T")


class TestCache:
    """Tests for Cache class."""

    @pytest.fixture
    def cache(self) -> Cache[str]:
        """Return cache instance for testing."""
        return Cache[str](ttl=0.1)

    def test_get_set(self, cache: Cache[str]) -> None:
        """Test basic get/set operations."""
        # Test setting and getting value
        cache.set("test", "value")
        assert cache.get("test") == "value"

        # Test getting non-existent key
        assert cache.get("non-existent") is None

    def test_ttl_expiration(self, cache: Cache[str]) -> None:
        """Test TTL expiration."""
        # Set value and verify it's there
        cache.set("test", "value")
        assert cache.get("test") == "value"

        # Wait for TTL to expire
        time.sleep(0.2)

        # Verify value is gone
        assert cache.get("test") is None

    def test_invalidate(self, cache: Cache[str]) -> None:
        """Test cache invalidation."""
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

    def test_generic_type(self) -> None:
        """Test generic type support."""
        # Test with string
        str_cache = Cache[str](ttl=0.1)
        str_cache.set("test", "value")
        assert str_cache.get("test") == "value"

        # Test with int
        int_cache = Cache[int](ttl=0.1)
        int_cache.set("test", 42)
        assert int_cache.get("test") == 42

        # Test with list
        list_cache = Cache[list[str]](ttl=0.1)
        list_cache.set("test", ["value1", "value2"])
        assert list_cache.get("test") == ["value1", "value2"]
