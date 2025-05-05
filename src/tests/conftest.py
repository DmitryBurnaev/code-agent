"""Test configuration and fixtures."""

import dataclasses
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.dependencies.settings import get_app_settings
from src.main import make_app
from src.settings import AppSettings
from src.constants import Provider
from src.models import LLMProvider
from pydantic import SecretStr


@pytest.fixture
def mock_settings() -> AppSettings:
    """Return mock settings."""
    return AppSettings(
        auth_api_token=SecretStr("test-token"),
        providers=[LLMProvider(vendor=Provider.OPENAI, api_key=SecretStr("test-key"))],
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


# @pytest.fixture
# def override_get_settings(mock_settings: AppSettings) -> Generator[None, None, None]:
#     """Override get_settings() for tests."""
#     # Store original function
#     original_wrapped = get_settings.__wrapped__
#
#     # Override get_settings
#     get_settings.__wrapped__ = lambda: mock_settings
#
#     yield
#
#     # Restore original function
#     get_settings.__wrapped__ = original_wrapped
#


@pytest.fixture
def test_app(mock_settings: AppSettings) -> FastAPI:
    """Return FastAPI application for testing."""
    return make_app(mock_settings)


@dataclasses.dataclass
class TestResponse:
    headers: dict[str, str]
    data: dict[str, Any]
    status_code: int = 200

    def json(self) -> dict[str, Any]:
        return self.data


# @pytest.fixture
# async def test_client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
#     """Return async HTTP client for testing."""
#     async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
#         yield client
