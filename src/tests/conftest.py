"""Test configuration and fixtures."""

import dataclasses
from typing import Any, cast, Self
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.dependencies.settings import get_app_settings
from src.main import make_app
from src.services.providers import ProviderService
from src.settings import AppSettings
from src.constants import Provider
from src.models import LLMProvider
from pydantic import SecretStr


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
def auth_test_token() -> str:
    return "test-auth-token"


@pytest.fixture
def auth_test_header(auth_test_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {auth_test_token}",
    }


@pytest.fixture
def providers() -> list[LLMProvider]:
    return [
        LLMProvider(
            vendor=Provider.OPENAI,
            api_key=SecretStr("test-key"),
        )
    ]


@pytest.fixture
def client(
    auth_test_token: str,
    providers: list[LLMProvider],
    auth_test_header: dict[str, str],
) -> TestClient:
    """Create a test client with mocked settings."""
    test_settings = AppSettings(
        auth_api_token=SecretStr(auth_test_token),
        providers=providers,
        http_proxy_url=None,
    )
    test_app = make_app(settings=test_settings)
    test_app.dependency_overrides = {
        get_app_settings: lambda: test_settings,
    }
    return TestClient(test_app, headers=auth_test_header)


@dataclasses.dataclass
class TestResponse:
    headers: dict[str, str]
    data: dict[str, Any]
    status_code: int = 200

    def json(self) -> dict[str, Any]:
        return self.data


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


@pytest.fixture
def service(mock_settings: AppSettings, mock_httpx_client: TestHTTPxClient) -> ProviderService:
    """Return a provider service instance."""
    return ProviderService(mock_settings, cast(httpx.AsyncClient, mock_httpx_client))


@pytest.fixture
def test_app(mock_settings: AppSettings) -> FastAPI:
    """Return FastAPI application for testing."""
    return make_app(mock_settings)
