"""Tests for vendor service."""

from typing import cast

import httpx
import pytest
from unittest.mock import AsyncMock

from src.services.vendors import VendorService, VendorClient
from src.models import AIModel, LLMVendor
from src.settings import AppSettings
from src.constants import VendorSlug

from src.tests.conftest import MockTestResponse, MockHTTPxClient

pytestmark = pytest.mark.asyncio
type MOCK_MODELS_TYPE = dict[str, dict[str, list[dict[str, str | int]]]]


@pytest.fixture
def mock_models() -> MOCK_MODELS_TYPE:
    return {
        "https://api.deepseek.com/v1/models": {
            "data": [
                {
                    "id": "deepseek-1",
                    "object": "model",
                    "created": 1698785180,
                    "owned_by": "system",
                },
            ]
        },
        "https://api.openai.com/v1/models": {
            "data": [
                {
                    "id": "gpt-4",
                    "object": "model",
                    "created": 1698785180,
                    "owned_by": "system",
                },
                {
                    "id": "open-model-e-3",
                    "object": "model",
                    "created": 1698785189,
                    "owned_by": "system",
                },
            ],
        },
    }


@pytest.fixture
def mock_httpx_for_models_client(mock_models: MOCK_MODELS_TYPE) -> MockHTTPxClient:
    """Return mock HTTP client."""

    async def mocked_response_by_vendor(url: str, *_, **__) -> MockTestResponse:  # type: ignore
        return MockTestResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            data=mock_models[url],
        )

    return MockHTTPxClient(get_method=AsyncMock(side_effect=mocked_response_by_vendor))


@pytest.fixture
def service(
    app_settings_test: AppSettings,
    mock_httpx_for_models_client: MockHTTPxClient,
) -> VendorService:
    """Return a vendor service instance."""
    return VendorService(app_settings_test, cast(httpx.AsyncClient, mock_httpx_for_models_client))


class TestVendorService:
    """Tests for VendorService."""

    async def test_get_client(
        self,
        service: VendorService,
        app_settings_test: AppSettings,
        llm_vendors: list[LLMVendor],
    ) -> None:
        """Test getting vendor client."""
        vendor = llm_vendors[0]
        client = service.get_client(vendor)
        assert isinstance(client, VendorClient)
        assert service.get_client(vendor) is client

    async def test_get_list_models_cached(
        self,
        app_settings_test: AppSettings,
        service: VendorService,
        mock_httpx_for_models_client: MockHTTPxClient,
    ) -> None:
        """Test getting models' list with cache."""
        service._cache_set_data(
            VendorSlug.OPENAI,
            [AIModel(id="openai__gpt-4", vendor="openai", vendor_id="gpt-4")],
        )

        models = await service.get_list_models()

        expected_model_pairs = [
            AIModel(id="openai__gpt-4", vendor="openai", vendor_id="gpt-4"),
            AIModel(id="deepseek__deepseek-1", vendor="deepseek", vendor_id="deepseek-1"),
        ]
        assert models == expected_model_pairs

        mock_httpx_for_models_client.get.assert_awaited_once_with(
            "https://api.deepseek.com/v1/models", headers={"Authorization": "Bearer deepseek-key"}
        )

    async def test_get_list_models_force_refresh(
        self,
        service: VendorService,
        mock_httpx_for_models_client: AsyncMock,
    ) -> None:
        """Test getting models list with force refresh."""

        # Set cache for the first vendor
        service._cache_set_data(
            VendorSlug.OPENAI,
            [AIModel(id="openai__old-gpt-4", vendor="openai", vendor_id="old-gpt-4")],
        )

        # get models and check results
        models = await service.get_list_models(force_refresh=True)

        expected_model_pairs = [
            AIModel(id="openai__gpt-4", vendor="openai", vendor_id="gpt-4"),
            AIModel(id="openai__open-model-e-3", vendor="openai", vendor_id="open-model-e-3"),
            AIModel(id="deepseek__deepseek-1", vendor="deepseek", vendor_id="deepseek-1"),
        ]
        assert models == expected_model_pairs

        expected_call_urls = [
            "https://api.deepseek.com/v1/models",
            "https://api.openai.com/v1/models",
        ]
        actual_call_urls = [
            call.args[0] for call in mock_httpx_for_models_client.get.call_args_list
        ]
        assert sorted(actual_call_urls) == expected_call_urls

    async def test_get_list_models_error_handling(
        self,
        service: VendorService,
        app_settings_test: AppSettings,
        mock_httpx_for_models_client: AsyncMock,
    ) -> None:
        """Test error handling when getting models' list."""
        # Mock error response
        mock_httpx_for_models_client.get = AsyncMock(side_effect=httpx.RequestError("Test error"))

        # Get models (should not raise exception)
        models = await service.get_list_models(force_refresh=True)

        # Verify empty result
        assert models == []
