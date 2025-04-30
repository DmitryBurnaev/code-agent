"""Tests for proxy API endpoints."""

import json
from typing import Any, Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.responses import Response

from src.models import ChatRequest, Message, AIModel, LLMProvider
from src.settings import AppSettings
from src.constants import Provider
from src.services.providers import ProviderService
from src.services.proxy import ProxyService, ProxyRequestData, ProxyEndpoint

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_provider_service() -> Generator[AsyncMock, Any, None]:
    """Return mock provider service."""
    mock_service = AsyncMock(spec=ProviderService)
    mock_service.get_list_models.return_value = [
        AIModel(id="gpt-4", name="GPT-4", type="chat", vendor="openai"),
        AIModel(id="claude-3", name="Claude 3", type="chat", vendor="anthropic"),
    ]
    with patch("src.routers.proxy.ProviderService", return_value=mock_service):
        yield mock_service


@pytest.fixture
def mock_proxy_service() -> Generator[AsyncMock, Any, None]:
    """Return mock proxy service."""
    service = AsyncMock(spec=ProxyService)
    service.handle_request.return_value = AsyncMock()
    with patch("src.routers.proxy.ProxyService.__aenter__", return_value=service):
        yield service


@pytest.fixture
def mock_settings() -> AppSettings:
    """Return mock settings for testing."""
    return AppSettings(
        auth_api_token=SecretStr("test-token"),
        providers=[
            LLMProvider(vendor=Provider.OPENAI, api_key=SecretStr("test-key")),
            LLMProvider(vendor=Provider.ANTHROPIC, api_key=SecretStr("test-key")),
        ],
        http_proxy_url=None,
    )


class TestProxyAPI:
    """Tests for proxy API endpoints."""

    def test_list_models(self, client: TestClient, mock_provider_service: AsyncMock) -> None:
        """Test GET /ai-proxy/models endpoint."""
        response = client.get("/api/ai-proxy/models")
        assert response.status_code == 200
        data = response.json()
        assert data == [
            {"id": "gpt-4", "name": "GPT-4", "type": "chat", "vendor": "openai"},
            {"id": "claude-3", "name": "Claude 3", "type": "chat", "vendor": "anthropic"},
        ]
        mock_provider_service.get_list_models.assert_awaited_once()

    def test_create_chat_completion(
        self,
        client: TestClient,
        mock_proxy_service: AsyncMock,
    ) -> None:
        """Test POST /ai-proxy/chat/completions endpoint."""
        chat_request = ChatRequest(
            messages=[Message(role="user", content="Ping")],
            model="openai__gpt-4",
        )
        mocked_response = {
            "id": "test-completion-id",
            "choices": [{"message": {"content": "Pong"}}],
        }
        mock_proxy_service.handle_request.return_value = Response(
            media_type="application/json",
            content=json.dumps(mocked_response),
            headers={"content-type": "application/json"},
            status_code=200,
        )
        response = client.post(
            "/api/ai-proxy/chat/completions",
            json=chat_request.model_dump(),
        )
        assert response.status_code == 200
        assert response.json() == {
            "id": "test-completion-id",
            "choices": [{"message": {"content": "Pong"}}],
        }
        mock_proxy_service.handle_request.assert_awaited_once_with(
            ProxyRequestData(
                method="POST",
                headers={
                    "host": "testserver",
                    "accept": "*/*",
                    "accept-encoding": "gzip, deflate",
                    "connection": "keep-alive",
                    "authorization": "Bearer test-auth-token",
                    "user-agent": "testclient",
                    "content-length": "86",
                    "content-type": "application/json",
                },
                query_params={},
                body=chat_request,
            ),
            ProxyEndpoint.CHAT_COMPLETION,
        )

    def test_create_chat_completion__streaming(
        self,
        client: TestClient,
        mock_proxy_service: AsyncMock,
    ) -> None:
        """Test POST /ai-proxy/chat/completions endpoint with stream=True."""
        raise AssertionError()

    def test_cancel_chat_completion(
        self,
        client: TestClient,
        mock_proxy_service: AsyncMock,
    ) -> None:
        """Test DELETE /ai-proxy/chat/completions/{completion_id} endpoint."""
        chat_request = ChatRequest(
            messages=[Message(role="user", content="Hello!")],
            model="openai__gpt-4",
        )
        completion_id = "test-completion-id"
        response = client.request(
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
