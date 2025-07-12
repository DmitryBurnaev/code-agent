"""Test configuration and fixtures."""

import dataclasses
import json
from typing import Any, cast, Self
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.main import make_app
from src.services.vendors import VendorService
from src.settings import AppSettings, get_app_settings
from src.constants import VendorSlug
from src.models import LLMVendor
from pydantic import SecretStr


@pytest.fixture
def mock_settings() -> AppSettings:
    """Return mock settings."""
    return AppSettings(
        api_token=SecretStr("test-token"),
        admin_username="test-username",
        admin_password=SecretStr("test-password"),
        secret_key=SecretStr("test-secret"),
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
def vendors() -> list[LLMVendor]:
    return [
        LLMVendor(
            slug=VendorSlug.OPENAI,
            api_key=SecretStr("test-key"),
        )
    ]


@pytest.fixture
def client(
    auth_test_token: str,
    vendors: list[LLMVendor],
    auth_test_header: dict[str, str],
) -> TestClient:
    """Create a test client with mocked settings."""
    test_settings = AppSettings(
        api_token=SecretStr(auth_test_token),
        http_proxy_url=None,
        admin_username="test-username",
        admin_password=SecretStr("test-password"),
        secret_key=SecretStr("test-secret"),
    )
    test_app = make_app(settings=test_settings)
    test_app.dependency_overrides = {
        get_app_settings: lambda: test_settings,
    }
    return TestClient(test_app, headers=auth_test_header)


@dataclasses.dataclass
class MockTestResponse:
    headers: dict[str, str]
    data: dict[str, Any] | list[dict[str, Any]]
    status_code: int = 200

    def json(self) -> dict[str, Any] | list[dict[str, Any]]:
        return self.data

    @property
    def text(self) -> str:
        return json.dumps(self.data)


class MockHTTPxClient:
    """Imitate real http client but with mocked response"""

    def __init__(
        self,
        response: MockTestResponse | None = None,
        get_method: AsyncMock | None = None,
    ):
        if not any([response, get_method]):
            raise AssertionError("At least one of `response` or `get_method` must be specified")

        self.response = response
        self.get = get_method or AsyncMock(return_value=response)
        self.aclose = AsyncMock()
        super().__init__()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore
        pass


@pytest.fixture
def mock_httpx_client() -> MockHTTPxClient:
    """Return mock HTTP client."""
    test_response = MockTestResponse(
        status_code=200,
        headers={"content-type": "application/json"},
        data={},
    )
    test_client = MockHTTPxClient(test_response)
    return test_client


@pytest.fixture
def service(mock_settings: AppSettings, mock_httpx_client: MockHTTPxClient) -> VendorService:
    """Return a vendor's service instance."""
    return VendorService(mock_settings, cast(httpx.AsyncClient, mock_httpx_client))


@pytest.fixture
def test_app(mock_settings: AppSettings) -> FastAPI:
    """Return FastAPI application for testing."""
    return make_app(mock_settings)
