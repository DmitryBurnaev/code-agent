"""Tests for system API endpoints."""

import platform
from datetime import datetime
from typing import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import SecretStr

from src.models import LLMProvider
from src.settings import AppSettings
from src.constants import Provider
from src.main import make_app


class TestSystemAPI:
    """Tests for system API endpoints."""

    @pytest.fixture
    def mock_settings(self) -> AppSettings:
        """Return mock settings for testing."""
        return AppSettings(
            auth_api_token=SecretStr("test-token"),
            providers=[],
            http_proxy_url=None,
        )

    @pytest.fixture
    def test_app(self, mock_settings: AppSettings) -> FastAPI:
        """Return FastAPI application for testing."""
        app = make_app(settings=mock_settings)
        return app

    @pytest.fixture
    async def test_client(self, test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
        """Return async HTTP client for testing."""
        async with AsyncClient(base_url="http://test", follow_redirects=True) as client:
            yield client

    async def test_get_system_info(self, test_client: AsyncClient) -> None:
        """Test GET /system/info/ endpoint."""
        response = await test_client.get("/api/system/info/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["os_version"] == platform.platform()
        assert data["providers"] == []

    async def test_get_system_info_with_providers(
        self,
        test_client: AsyncClient,
        mock_settings: AppSettings,
    ) -> None:
        """Test GET /system/info/ endpoint with providers."""
        mock_settings.providers = [
            LLMProvider(vendor=Provider.OPENAI, api_key=SecretStr("test-key")),
            LLMProvider(vendor=Provider.ANTHROPIC, api_key=SecretStr("test-key")),
        ]
        response = await test_client.get("/api/system/info/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["os_version"] == platform.platform()
        assert data["providers"] == ["openai", "anthropic"]

    async def test_health_check(self, test_client: AsyncClient) -> None:
        """Test GET /system/health/ endpoint."""
        response = await test_client.get("/api/system/health/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert isinstance(datetime.fromisoformat(data["timestamp"]), datetime)
