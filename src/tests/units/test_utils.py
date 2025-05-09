"""Tests for utils."""

import time

import pytest

from src.utils import Cache, singleton


class TestSingleton:
    """Tests for singleton decorator."""

    def test_same_instance(self) -> None:
        """Test that multiple instances are actually the same object."""
        # Create instances of the same class

        @singleton
        class TestClass:
            def __init__(self, value: str = "default") -> None:
                self.value = value

        instance1 = TestClass("first")
        instance2 = TestClass("second")
        instance3 = TestClass()

        # Check that this is the same object
        assert instance1 is instance2 is instance3
        # And it has the values from the first initialization
        assert instance1.value == "first"
        assert instance2.value == "first"
        assert instance3.value == "first"

    def test_state_persistence(self) -> None:
        """Test that a singleton state persists between instances."""
        # Create an instance and change its state

        @singleton
        class TestClass:
            def __init__(self, value: str = "default") -> None:
                self.value = value
                self.modified = False

        instance1 = TestClass()
        instance1.value = "modified"
        instance1.modified = True

        # Create a new instance and check that the state is preserved
        instance2 = TestClass("ignored value")
        assert instance2.value == "modified"
        assert instance2.modified is True

        instance2.value = ""

    def test_multiple_singleton_classes(self) -> None:
        """Test that different singleton classes don't interfere."""

        @singleton
        class TestClass:
            def __init__(self, value: str) -> None:
                self.value = value

        @singleton
        class AnotherTestClass:
            def __init__(self, value: int = 0) -> None:
                self.value = value

        # Create instances of different classes
        test1 = TestClass("test")
        test2 = TestClass("ignored")
        another1 = AnotherTestClass(42)
        another2 = AnotherTestClass(24)

        # Check that instances of the same class are the same
        assert test1 is test2
        assert another1 is another2

        # But instances of different classes are different
        assert test1 is not another1  # type: ignore

        # And states are not shared
        assert test1.value == "test"
        assert another1.value == 42


class TestCache:
    """Tests for Cache class."""

    @pytest.fixture
    def cache(self) -> Cache[str]:
        """Return a cache instance for testing."""
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
        # Set a value and verify it's there
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

        # Test with a list
        list_cache = Cache[list[str]](ttl=0.1)
        list_cache.set("test", ["value1", "value2"])
        assert list_cache.get("test") == ["value1", "value2"]
