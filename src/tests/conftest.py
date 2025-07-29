"""Test configuration and fixtures."""

import dataclasses
import json
from typing import Any, Generator, cast, Self
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.main import make_app
from src.modules.auth.tokens import make_api_token
from src.services.vendors import VendorService
from src.settings import AppSettings, get_app_settings
from src.constants import VendorSlug
from src.models import LLMVendor
from pydantic import SecretStr

type GenMockPair = Generator[tuple[MagicMock, AsyncMock], Any, None]


@dataclasses.dataclass
class MockUser:
    id: int
    is_active: bool = False
    username: str = "test-user"


@pytest.fixture
def mock_user() -> MockUser:
    """Return a mock user object."""
    return MockUser(id=1, is_active=True, username="test-user")


@dataclasses.dataclass
class MockAPIToken:
    is_active: bool
    user: MockUser


@pytest.fixture
def app_settings_test(auth_test_token: str) -> AppSettings:
    """Return mock settings."""
    return AppSettings(
        api_token=SecretStr(auth_test_token),
        http_proxy_url=None,
        admin_username="test-username",
        admin_password=SecretStr("test-password"),
        secret_key=SecretStr("test-secret"),
        vendor_encryption_key=SecretStr("test-key"),
    )


@pytest.fixture
def test_app(app_settings_test: AppSettings) -> FastAPI:
    """Return FastAPI application for testing."""
    return make_app(app_settings_test)


@pytest.fixture
def auth_test_token(app_settings_test: AppSettings) -> str:
    return make_api_token(expires_at=None, settings=app_settings_test).value


@pytest.fixture
def mock_request() -> MagicMock:
    """Return mock request object."""
    request = MagicMock()
    request.method = "GET"
    return request


@pytest.fixture
def mock_session_uow() -> GenMockPair:
    """Mock SASessionUOW context manager."""
    with patch("src.db.services.SASessionUOW") as mock_uow:
        mock_session = AsyncMock()
        mock_uow.return_value.__aenter__.return_value.session = mock_session
        yield mock_uow, mock_session


@pytest.fixture
def llm_vendors() -> list[LLMVendor]:
    return [
        LLMVendor(
            slug=VendorSlug.OPENAI,
            api_key=SecretStr("test-key"),
        )
    ]


@pytest.fixture
def client(
    app_settings_test: AppSettings,
    llm_vendors: list[LLMVendor],
    auth_test_token: str,
) -> TestClient:
    """Create a test client with mocked settings."""
    test_app = make_app(settings=app_settings_test)
    test_app.dependency_overrides = {get_app_settings: lambda: app_settings_test}
    headers = {
        "Authorization": f"Bearer {auth_test_token}",
    }
    return TestClient(test_app, headers=headers)


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
def service(app_settings_test: AppSettings, mock_httpx_client: MockHTTPxClient) -> VendorService:
    """Return a vendor's service instance."""
    return VendorService(app_settings_test, cast(httpx.AsyncClient, mock_httpx_client))
