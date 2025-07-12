"""Tests for HTTP client."""

import pytest

from src.services.http import VendorHTTPClient
from src.settings import AppSettings
from src.models import LLMVendor
from src.constants import VendorSlug
from pydantic import SecretStr


@pytest.fixture
def mock_settings() -> AppSettings:
    """Return mock settings."""
    return AppSettings(
        api_token=SecretStr("test_token"),
        http_proxy_url=None,
    )


@pytest.fixture
def mock_vendor() -> LLMVendor:
    """Return mock vendor."""
    return LLMVendor(
        slug=VendorSlug.OPENAI,
        api_key=SecretStr("test_token"),
    )


class TestAIVendorHTTPClient:
    """Tests for AIVendorHTTPClient."""

    def test_init_without_vendor(self, mock_settings: AppSettings) -> None:
        """Test client initialization without a vendor."""
        client = VendorHTTPClient(mock_settings)
        assert client.headers == {
            "accept": "application/json",
            "accept-encoding": "gzip, deflate",
            "connection": "keep-alive",
            "content-type": "application/json",
            "user-agent": client.headers["user-agent"],
        }

    def test_init_with_vendor(self, mock_settings: AppSettings, mock_vendor: LLMVendor) -> None:
        """Test client initialization with vendor."""
        client = VendorHTTPClient(mock_settings, mock_vendor)
        headers = dict(client.headers)
        assert headers["accept"] == "application/json"
        assert headers["content-type"] == "application/json"
        assert headers["authorization"] == mock_vendor.auth_headers["Authorization"]

    def test_init_with_proxy(self, mock_settings: AppSettings) -> None:
        """Test client initialization with proxy."""
        mock_settings.http_proxy_url = "socks5://proxy.com"
        client = VendorHTTPClient(mock_settings)
        assert client is not None
        assert client.transport._pool is not None
        assert repr(client.transport._pool._proxy_url) == (  # type: ignore
            "URL(scheme=b'socks5', host=b'proxy.com', port=None, target=b'/')"
        )

    def test_init_with_custom_retries(self, mock_settings: AppSettings) -> None:
        """Test client initialization with custom retries."""
        client = VendorHTTPClient(mock_settings, retries=5)
        assert client is not None
        assert client.transport._pool._retries == 5
