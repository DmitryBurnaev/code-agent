import os
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from src.main import make_app, CodeAgentAPP
from src.modules.auth.tokens import make_api_token
from src.settings import AppSettings, get_app_settings
from src.constants import VendorSlug
from src.models import LLMVendor
from pydantic import SecretStr

from src.tests.mocks import MockAPIToken, MockUser, MockVendor, MockTestResponse, MockHTTPxClient


MINIMAL_ENV_VARS = {
    "SECRET_KEY": "test-key",
    "ADMIN_PASSWORD": "test-password",
    "VENDOR_ENCRYPTION_KEY": "test-encryption-key",
}


@pytest.fixture
def mock_user() -> MockUser:
    return MockUser(id=1, is_active=True, username="test-user")


@pytest.fixture
def app_settings_test() -> AppSettings:
    return AppSettings(
        http_proxy_url=None,
        admin_username="test-username",
        admin_password=SecretStr("test-password-oKcqO3rPCxt2"),
        app_secret_key=SecretStr("example-UStLb8mds9K"),
        vendor_encryption_key=SecretStr("test-encryption-key"),
    )


@pytest.fixture(autouse=True)
def minimal_env_vars() -> Generator[None, Any, None]:
    with patch.dict(os.environ, MINIMAL_ENV_VARS):
        yield


@pytest.fixture
def test_app(app_settings_test: AppSettings) -> Generator[CodeAgentAPP, Any, None]:
    test_app = make_app(settings=app_settings_test)
    test_app.dependency_overrides[get_app_settings] = lambda: test_app.settings
    yield test_app
    test_app.dependency_overrides.clear()


@pytest.fixture
def auth_test_token(app_settings_test: AppSettings) -> str:
    return make_api_token(expires_at=None, settings=app_settings_test).value


@pytest.fixture
def mock_request() -> MagicMock:
    request = MagicMock()
    request.method = "GET"
    return request


@pytest.fixture
def llm_vendors() -> list[LLMVendor]:
    return [
        LLMVendor(
            slug=VendorSlug.OPENAI,
            api_key=SecretStr("test-key"),
        )
    ]


@pytest.fixture
def mock_db_vendors__all() -> Generator[list[MockVendor], Any, None]:
    with patch("src.db.repositories.VendorRepository.all") as mock_get_vendors:
        mocked_vendors = [
            MockVendor(id=1, slug=VendorSlug.OPENAI, name=VendorSlug.OPENAI),
            MockVendor(id=2, slug=VendorSlug.DEEPSEEK, name=VendorSlug.DEEPSEEK, is_active=False),
        ]
        mock_get_vendors.return_value = mocked_vendors
        yield mocked_vendors


@pytest.fixture
def mock_db_vendors__active() -> Generator[list[MockVendor], Any, None]:
    with patch("src.db.repositories.VendorRepository.filter") as mock_get_vendors:
        mocked_vendors = [
            MockVendor(id=1, slug=VendorSlug.OPENAI, name=VendorSlug.OPENAI, is_active=True),
            MockVendor(id=2, slug=VendorSlug.DEEPSEEK, name=VendorSlug.DEEPSEEK, is_active=True),
        ]
        mock_get_vendors.return_value = mocked_vendors
        yield mocked_vendors


@pytest.fixture
def mock_db_api_token__active() -> Generator[MockAPIToken, Any, None]:
    with patch("src.db.repositories.TokenRepository.get_by_token") as mock_get_by_token:
        mock_token = MockAPIToken(is_active=True, user=MockUser(id=1, is_active=True))
        mock_get_by_token.return_value = mock_token
        yield mock_token


@pytest.fixture
def client(
    test_app: CodeAgentAPP,
    mock_db_api_token__active: MockAPIToken,
    llm_vendors: list[LLMVendor],
    auth_test_token: str,
) -> Generator[TestClient, Any, None]:
    headers = {
        "Authorization": f"Bearer {auth_test_token}",
    }
    with TestClient(test_app, headers=headers) as client:
        yield client


@pytest.fixture
def mock_httpx_client() -> MockHTTPxClient:
    test_response = MockTestResponse(
        status_code=200,
        headers={"content-type": "application/json"},
        data={},
    )
    test_client = MockHTTPxClient(test_response)
    return test_client
