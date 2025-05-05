"""Tests for provider service."""

import dataclasses
from typing import Self, cast

import httpx
import pytest
from pydantic import SecretStr
from unittest.mock import AsyncMock

from src.services.providers import ProviderService, ProviderClient
from src.models import LLMProvider, AIModel
from src.settings import AppSettings
from src.constants import Provider

from src.tests.conftest import TestResponse

pytestmark = pytest.mark.asyncio


@dataclasses.dataclass
class TestHTTPxClient:
    def __init__(self, response: TestResponse, status_code: int = 200):
        self.response = response
        self.status_code = status_code
        self.get = AsyncMock(return_value=response)
        self.aclose = AsyncMock()
        super().__init__()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore
        pass


@pytest.fixture
def mock_httpx_client() -> TestHTTPxClient:
    """Return mock HTTP client."""
    test_response = TestResponse(
        status_code=200,
        headers={"content-type": "application/json"},
        data={},
    )
    test_client = TestHTTPxClient(test_response)
    return test_client

    # mock_client = AsyncMock(spec=httpx.AsyncClient, name="MockedHTTPxClient")
    # mock_client.__aenter__ = mock_client
    # # mock_client.get = AsyncMock()
    # # mock_client.aclose = AsyncMock()
    # return mock_client
    # # with patch("src.routers.proxy.ProxyService.__new__", return_value=service):
    # #     yield mock_client


@pytest.fixture
def mock_settings() -> AppSettings:
    """Return mock settings."""
    return AppSettings(
        auth_api_token=SecretStr("test-token"),
        providers=[
            LLMProvider(vendor=Provider.OPENAI, api_key=SecretStr("openai-key")),
            LLMProvider(vendor=Provider.ANTHROPIC, api_key=SecretStr("anthropic-key")),
        ],
        models_cache_ttl=60,
        http_proxy_url=None,
    )


@pytest.fixture
def service(mock_settings: AppSettings, mock_httpx_client: TestHTTPxClient) -> ProviderService:
    """Return a provider service instance."""
    return ProviderService(mock_settings, cast(httpx.AsyncClient, mock_httpx_client))


class TestProviderService:
    """Tests for ProviderService."""

    def test_get_client(self, service: ProviderService, mock_settings: AppSettings) -> None:
        """Test getting provider client."""
        provider = mock_settings.providers[0]
        client = service.get_client(provider)
        assert isinstance(client, ProviderClient)
        # Check client reuse
        assert service.get_client(provider) is client

    async def test_get_list_models_cached(
        self,
        mock_settings: AppSettings,
        service: ProviderService,
        mock_httpx_client: TestHTTPxClient,
    ) -> None:
        """Test getting models list with cache."""

        # Prepare mock models
        mock_models = [
            AIModel(id="gpt-4", name="GPT 4", type="chat", vendor="openai"),
            AIModel(id="claude-3", name="Claude 3", type="chat", vendor="anthropic"),
        ]
        # Set cache for the first provider
        service._models_cache.set(Provider.OPENAI, [mock_models[0]])
        # Another vendor is getting from API
        mock_httpx_client.response.data = {"data": {"models": [mock_models[1].model_dump()]}}

        # get models and check results
        models = await service.get_list_models()

        expected_model_pairs = [("openai", "GPT 4"), ("anthropic", "Claude 3")]
        actual_model_pairs = [(m.vendor, m.name) for m in models]
        assert expected_model_pairs == actual_model_pairs

        mock_httpx_client.get.assert_awaited_once_with(
            "https://api.anthropic.com/models", headers={"Authorization": "Bearer anthropic-key"}
        )

    async def test_get_list_models_force_refresh(
        self,
        service: ProviderService,
        mock_httpx_client: AsyncMock,
    ) -> None:
        """Test getting models list with force refresh."""

        old_model = AIModel(id="gpt-4", name="GPT 4 Old", type="chat", vendor="openai")
        # Prepare mock models
        mock_models: dict[str, list[AIModel]] = {
            "https://api.anthropic.com/models": [
                AIModel(id="gpt-4", name="GPT 4 New", type="chat", vendor="openai"),
            ],
            "https://api.openai.com/models": [
                AIModel(id="claude-3", name="Claude 3", type="chat", vendor="anthropic"),
            ],
        }
        # Set cache for the first provider
        service._models_cache.set(Provider.OPENAI, [old_model])

        # Another vendor is getting from API
        async def mocked_response_by_vendor(url: str, *_, **__) -> TestResponse:  # type: ignore
            return TestResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                data={"data": {"models": [m.model_dump() for m in mock_models[url]]}},
            )

        mock_httpx_client.get = AsyncMock(side_effect=mocked_response_by_vendor)

        # get models and check results
        models = await service.get_list_models(force_refresh=True)

        expected_model_pairs = {("openai", "GPT 4 New"), ("anthropic", "Claude 3")}
        actual_model_pairs = {(m.vendor, m.name) for m in models}
        assert actual_model_pairs == expected_model_pairs

        expected_call_urls = {
            "https://api.anthropic.com/models",
            "https://api.openai.com/models",
        }
        actual_call_urls = {call.args[0] for call in mock_httpx_client.get.call_args_list}
        assert actual_call_urls == expected_call_urls

    async def test_get_list_models_error_handling(
        self, service: ProviderService, mock_settings: AppSettings, mock_httpx_client: AsyncMock
    ) -> None:
        """Test error handling when getting models list."""
        # Mock error response
        mock_httpx_client.get = AsyncMock(side_effect=httpx.RequestError("Test error"))

        # Get models (should not raise exception)
        models = await service.get_list_models(force_refresh=True)

        # Verify empty result
        assert len(models) == 0

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

    async def test_close(
        self, service: ProviderService, mock_settings: AppSettings, mock_httpx_client: AsyncMock
    ) -> None:
        """Test service cleanup."""
        # Create some clients
        for provider in mock_settings.providers:
            service.get_client(provider)

        # Close service
        await service.close()

        # Verify all clients were closed
        assert mock_httpx_client.aclose.called
