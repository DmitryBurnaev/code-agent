"""Tests for HTTP client."""

import pytest
from httpx import URL

from src.services.http import AIProviderHTTPClient
from src.settings import AppSettings
from src.models import LLMProvider
from src.constants import Provider
from pydantic import SecretStr

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_settings() -> AppSettings:
    """Return mock settings."""
    return AppSettings(
        auth_api_token=SecretStr("test_token"),
        providers=[],
        models_cache_ttl=60,
        http_proxy_url=None,
    )


@pytest.fixture
def mock_provider() -> LLMProvider:
    """Return mock provider."""
    return LLMProvider(
        vendor=Provider.OPENAI,
        api_key=SecretStr("test_token"),
    )


class TestAIProviderHTTPClient:
    """Tests for AIProviderHTTPClient."""

    def test_init_without_provider(self, mock_settings: AppSettings) -> None:
        """Test client initialization without a provider."""
        client = AIProviderHTTPClient(mock_settings)
        assert client.headers == {
            "accept": "application/json",
            "accept-encoding": "gzip, deflate",
            "connection": "keep-alive",
            "content-type": "application/json",
            "user-agent": client.headers["user-agent"],
        }

    def test_init_with_provider(
        self, mock_settings: AppSettings, mock_provider: LLMProvider
    ) -> None:
        """Test client initialization with provider."""
        client = AIProviderHTTPClient(mock_settings, mock_provider)
        headers = dict(client.headers)
        assert headers["accept"] == "application/json"
        assert headers["content-type"] == "application/json"
        assert headers["authorization"] == mock_provider.auth_headers["Authorization"]

    def test_init_with_proxy(self, mock_settings: AppSettings) -> None:
        """Test client initialization with proxy."""
        mock_settings.http_proxy_url = "socks5://proxy.com"
        client = AIProviderHTTPClient(mock_settings)
        assert client is not None
        assert client.transport._pool is not None
        assert repr(client.transport._pool._proxy_url) == (  # type: ignore
            "URL(scheme=b'socks5', host=b'proxy.com', port=None, target=b'/')"
        )

    def test_init_with_custom_retries(self, mock_settings: AppSettings) -> None:
        """Test client initialization with custom retries."""
        client = AIProviderHTTPClient(mock_settings, retries=5)
        assert client is not None
        assert client.transport._pool._retries == 5
