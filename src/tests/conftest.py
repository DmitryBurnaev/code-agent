import os
from typing import Any, Generator, AsyncGenerator
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from starlette.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.db.session import AsyncDBConnectors
from src.application import CodeAgentAPP
from src.main import make_app
from src.modules.auth.tokens import make_api_token
from src.settings import AppSettings, get_app_settings
from src.settings.app import AdminSettings, FlagsSettings, WebSettings
from src.settings.log import LogSettings
from src.settings.db import get_db_settings
from src.constants import VendorSlug
from src.models import LLMVendor
from pydantic import SecretStr

from src.tests.mocks import MockAPIToken, MockUser, MockVendor, MockTestResponse, MockHTTPxClient

MINIMAL_ENV_VARS = {
    "API_DOCS_ENABLED": "true",
    "APP_SECRET_KEY": "test-only-jwt-signing-key-" * 3,  # Covers HS512's 64-byte minimum.
    "ADMIN_PASSWORD": "test-password",
    "VENDOR_ENCRYPTION_KEY": "test-encryption-key",
}


@pytest.fixture
def mock_user() -> MockUser:
    return MockUser(id=1, is_active=True, username="test-user")


@pytest.fixture
def app_settings_test(minimal_env_vars: None) -> AppSettings:
    return AppSettings(
        http_proxy_url=None,
        app_secret_key=SecretStr(MINIMAL_ENV_VARS["APP_SECRET_KEY"]),
        vendor_encryption_key=SecretStr("test-encryption-key"),
    )


@pytest.fixture(autouse=True)
def minimal_env_vars(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Isolate app settings while preserving the configured test database connection."""
    setting_names: set[str] = set()
    for settings_class in (AppSettings, AdminSettings, WebSettings, FlagsSettings, LogSettings):
        monkeypatch.setitem(settings_class.model_config, "env_file", None)
        prefix = settings_class.model_config.get("env_prefix", "")
        setting_names.update(f"{prefix}{name}".upper() for name in settings_class.model_fields)
    for name in list(os.environ):
        if name.upper() in setting_names:
            monkeypatch.delenv(name)
    for name, value in MINIMAL_ENV_VARS.items():
        monkeypatch.setenv(name, value)
    get_app_settings.cache_clear()
    yield
    get_app_settings.cache_clear()


@pytest.fixture(autouse=True)
async def test_app(
    app_settings_test: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[CodeAgentAPP, Any]:
    test_app = make_app(settings=app_settings_test)
    test_app.dependency_overrides[get_app_settings] = lambda: test_app.settings
    # Tests and TestClient run on separate loops; never carry pooled connections between them.
    engine = create_async_engine(get_db_settings().database_dsn, poolclass=NullPool)
    monkeypatch.setattr(
        AsyncDBConnectors(), "session_factory", async_sessionmaker(engine, expire_on_commit=False)
    )
    try:
        yield test_app
    finally:
        test_app.dependency_overrides.clear()
        await engine.dispose()


@pytest.fixture
def auth_test_token(app_settings_test: AppSettings) -> str:
    return make_api_token(expires_at=None, settings=app_settings_test).value


@pytest.fixture
def mock_request() -> MagicMock:
    request = MagicMock()
    request.method = "GET"
    return request


@pytest.fixture
def mock_db_session() -> AsyncMock:
    s = AsyncMock(spec=AsyncSession)
    s.begin = AsyncMock()
    s.__aenter__ = AsyncMock(return_value=s)
    return s


@pytest.fixture
def mock_db_session_factory(mock_db_session: AsyncMock) -> Generator[MagicMock, None]:
    _session_factory = MagicMock(spec=async_sessionmaker, return_value=mock_db_session)
    with patch("src.db.session.get_session_factory", return_value=_session_factory) as _mock:
        yield _mock


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
        mock_token = MockAPIToken(
            is_active=True,
            user=MockUser(
                id=1,
                is_active=True,
                can_access_system_api=True,
                can_use_llm=True,
                can_access_billing=True,
            ),
        )
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
