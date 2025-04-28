"""Test configuration and fixtures."""
from typing import AsyncGenerator, Generator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.main import make_app
from src.settings import AppSettings, get_settings
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
def override_get_settings(mock_settings: AppSettings) -> Generator[None, None, None]:
    """Override get_settings() for tests."""
    # Store original function
    original_get_settings = get_settings
    
    # Override get_settings
    get_settings.__wrapped__ = lambda: mock_settings
    
    yield
    
    # Restore original function
    get_settings.__wrapped__ = original_get_settings.__wrapped__


@pytest.fixture
def test_app(mock_settings: AppSettings, override_get_settings: None) -> FastAPI:
    """Return FastAPI application for testing."""
    return make_app(mock_settings)


@pytest.fixture
async def test_client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Return async HTTP client for testing."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        yield client 