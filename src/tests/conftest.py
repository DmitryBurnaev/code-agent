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
from src.services.vendors import VendorService
from src.settings import AppSettings, get_app_settings
from src.constants import VendorSlug
from src.db.models import User, Token
from src.models import LLMVendor
from pydantic import SecretStr

type GenMockPair = Generator[tuple[MagicMock, AsyncMock], Any, None]


@pytest.fixture
def mock_settings(auth_test_token: str) -> AppSettings:
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
def auth_test_token() -> str:
    return "test-auth-token"


@pytest.fixture
def mock_request() -> MagicMock:
    """Return mock request object."""
    request = MagicMock()
    request.method = "GET"
    return request


@pytest.fixture
def mock_make_token() -> Generator[MagicMock, Any, None]:
    """Mock make_api_token function."""
    with patch("src.modules.auth.tokens.make_api_token") as mock:
        mock.return_value = MagicMock(value="test-token-value", hashed_value="test-hash")
        yield mock


@pytest.fixture
def mock_decode_token() -> Generator[MagicMock, Any, None]:
    """Mock decode_api_token function."""
    with patch("src.modules.auth.tokens.decode_api_token") as mock:
        mock.return_value = MagicMock(sub="test-user-id")
        yield mock


@pytest.fixture
def mock_hash_token() -> Generator[MagicMock, Any, None]:
    """Mock hash_token function."""
    with patch("src.modules.auth.tokens.hash_token") as mock:
        mock.return_value = "test-hash"
        yield mock


@pytest.fixture
def mock_session_uow() -> GenMockPair:
    """Mock SASessionUOW context manager."""
    with patch("src.db.services.SASessionUOW") as mock_uow:
        mock_session = AsyncMock()
        mock_uow.return_value.__aenter__.return_value.session = mock_session
        yield mock_uow, mock_session


@pytest.fixture
def mock_token_repository_active(mock_session_uow: GenMockPair) -> Generator[MagicMock, Any, None]:
    """Mock TokenRepository with active token and user."""
    with patch("src.db.repositories.TokenRepository.get_by_token") as mock_get_by_token:
        mock_token = MagicMock()
        mock_token.is_active = True
        mock_token.user.is_active = True
        mock_get_by_token.return_value = mock_token
        yield mock_get_by_token


@dataclasses.dataclass
class MockUser:
    is_active: bool = False


@dataclasses.dataclass
class MockToken:
    is_active: bool
    user: MockUser


@pytest.fixture
def mock_token() -> Generator[MockToken, Any, None]:
    """Mock TokenRepository with inactive token."""
    with patch("src.db.repositories.TokenRepository.get_by_token") as mock_get_by_token:
        mock_token = MockToken(is_active=False, user=MockUser(is_active=False))
        mock_get_by_token.return_value = mock_token
        yield mock_token


@pytest.fixture
def auth_token(
    mock_decode_token: MagicMock,
    mock_hash_token: MagicMock,
    mock_token: MockToken,
) -> Generator[str, Any, None]:
    yield "test-auth-token"


@pytest.fixture
def auth_test_header(auth_token: str) -> dict[str, str]:
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
    mock_settings: AppSettings,
    vendors: list[LLMVendor],
    auth_test_token: str,
) -> TestClient:
    """Create a test client with mocked settings."""
    test_app = make_app(settings=mock_settings)
    test_app.dependency_overrides = {get_app_settings: lambda: mock_settings}
    return TestClient(test_app, headers={"Authorization": f"Bearer {auth_test_token}"})


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


# Common fixtures for authentication tests
@pytest.fixture
def auth_test_settings() -> AppSettings:
    """Return test settings for authentication tests."""
    return AppSettings(
        api_token=SecretStr("test-token"),
        admin_username="test-username",
        admin_password=SecretStr("test-password"),
        secret_key=SecretStr("test-secret-key-for-auth-tests"),
        jwt_algorithm="HS256",
    )


@pytest.fixture
def mock_user() -> User:
    """Return mock user object."""
    user = MagicMock(spec=User)
    user.id = 1
    user.username = "test-user"
    user.is_active = True
    return user


#
# @pytest.fixture
# def mock_token(mock_user: User) -> Token:
#     """Return mock token object."""
#     token = MagicMock(spec=Token)
#     token.id = 1
#     token.token_hash = "test-hash"
#     token.is_active = True
#     token.user = mock_user
#     return token
#
#
# @pytest.fixture
# def mock_request() -> MagicMock:
#     """Return mock request object."""
#     request = MagicMock()
#     request.method = "GET"
#     return request
#
#
# @pytest.fixture
# def mock_session_uow() -> Generator[tuple[MagicMock, AsyncMock], None, None]:
#     """Mock SASessionUOW context manager."""
#     with patch("src.modules.auth.tokens.SASessionUOW") as mock_uow:
#         mock_session = AsyncMock()
#         mock_uow.return_value.__aenter__.return_value.session = mock_session
#         yield mock_uow, mock_session
#


@pytest.fixture
def mock_token_repository(mock_token: Token) -> Generator[tuple[MagicMock, AsyncMock], None, None]:
    """Mock TokenRepository with active token."""
    with patch("src.modules.auth.tokens.TokenRepository") as mock_repo_class:
        mock_repo = AsyncMock()
        mock_repo.get_by_token.return_value = mock_token
        mock_repo_class.return_value = mock_repo
        yield mock_repo_class, mock_repo


@pytest.fixture
def mock_token_repository_inactive_token(
    mock_user: User,
) -> Generator[tuple[MagicMock, AsyncMock], None, None]:
    """Mock TokenRepository with inactive token."""
    with patch("src.modules.auth.tokens.TokenRepository") as mock_repo_class:
        mock_repo = AsyncMock()
        mock_token = MagicMock()
        mock_token.is_active = False
        mock_repo.get_by_token.return_value = mock_token
        mock_repo_class.return_value = mock_repo
        yield mock_repo_class, mock_repo


@pytest.fixture
def mock_token_repository_inactive_user(
    mock_user: User,
) -> Generator[tuple[MagicMock, AsyncMock], None, None]:
    """Mock TokenRepository with inactive user."""
    with patch("src.modules.auth.tokens.TokenRepository") as mock_repo_class:
        mock_repo = AsyncMock()
        mock_token = MagicMock()
        mock_token.is_active = True
        mock_token.user.is_active = False
        mock_repo.get_by_token.return_value = mock_token
        mock_repo_class.return_value = mock_repo
        yield mock_repo_class, mock_repo


@pytest.fixture
def mock_token_repository_unknown_token() -> Generator[tuple[MagicMock, AsyncMock], None, None]:
    """Mock TokenRepository with unknown token."""
    with patch("src.modules.auth.tokens.TokenRepository") as mock_repo_class:
        mock_repo = AsyncMock()
        mock_repo.get_by_token.return_value = None
        mock_repo_class.return_value = mock_repo
        yield mock_repo_class, mock_repo


#
# @pytest.fixture
# def mock_make_token() -> Generator[MagicMock, None, None]:
#     """Mock make_api_token function."""
#     with patch("src.modules.auth.dependencies.make_api_token") as mock:
#         mock.return_value = MagicMock(value="test-token-value", hashed_value="test-hash")
#         yield mock
#
#
# @pytest.fixture
# def mock_decode_token() -> Generator[MagicMock, None, None]:
#     """Mock decode_api_token function."""
#     with patch("src.modules.auth.dependencies.decode_api_token") as mock:
#         mock.return_value = MagicMock(sub="test-user-id")
#         yield mock
#
#
# @pytest.fixture
# def mock_hash_token() -> Generator[MagicMock, None, None]:
#     """Mock hash_token function."""
#     with patch("src.modules.auth.dependencies.hash_token") as mock:
#         mock.return_value = "test-hash"
#         yield mock

#
# @pytest.fixture
# def mock_decode_token_no_identity() -> Generator[MagicMock, None, None]:
#     """Mock decode_api_token function with no identity."""
#     with patch("src.modules.auth.dependencies.decode_api_token") as mock:
#         mock.return_value = MagicMock(sub="")
#         yield mock
#
#
# @pytest.fixture
# def mock_decode_token_none_identity() -> Generator[MagicMock, None, None]:
#     """Mock decode_api_token function with None identity."""
#     with patch("src.modules.auth.dependencies.decode_api_token") as mock:
#         mock.return_value = MagicMock(sub=None)
#         yield mock
#
#
# @pytest.fixture
# def mock_decode_token_error() -> Generator[MagicMock, None, None]:
#     """Mock decode_api_token function that raises error."""
#     with patch("src.modules.auth.dependencies.decode_api_token") as mock:
#         mock.side_effect = Exception("Invalid token")
#         yield mock
#
#
# @pytest.fixture
# def mock_session_uow_error() -> Generator[MagicMock, None, None]:
#     """Mock SASessionUOW context manager that raises error."""
#     with patch("src.modules.auth.dependencies.SASessionUOW") as mock_uow:
#         mock_uow.side_effect = Exception("Database error")
#         yield mock_uow
