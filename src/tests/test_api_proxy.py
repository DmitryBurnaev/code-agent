"""Tests for proxy API endpoints."""

import json
import asyncio
from typing import Any, Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.responses import Response, StreamingResponse
import httpx

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
        mock_proxy_service.__aexit__.assert_awaited_once_with(None, None, None)

    def test_create_chat_completion__streaming(
        self,
        client: TestClient,
        mock_proxy_service: AsyncMock,
    ) -> None:
        """Test POST /ai-proxy/chat/completions endpoint with stream=True."""
        # Create mock streaming response
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "text/event-stream"}

        # Create mock chunks for streaming
        chunks = [
            b'data: {"id": "test-1", "choices": [{"delta": {"content": "Hello"}}]}\n\n',
            b'data: {"id": "test-2", "choices": [{"delta": {"content": " World"}}]}\n\n',
            b'data: {"id": "test-3", "choices": [{"delta": {"content": "!"}}]}\n\n',
        ]

        # Create async iterator for chunks
        async def mock_aiter_bytes():
            for chunk in chunks:
                yield chunk

        mock_response.aiter_bytes = mock_aiter_bytes

        # Setup mock service
        mock_proxy_service.handle_request.return_value = StreamingResponse(
            content=mock_response.aiter_bytes(),
            status_code=200,
            headers={"Content-Type": "text/event-stream"},
        )

        # Make request
        chat_request = ChatRequest(
            messages=[Message(role="user", content="Ping")],
            model="openai__gpt-4",
            stream=True,
        )

        response = client.post(
            "/api/ai-proxy/chat/completions",
            json=chat_request.model_dump(),
            headers={"accept": "text/event-stream"},
        )

        # Verify response
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream"

        # Verify streaming content
        content = response.text
        assert "Hello" in content
        assert "World" in content
        assert "!" in content

        # Verify service was called correctly
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

        # Verify service cleanup was called
        mock_proxy_service.close.assert_awaited_once()

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

    def test_create_chat_completion__streaming_single_chunk(
        self,
        client: TestClient,
        mock_proxy_service: AsyncMock,
    ) -> None:
        """Test streaming response with single chunk."""
        # Create mock streaming response with single chunk
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "text/event-stream"}

        # Single chunk
        chunks = [
            b'data: {"id": "test-1", "choices": [{"delta": {"content": "Hello World!"}}]}\n\n',
        ]

        async def mock_aiter_bytes():
            for chunk in chunks:
                yield chunk

        mock_response.aiter_bytes = mock_aiter_bytes

        # Setup mock service
        mock_proxy_service.handle_request.return_value = StreamingResponse(
            content=mock_response.aiter_bytes(),
            status_code=200,
            headers={"Content-Type": "text/event-stream"},
        )

        # Make request
        chat_request = ChatRequest(
            messages=[Message(role="user", content="Ping")],
            model="openai__gpt-4",
            stream=True,
        )

        response = client.post(
            "/api/ai-proxy/chat/completions",
            json=chat_request.model_dump(),
            headers={"accept": "text/event-stream"},
        )

        # Verify response
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream"

        # Verify content
        content = response.text
        assert "Hello World!" in content

        # Verify service cleanup
        mock_proxy_service.close.assert_awaited_once()

    def test_create_chat_completion__streaming_empty(
        self,
        client: TestClient,
        mock_proxy_service: AsyncMock,
    ) -> None:
        """Test streaming response with empty stream."""
        # Create mock streaming response with no chunks
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "text/event-stream"}

        # Empty chunks
        chunks = []

        async def mock_aiter_bytes():
            for chunk in chunks:
                yield chunk

        mock_response.aiter_bytes = mock_aiter_bytes

        # Setup mock service
        mock_proxy_service.handle_request.return_value = StreamingResponse(
            content=mock_response.aiter_bytes(),
            status_code=200,
            headers={"Content-Type": "text/event-stream"},
        )

        # Make request
        chat_request = ChatRequest(
            messages=[Message(role="user", content="Ping")],
            model="openai__gpt-4",
            stream=True,
        )

        response = client.post(
            "/api/ai-proxy/chat/completions",
            json=chat_request.model_dump(),
            headers={"accept": "text/event-stream"},
        )

        # Verify response
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream"
        assert response.text == ""

        # Verify service cleanup
        mock_proxy_service.close.assert_awaited_once()

    def test_create_chat_completion__streaming_error(
        self,
        client: TestClient,
        mock_proxy_service: AsyncMock,
    ) -> None:
        """Test streaming response with error in stream."""
        # Create mock streaming response that raises error
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "text/event-stream"}

        async def mock_aiter_bytes():
            yield b'data: {"id": "test-1", "choices": [{"delta": {"content": "Hello"}}]}\n\n'
            raise RuntimeError("Stream error")

        mock_response.aiter_bytes = mock_aiter_bytes

        # Setup mock service
        mock_proxy_service.handle_request.return_value = StreamingResponse(
            content=mock_response.aiter_bytes(),
            status_code=200,
            headers={"Content-Type": "text/event-stream"},
        )

        # Make request
        chat_request = ChatRequest(
            messages=[Message(role="user", content="Ping")],
            model="openai__gpt-4",
            stream=True,
        )

        response = client.post(
            "/api/ai-proxy/chat/completions",
            json=chat_request.model_dump(),
            headers={"accept": "text/event-stream"},
        )

        # Verify response
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream"

        # Verify partial content
        content = response.text
        assert "Hello" in content

        # Verify service cleanup
        mock_proxy_service.close.assert_awaited_once()

    def test_create_chat_completion__streaming_headers(
        self,
        client: TestClient,
        mock_proxy_service: AsyncMock,
    ) -> None:
        """Test streaming response headers."""
        # Create mock streaming response
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Custom-Header": "test",
        }

        # Single chunk
        chunks = [
            b'data: {"id": "test-1", "choices": [{"delta": {"content": "Hello"}}]}\n\n',
        ]

        async def mock_aiter_bytes():
            for chunk in chunks:
                yield chunk

        mock_response.aiter_bytes = mock_aiter_bytes

        # Setup mock service
        mock_proxy_service.handle_request.return_value = StreamingResponse(
            content=mock_response.aiter_bytes(),
            status_code=200,
            headers=mock_response.headers,
        )

        # Make request
        chat_request = ChatRequest(
            messages=[Message(role="user", content="Ping")],
            model="openai__gpt-4",
            stream=True,
        )

        response = client.post(
            "/api/ai-proxy/chat/completions",
            json=chat_request.model_dump(),
            headers={"accept": "text/event-stream"},
        )

        # Verify response headers
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream"
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["connection"] == "keep-alive"
        assert response.headers["x-custom-header"] == "test"

        # Verify service cleanup
        mock_proxy_service.close.assert_awaited_once()

    def test_create_chat_completion__timeout(
        self,
        client: TestClient,
        mock_proxy_service: AsyncMock,
    ) -> None:
        """Test non-streaming response with timeout."""
        # Create mock response that takes too long
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}

        async def mock_content():
            await asyncio.sleep(0.3)  # Simulate long processing > client timeout
            return json.dumps({"error": "timeout"}).encode()

        mock_response.content = mock_content()

        # Setup mock service
        mock_proxy_service.handle_request.return_value = Response(
            content=mock_response.content,
            status_code=200,
            headers=mock_response.headers,
        )

        # Make request with short timeout
        chat_request = ChatRequest(
            messages=[Message(role="user", content="Ping")],
            model="openai__gpt-4",
        )

        with pytest.raises(httpx.ReadTimeout):
            client.post(
                "/api/ai-proxy/chat/completions",
                json=chat_request.model_dump(),
                timeout=0.1,  # Very short timeout < sleep time
            )

        # Verify service cleanup
        mock_proxy_service.close.assert_awaited_once()

    def test_create_chat_completion__error_status(
        self,
        client: TestClient,
        mock_proxy_service: AsyncMock,
    ) -> None:
        """Test non-streaming response with error status code."""
        # Create mock error response
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 429  # Too Many Requests
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.content = json.dumps(
            {
                "error": {
                    "message": "Rate limit exceeded",
                    "type": "rate_limit_error",
                }
            }
        ).encode()

        # Setup mock service
        mock_proxy_service.handle_request.return_value = Response(
            content=mock_response.content,
            status_code=mock_response.status_code,
            headers=mock_response.headers,
        )

        # Make request
        chat_request = ChatRequest(
            messages=[Message(role="user", content="Ping")],
            model="openai__gpt-4",
        )

        response = client.post(
            "/api/ai-proxy/chat/completions",
            json=chat_request.model_dump(),
        )

        # Verify error response
        assert response.status_code == 429
        assert response.json()["error"]["type"] == "rate_limit_error"

        # Verify service cleanup
        mock_proxy_service.close.assert_awaited_once()

    def test_create_chat_completion__streaming_timeout(
        self,
        client: TestClient,
        mock_proxy_service: AsyncMock,
    ) -> None:
        """Test streaming response with timeout."""
        # Create mock streaming response that takes too long
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "text/event-stream"}

        async def mock_aiter_bytes():
            yield b'data: {"id": "test-1", "choices": [{"delta": {"content": "Hello"}}]}\n\n'
            await asyncio.sleep(0.3)  # Simulate long processing > client timeout
            yield b'data: {"id": "test-2", "choices": [{"delta": {"content": " World"}}]}\n\n'

        mock_response.aiter_bytes = mock_aiter_bytes

        # Setup mock service
        mock_proxy_service.handle_request.return_value = StreamingResponse(
            content=mock_response.aiter_bytes(),
            status_code=200,
            headers={"Content-Type": "text/event-stream"},
        )

        # Make request with short timeout
        chat_request = ChatRequest(
            messages=[Message(role="user", content="Ping")],
            model="openai__gpt-4",
            stream=True,
        )

        with pytest.raises(httpx.ReadTimeout):
            client.post(
                "/api/ai-proxy/chat/completions",
                json=chat_request.model_dump(),
                headers={"accept": "text/event-stream"},
                timeout=0.1,  # Very short timeout < sleep time
            )

        # Verify service cleanup
        mock_proxy_service.close.assert_awaited_once()

    def test_create_chat_completion__streaming_error_status(
        self,
        client: TestClient,
        mock_proxy_service: AsyncMock,
    ) -> None:
        """Test streaming response with error status code."""
        # Create mock streaming error response
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 503  # Service Unavailable
        mock_response.headers = {"Content-Type": "text/event-stream"}

        async def mock_aiter_bytes():
            yield b'data: {"error": {"message": "Service unavailable", "type": "service_error"}}\n\n'

        mock_response.aiter_bytes = mock_aiter_bytes

        # Setup mock service
        mock_proxy_service.handle_request.return_value = StreamingResponse(
            content=mock_response.aiter_bytes(),
            status_code=503,
            headers={"Content-Type": "text/event-stream"},
        )

        # Make request
        chat_request = ChatRequest(
            messages=[Message(role="user", content="Ping")],
            model="openai__gpt-4",
            stream=True,
        )

        response = client.post(
            "/api/ai-proxy/chat/completions",
            json=chat_request.model_dump(),
            headers={"accept": "text/event-stream"},
        )

        # Verify error response
        assert response.status_code == 503
        content = response.text
        assert "service_error" in content
        assert "Service unavailable" in content

        # Verify service cleanup
        mock_proxy_service.close.assert_awaited_once()
