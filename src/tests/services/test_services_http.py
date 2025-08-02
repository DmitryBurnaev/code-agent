"""Tests for HTTP client."""

import pytest

from src.services.http import VendorHTTPClient
from src.settings import AppSettings
from src.models import LLMVendor
from src.constants import VendorSlug
from pydantic import SecretStr

from src.tests.conftest import app_settings_test


@pytest.fixture
def mock_vendor() -> LLMVendor:
    """Return mock vendor."""
    return LLMVendor(
        slug=VendorSlug.OPENAI,
        api_key=SecretStr("test_token"),
    )


class TestAIVendorHTTPClient:
    """Tests for AIVendorHTTPClient."""

    def test_init_without_vendor(self, app_settings_test: AppSettings) -> None:
        """Test client initialization without a vendor."""
        client = VendorHTTPClient(app_settings_test)
        assert client.headers == {
            "accept": "application/json",
            "accept-encoding": "gzip, deflate",
            "connection": "keep-alive",
            "content-type": "application/json",
            "user-agent": client.headers["user-agent"],
        }

    def test_init_with_vendor(self, app_settings_test: AppSettings, mock_vendor: LLMVendor) -> None:
        """Test client initialization with vendor."""
        client = VendorHTTPClient(app_settings_test, mock_vendor)
        headers = dict(client.headers)
        assert headers["accept"] == "application/json"
        assert headers["content-type"] == "application/json"
        assert headers["authorization"] == mock_vendor.auth_headers["Authorization"]

    def test_init_with_proxy(self, app_settings_test: AppSettings) -> None:
        """Test client initialization with proxy."""
        app_settings_test.http_proxy_url = "socks5://proxy.com"
        client = VendorHTTPClient(app_settings_test)
        assert client is not None
        assert client.transport._pool is not None
        assert repr(client.transport._pool._proxy_url) == (  # type: ignore
            "URL(scheme=b'socks5', host=b'proxy.com', port=None, target=b'/')"
        )

    def test_init_with_custom_retries(self, app_settings_test: AppSettings) -> None:
        """Test client initialization with custom retries."""
        client = VendorHTTPClient(app_settings_test, retries=5)
        assert client is not None
        assert client.transport._pool._retries == 5
