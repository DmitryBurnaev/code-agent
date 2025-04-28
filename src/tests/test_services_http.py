"""Tests for HTTP client."""
import pytest
from unittest.mock import Mock

from src.services.http import AIProviderHTTPClient
from src.settings import AppSettings
from src.models import LLMProvider
from src.constants import Provider
from pydantic import SecretStr


class TestAIProviderHTTPClient:
    """Tests for AIProviderHTTPClient."""

    @pytest.fixture
    def mock_settings(self) -> AppSettings:
        """Return mock settings."""
        return AppSettings(
            auth_api_token=SecretStr("test_token"),
            providers=[],
            models_cache_ttl=60,
            http_proxy_url=None,
        )

    @pytest.fixture
    def mock_provider(self) -> LLMProvider:
        """Return mock provider."""
        return LLMProvider(
            vendor=Provider.OPENAI,
            api_key=SecretStr("test_token"),
        )

    @pytest.mark.anyio
    async def test_init_without_provider(self, mock_settings: AppSettings, override_get_settings: None) -> None:
        """Test client initialization without provider."""
        client = AIProviderHTTPClient(mock_settings)
        try:
            assert dict(client.headers) == {
                "accept": "application/json",
                "accept-encoding": "gzip, deflate",
                "connection": "keep-alive",
                "content-type": "application/json",
                "user-agent": client.headers["user-agent"],
            }
        finally:
            await client.aclose()

    @pytest.mark.anyio
    async def test_init_with_provider(
        self, mock_settings: AppSettings, mock_provider: LLMProvider, override_get_settings: None
    ) -> None:
        """Test client initialization with provider."""
        client = AIProviderHTTPClient(mock_settings, mock_provider)
        try:
            headers = dict(client.headers)
            assert headers["accept"] == "application/json"
            assert headers["content-type"] == "application/json"
            assert headers["authorization"] == "[secure]"
        finally:
            await client.aclose()

    @pytest.mark.anyio
    async def test_init_with_proxy(self, mock_settings: AppSettings, override_get_settings: None) -> None:
        """Test client initialization with proxy."""
        mock_settings.http_proxy_url = "http://proxy.com"
        client = AIProviderHTTPClient(mock_settings)
        try:
            # Just check that the client can be created with a proxy
            assert client is not None
        finally:
            await client.aclose()

    @pytest.mark.anyio
    async def test_init_with_custom_retries(self, mock_settings: AppSettings, override_get_settings: None) -> None:
        """Test client initialization with custom retries."""
        client = AIProviderHTTPClient(mock_settings, retries=5)
        try:
            # Just check that the client can be created with custom retries
            assert client is not None
        finally:
            await client.aclose() 