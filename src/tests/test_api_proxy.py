"""Tests for proxy API endpoints."""
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import SecretStr

from src.models import ChatRequest, Message, AIModel, LLMProvider
from src.settings import AppSettings
from src.constants import Provider
from src.main import make_app
from src.services.providers import ProviderService
from src.services.proxy import ProxyService, ProxyRequestData, ProxyEndpoint


class TestProxyAPI:
    """Tests for proxy API endpoints."""

    @pytest.fixture
    def mock_settings(self) -> AppSettings:
        """Return mock settings for testing."""
        return AppSettings(
            auth_api_token=SecretStr("test-token"),
            providers=[
                LLMProvider(vendor=Provider.OPENAI, api_key=SecretStr("test-key")),
                LLMProvider(vendor=Provider.ANTHROPIC, api_key=SecretStr("test-key")),
            ],
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

    @pytest.fixture
    def mock_provider_service(self) -> AsyncMock:
        """Return mock provider service."""
        service = AsyncMock(spec=ProviderService)
        service.get_list_models.return_value = [
            AIModel(id="gpt-4", name="GPT-4", type="chat", vendor="openai"),
            AIModel(id="claude-3", name="Claude 3", type="chat", vendor="anthropic"),
        ]
        return service

    @pytest.fixture
    def mock_proxy_service(self) -> AsyncMock:
        """Return mock proxy service."""
        service = AsyncMock(spec=ProxyService)
        service.handle_request.return_value = AsyncMock()
        return service

    async def test_list_models(
        self,
        test_client: AsyncClient,
        mock_provider_service: AsyncMock,
    ) -> None:
        """Test GET /ai-proxy/models endpoint."""
        with patch("src.routers.proxy.ProviderService", return_value=mock_provider_service):
            response = await test_client.get("/api/ai-proxy/models")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["id"] == "gpt-4"
            assert data[1]["id"] == "claude-3"
            mock_provider_service.get_list_models.assert_called_once()

    async def test_create_chat_completion(
        self,
        test_client: AsyncClient,
        mock_proxy_service: AsyncMock,
    ) -> None:
        """Test POST /ai-proxy/chat/completions endpoint."""
        chat_request = ChatRequest(
            messages=[Message(role="user", content="Hello!")],
            model="openai__gpt-4",
        )
        with patch("src.routers.proxy.ProxyService", return_value=mock_proxy_service):
            response = await test_client.post(
                "/api/ai-proxy/chat/completions",
                json=chat_request.model_dump(),
            )
            assert response.status_code == 200
            mock_proxy_service.handle_request.assert_called_once()
            call_args = mock_proxy_service.handle_request.call_args[0]
            assert isinstance(call_args[0], ProxyRequestData)
            assert call_args[1] == ProxyEndpoint.CHAT_COMPLETION

    async def test_cancel_chat_completion(
        self,
        test_client: AsyncClient,
        mock_proxy_service: AsyncMock,
    ) -> None:
        """Test DELETE /ai-proxy/chat/completions/{completion_id} endpoint."""
        chat_request = ChatRequest(
            messages=[Message(role="user", content="Hello!")],
            model="openai__gpt-4",
        )
        completion_id = "test-completion-id"
        with patch("src.routers.proxy.ProxyService", return_value=mock_proxy_service):
            response = await test_client.request(
                "DELETE",
                f"/api/ai-proxy/chat/completions/{completion_id}",
                json=chat_request.model_dump(),
            )
            assert response.status_code == 200
            mock_proxy_service.handle_request.assert_called_once()
            call_args = mock_proxy_service.handle_request.call_args[0]
            assert isinstance(call_args[0], ProxyRequestData)
            assert call_args[0].completion_id == completion_id
            assert call_args[1] == ProxyEndpoint.CANCEL_CHAT_COMPLETION 