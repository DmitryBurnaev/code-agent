import pytest
from unittest.mock import AsyncMock, Mock, patch
import time

from src.services.providers import ProviderService, AIModel
from src.utils import Cache
from src.settings import Settings, ProxyRoute


@pytest.fixture
def settings():
    """Create test settings with two providers."""
    return Settings(
        auth_api_token="test_token",
        providers=[],
        proxy_routes=[
            ProxyRoute(
                source_path="/proxy/openai",
                target_url="http://test.openai",
                auth_token="test",
            ),
            ProxyRoute(
                source_path="/proxy/anthropic",
                target_url="http://test.anthropic",
                auth_token="test",
            ),
        ],
    )


class TestCache:
    """Test suite for Cache class."""

    def test_cache_get_set(self):
        """Test basic get/set operations with different keys."""
        cache = Cache[str](ttl=1.0)

        # Check empty cache
        assert cache.get("test") is None

        # Verify basic set/get
        cache.set("test", "value")
        assert cache.get("test") == "value"

        # Verify multiple keys don't interfere
        cache.set("other", "value2")
        assert cache.get("test") == "value"
        assert cache.get("other") == "value2"

    def test_cache_expiration(self):
        """Test that cached values expire after TTL."""
        cache = Cache[str](ttl=0.1)  # Short TTL for testing

        cache.set("test", "value")
        assert cache.get("test") == "value"

        # Wait for TTL to expire
        time.sleep(0.2)
        assert cache.get("test") is None

    def test_cache_invalidation(self):
        """Test both selective and full cache invalidation."""
        cache = Cache[str](ttl=10.0)

        # Prepare test data
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        # Test selective invalidation
        cache.invalidate("key1")
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"

        # Test full cache invalidation
        cache.invalidate()
        assert cache.get("key2") is None


class TestProviderService:
    """Test suite for ProviderService class."""

    @pytest.fixture
    def service(self, settings):
        """Create ProviderService instance with test settings."""
        return ProviderService(settings)

    @pytest.fixture
    def mock_client(self):
        """Create mock client with async list_models method."""
        client = Mock()
        client.list_models = AsyncMock()
        return client

    async def test_list_models_caching(self, service, mock_client):
        """Test per-provider model caching behavior."""
        service.get_client = Mock(return_value=mock_client)

        # Prepare test responses
        openai_models = [AIModel(id="gpt-4", provider="openai")]
        anthropic_models = [AIModel(id="claude-3", provider="anthropic")]

        mock_client.list_models.side_effect = [
            openai_models,  # First call for OpenAI
            anthropic_models,  # First call for Anthropic
        ]

        # Initial fetch should call both providers
        models = await service.list_models()
        assert len(models) == 2
        assert mock_client.list_models.call_count == 2

        # Subsequent fetch should use cache
        models = await service.list_models()
        assert len(models) == 2
        assert mock_client.list_models.call_count == 2  # Count shouldn't increase

    async def test_partial_cache_invalidation(self, service, mock_client):
        """Test that cache invalidation affects only specified provider."""
        service.get_client = Mock(return_value=mock_client)

        openai_models = [AIModel(id="gpt-4", provider="openai")]
        anthropic_models = [AIModel(id="claude-3", provider="anthropic")]

        mock_client.list_models.side_effect = [
            openai_models,
            anthropic_models,
        ]

        # Cache initial data
        await service.list_models()
        assert mock_client.list_models.call_count == 2

        # Invalidate only OpenAI cache
        service.invalidate_models_cache("openai")

        # Next fetch should only refresh OpenAI
        mock_client.list_models.side_effect = [openai_models]
        models = await service.list_models()

        assert len(models) == 2
        assert mock_client.list_models.call_count == 3  # One additional call for OpenAI

    async def test_failed_provider_handling(self, service, mock_client):
        """Test graceful handling of provider failures."""
        service.get_client = Mock(return_value=mock_client)

        openai_models = [AIModel(id="gpt-4", provider="openai")]
        mock_client.list_models.side_effect = [
            openai_models,  # OpenAI succeeds
            Exception("API Error"),  # Anthropic fails
        ]

        # Should return models from successful provider only
        models = await service.list_models()
        assert len(models) == 1
        assert models[0].provider == "openai"

        # Cached data should persist despite new failures
        mock_client.list_models.side_effect = [Exception("API Error")]
        models = await service.list_models()
        assert len(models) == 1
        assert models[0].provider == "openai"


class TestProviderService2:
    """Test suite for ProviderService class."""

    @pytest.fixture
    def service(self, settings):
        """Create test service instance."""
        return ProviderService(settings)

    @pytest.fixture
    def mock_client(self):
        """Create mock client with list_models method."""
        client = Mock()
        client.list_models = AsyncMock()
        return client

    async def test_list_models_caching(self, service, mock_client):
        """Test that models are cached per provider."""
        # Mock get_client to return our test client
        service.get_client = Mock(return_value=mock_client)

        # Setup mock responses
        openai_models = [AIModel(id="gpt-4", provider="openai")]
        anthropic_models = [AIModel(id="claude-3", provider="anthropic")]

        mock_client.list_models.side_effect = [
            openai_models,  # First call for openai
            anthropic_models,  # First call for anthropic
        ]

        # First call should fetch all providers
        models = await service.list_models()
        assert len(models) == 2
        assert mock_client.list_models.call_count == 2

        # Second call should use cache
        models = await service.list_models()
        assert len(models) == 2
        # Call count should not increase as we use cache
        assert mock_client.list_models.call_count == 2

    async def test_partial_cache_invalidation(self, service, mock_client):
        """Test that invalidating one provider doesn't affect others."""
        service.get_client = Mock(return_value=mock_client)

        openai_models = [AIModel(id="gpt-4", provider="openai")]
        anthropic_models = [AIModel(id="claude-3", provider="anthropic")]

        mock_client.list_models.side_effect = [
            openai_models,
            anthropic_models,
        ]

        # Initial fetch
        await service.list_models()
        assert mock_client.list_models.call_count == 2

        # Invalidate only openai cache
        service.invalidate_models_cache("openai")

        # Next fetch should only call openai
        mock_client.list_models.side_effect = [openai_models]
        models = await service.list_models()

        assert len(models) == 2
        # One more call for openai only
        assert mock_client.list_models.call_count == 3

    async def test_failed_provider_handling(self, service, mock_client):
        """Test handling of failed provider requests."""
        service.get_client = Mock(return_value=mock_client)

        openai_models = [AIModel(id="gpt-4", provider="openai")]
        mock_client.list_models.side_effect = [
            openai_models,  # openai succeeds
            Exception("API Error"),  # anthropic fails
        ]

        # Should return models from successful provider
        models = await service.list_models()
        assert len(models) == 1
        assert models[0].provider == "openai"

        # Cache should still work for successful provider
        mock_client.list_models.side_effect = [Exception("API Error")]
        models = await service.list_models()
        assert len(models) == 1
        assert models[0].provider == "openai"
