"""Tests for provider service."""
import pytest
from unittest.mock import Mock, AsyncMock, PropertyMock
import httpx

from src.services.providers import ProviderService, ProviderClient
from src.models import LLMProvider, AIModel
from src.settings import AppSettings
from src.constants import Provider
from pydantic import SecretStr


class TestProviderService:
    """Tests for ProviderService."""

    @pytest.fixture
    def mock_http_client(self) -> AsyncMock:
        """Return mock HTTP client."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "models": [],
            }
        }
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()
        return mock_client

    @pytest.fixture
    def mock_settings(self) -> AppSettings:
        """Return mock settings."""
        return AppSettings(
            auth_api_token=SecretStr("test-token"),
            providers=[
                LLMProvider(vendor=Provider.OPENAI, api_key=SecretStr("test-key")),
                LLMProvider(vendor=Provider.ANTHROPIC, api_key=SecretStr("test-key")),
            ],
            models_cache_ttl=60,
            http_proxy_url=None,
        )

    @pytest.fixture
    def service(self, mock_settings: AppSettings, mock_http_client: AsyncMock) -> ProviderService:
        """Return provider service instance."""
        return ProviderService(mock_settings, mock_http_client)

    @pytest.mark.anyio
    async def test_get_client(self, service: ProviderService, mock_settings: AppSettings) -> None:
        """Test getting provider client."""
        provider = mock_settings.providers[0]
        client = service.get_client(provider)
        assert isinstance(client, ProviderClient)
        # Check client reuse
        assert service.get_client(provider) is client

    @pytest.mark.anyio
    async def test_get_list_models_cached(
        self, service: ProviderService, mock_settings: AppSettings, mock_http_client: AsyncMock
    ) -> None:
        """Test getting models list with cache."""
        # Prepare mock models
        mock_models = [
            AIModel(id="gpt-4", name="GPT-4", type="chat", vendor="openai"),
            AIModel(id="claude-3", name="Claude 3", type="chat", vendor="anthropic"),
        ]
        
        # Set cache for first provider
        service._models_cache.set(mock_settings.providers[0].vendor, [mock_models[0]])
        
        # Mock response for second provider
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "models": [mock_models[1].model_dump()],
            }
        }
        mock_http_client.get = AsyncMock(return_value=mock_response)

        # Get models
        models = await service.get_list_models()
        
        # Verify results
        assert len(models) == 2
        assert any(m.id == "gpt-4" for m in models)
        assert any(m.id == "claude-3" for m in models)

    @pytest.mark.anyio
    async def test_get_list_models_force_refresh(
        self, service: ProviderService, mock_settings: AppSettings, mock_http_client: AsyncMock
    ) -> None:
        """Test getting models list with force refresh."""
        # Prepare mock models
        mock_models = [
            AIModel(id="gpt-4", name="GPT-4", type="chat", vendor="openai"),
            AIModel(id="claude-3", name="Claude 3", type="chat", vendor="anthropic"),
        ]
        
        # Set cache for both providers
        for provider, model in zip(mock_settings.providers, mock_models):
            service._models_cache.set(provider.vendor, [model])

        # Mock responses for both providers
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "models": [m.model_dump() for m in mock_models],
            }
        }
        mock_http_client.get = AsyncMock(return_value=mock_response)

        # Get models with force refresh
        models = await service.get_list_models(force_refresh=True)
        
        # Verify results
        assert len(models) == 4  # 2 from each provider
        assert len([m for m in models if m.id == "gpt-4"]) == 2
        assert len([m for m in models if m.id == "claude-3"]) == 2

    @pytest.mark.anyio
    async def test_get_list_models_error_handling(
        self, service: ProviderService, mock_settings: AppSettings, mock_http_client: AsyncMock
    ) -> None:
        """Test error handling when getting models list."""
        # Mock error response
        mock_http_client.get = AsyncMock(side_effect=httpx.RequestError("Test error"))

        # Get models (should not raise exception)
        models = await service.get_list_models(force_refresh=True)
        
        # Verify empty result
        assert len(models) == 0

    @pytest.mark.anyio
    async def test_invalidate_models_cache(
        self, service: ProviderService, mock_settings: AppSettings
    ) -> None:
        """Test cache invalidation."""
        # Prepare mock models
        mock_models = [
            AIModel(id="gpt-4", name="GPT-4", type="chat", vendor="openai"),
            AIModel(id="claude-3", name="Claude 3", type="chat", vendor="anthropic"),
        ]
        
        # Set cache for both providers
        for provider, model in zip(mock_settings.providers, mock_models):
            service._models_cache.set(provider.vendor, [model])

        # Invalidate cache for first provider
        service.invalidate_models_cache(mock_settings.providers[0].vendor)
        assert service._models_cache.get(mock_settings.providers[0].vendor) is None
        assert service._models_cache.get(mock_settings.providers[1].vendor) is not None

        # Invalidate all cache
        service.invalidate_models_cache()
        assert service._models_cache.get(mock_settings.providers[0].vendor) is None
        assert service._models_cache.get(mock_settings.providers[1].vendor) is None

    @pytest.mark.anyio
    async def test_close(
        self, service: ProviderService, mock_settings: AppSettings, mock_http_client: AsyncMock
    ) -> None:
        """Test service cleanup."""
        # Create some clients
        for provider in mock_settings.providers:
            service.get_client(provider)

        # Close service
        await service.close()

        # Verify all clients were closed
        assert mock_http_client.aclose.called 