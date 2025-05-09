"""Tests for proxy API endpoints."""

import json
from typing import Any, Generator, AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr
from fastapi.testclient import TestClient
from starlette.responses import Response, StreamingResponse

from src.constants import Provider
from src.settings import AppSettings
from src.services.providers import ProviderService
from src.models import ChatRequest, Message, AIModel, LLMProvider
from src.services.proxy import ProxyService, ProxyRequestData, ProxyEndpoint


@pytest.fixture
def mock_provider_service() -> Generator[AsyncMock, Any, None]:
    """Return mock provider service."""
    mock_service = AsyncMock(spec=ProviderService)
    mock_service.get_list_models.return_value = [
        AIModel(id="openai__gpt-4", vendor="openai", vendor_id="gpt-4"),
        AIModel(id="anthropic__claude-3", vendor="anthropic", vendor_id="claude-3"),
    ]
    with patch("src.routers.proxy.ProviderService", return_value=mock_service):
        yield mock_service


@pytest.fixture
def mock_proxy_service() -> Generator[AsyncMock, Any, None]:
    """Return mock proxy service."""
    service = AsyncMock(spec=ProxyService)
    service.handle_request.return_value = AsyncMock()
    with patch("src.routers.proxy.ProxyService", return_value=service):
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
            {"id": "openai__gpt-4", "vendor": "openai", "vendor_id": "gpt-4"},
            {"id": "anthropic__claude-3", "vendor": "anthropic", "vendor_id": "claude-3"},
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
        mock_proxy_service.__aexit__.assert_awaited_once_with(None, None, None)

    @pytest.mark.parametrize(
        "stream_words",
        (
            ["Hello", "World", "!"],
            ["Hello"],
            [],
        ),
    )
    def test_create_chat_completion__streaming(
        self, client: TestClient, mock_proxy_service: AsyncMock, stream_words: list[str]
    ) -> None:
        """Test POST /ai-proxy/chat/completions endpoint with stream=True."""
        chat_request = ChatRequest(
            messages=[Message(role="user", content="Ping")],
            model="openai__gpt-4",
            stream=True,
        )

        async def mock_aiter_bytes() -> AsyncIterator[bytes]:
            for i, word in enumerate(stream_words):
                yield "data: {}\n\n".format(
                    {
                        "id": f"test-{i}",
                        "choices": [{"delta": {"content": word}}],
                    }
                ).encode()

        mock_proxy_service.handle_request.return_value = StreamingResponse(
            media_type="application/json",
            content=mock_aiter_bytes(),
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
            status_code=200,
        )

        response = client.post(
            "/api/ai-proxy/chat/completions",
            json=chat_request.model_dump(),
            headers={"accept": "text/event-stream"},
        )

        # Verify response
        assert response.status_code == 200
        assert response.headers == {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }

        # Verify streaming content
        content = response.text
        for word in stream_words:
            assert word in content, "Word '{}' not found in response".format(word)

        # Verify service was called correctly
        mock_proxy_service.handle_request.assert_awaited_once_with(
            ProxyRequestData(
                method="POST",
                headers={
                    "host": "testserver",
                    "accept-encoding": "gzip, deflate",
                    "connection": "keep-alive",
                    "authorization": "Bearer test-auth-token",
                    "user-agent": "testclient",
                    "accept": "text/event-stream",
                    "content-length": "85",
                    "content-type": "application/json",
                },
                query_params={},
                body=chat_request,
            ),
            ProxyEndpoint.CHAT_COMPLETION,
        )

        mock_proxy_service.__aexit__.assert_awaited_once_with(None, None, None)

    def test_cancel_chat_completion(
        self,
        client: TestClient,
        mock_proxy_service: AsyncMock,
    ) -> None:
        """Test DELETE /ai-proxy/chat/completions/{completion_id} endpoint."""
        completion_id = "test-completion-id"
        mock_proxy_service.handle_request.return_value = Response(
            media_type="application/json",
            content=json.dumps(
                {
                    "id": completion_id,
                    "object": "chat.completion",
                }
            ),
            headers={"content-type": "application/json"},
            status_code=200,
        )
        response = client.delete(f"/api/ai-proxy/chat/completions/{completion_id}")

        assert response.status_code == 200
        mock_proxy_service.handle_request.assert_awaited_once_with(
            ProxyRequestData(
                method="DELETE",
                headers={
                    "host": "testserver",
                    "accept": "*/*",
                    "accept-encoding": "gzip, deflate",
                    "connection": "keep-alive",
                    "authorization": "Bearer test-auth-token",
                    "user-agent": "testclient",
                },
                query_params={},
                body=None,
                completion_id=completion_id,
            ),
            ProxyEndpoint.CANCEL_CHAT_COMPLETION,
        )
        mock_proxy_service.__aexit__.assert_awaited_once_with(None, None, None)
