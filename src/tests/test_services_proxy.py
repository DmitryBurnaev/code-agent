"""Tests for proxy service."""

from unittest.mock import Mock, AsyncMock

import pytest
import httpx
from fastapi import Response
from fastapi.responses import StreamingResponse

from src.services.proxy import ProxyService, ProxyRequestData, ProxyEndpoint
from src.models import ChatRequest, LLMProvider, Message
from src.settings import AppSettings
from src.constants import Provider
from src.exceptions import ProviderProxyError
from pydantic import SecretStr


class TestProxyService:
    """Tests for ProxyService."""

    @pytest.fixture
    def mock_settings(self) -> AppSettings:
        """Return mock settings."""
        return AppSettings(
            auth_api_token=SecretStr("test-token"),
            providers=[
                LLMProvider(vendor=Provider.OPENAI, api_key=SecretStr("test-key")),
                LLMProvider(vendor=Provider.ANTHROPIC, api_key=SecretStr("test-key")),
            ],
            models_cache_ttl=60,
            http_proxy_url=None,
        )

    @pytest.fixture
    def mock_request_data(self) -> ProxyRequestData:
        """Return mock request data."""
        return ProxyRequestData(
            method="POST",
            headers={"Content-Type": "application/json"},
            query_params={},
            body=ChatRequest(
                messages=[Message(role="user", content="Hello")],
                model="openai__gpt-4",
                stream=False,
            ),
        )

    @pytest.fixture
    def mock_streaming_request_data(self) -> ProxyRequestData:
        """Return mock streaming request data."""
        return ProxyRequestData(
            method="POST",
            headers={"Content-Type": "application/json"},
            query_params={},
            body=ChatRequest(
                messages=[Message(role="user", content="Hello")],
                model="openai__gpt-4",
                stream=True,
            ),
        )

    @pytest.fixture
    def mock_http_client(self) -> AsyncMock:
        """Return mock HTTP client."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.build_request = Mock(return_value=Mock(spec=httpx.Request))
        mock_client.send = AsyncMock()
        return mock_client

    @pytest.mark.anyio
    async def test_handle_request_regular(
        self,
        mock_settings: AppSettings,
        mock_request_data: ProxyRequestData,
        mock_http_client: AsyncMock,
    ) -> None:
        """Test handling regular (non-streaming) request."""
        async with ProxyService(mock_settings) as service:
            # Replace service's HTTP client with our mock
            service._http_client = mock_http_client

            # Mock response
            mock_response = AsyncMock(spec=httpx.Response)
            mock_response.status_code = 200
            mock_response.content = b'{"response": "Hello!"}'
            mock_response.headers = {"Content-Type": "application/json"}
            mock_http_client.send.return_value = mock_response

            # Handle request
            response = await service.handle_request(
                mock_request_data, ProxyEndpoint.CHAT_COMPLETION
            )

            # Verify response
            assert isinstance(response, Response)
            assert response.status_code == 200
            assert response.body == b'{"response": "Hello!"}'
            assert response.headers["Content-Type"] == "application/json"

    @pytest.mark.anyio
    async def test_handle_request_streaming(
        self,
        mock_settings: AppSettings,
        mock_streaming_request_data: ProxyRequestData,
        mock_http_client: AsyncMock,
    ) -> None:
        """Test handling streaming request."""
        async with ProxyService(mock_settings) as service:
            # Replace service's HTTP client with our mock
            service._http_client = mock_http_client

            # Mock response
            mock_response = AsyncMock(spec=httpx.Response)
            mock_response.status_code = 200
            mock_response.headers = {"Content-Type": "text/event-stream"}
            mock_http_client.send.return_value = mock_response

            # Handle request
            response = await service.handle_request(
                mock_streaming_request_data, ProxyEndpoint.CHAT_COMPLETION
            )

            # Verify response
            assert isinstance(response, StreamingResponse)
            assert response.status_code == 200
            assert response.headers["Content-Type"] == "text/event-stream"
            assert response.headers["Cache-Control"] == "no-cache"
            assert response.headers["Connection"] == "keep-alive"

    @pytest.mark.anyio
    async def test_handle_request_no_body(self, mock_settings: AppSettings) -> None:
        """Test handling request without body."""
        async with ProxyService(mock_settings) as service:
            request_data = ProxyRequestData(
                method="POST",
                headers={},
                query_params={},
                body=None,
            )

            # Handle request (should raise error)
            with pytest.raises(ProviderProxyError, match="Request body is required"):
                await service.handle_request(request_data, ProxyEndpoint.CHAT_COMPLETION)

    @pytest.mark.anyio
    async def test_handle_request_invalid_model(
        self, mock_settings: AppSettings, mock_request_data: ProxyRequestData
    ) -> None:
        """Test handling request with invalid model format."""
        async with ProxyService(mock_settings) as service:
            # Invalid model format
            mock_request_data.body.model = "invalid-model"  # type: ignore

            # Handle request (should raise error)
            with pytest.raises(ProviderProxyError, match="Invalid model format"):
                await service.handle_request(mock_request_data, ProxyEndpoint.CHAT_COMPLETION)

    @pytest.mark.anyio
    async def test_handle_request_unknown_provider(
        self, mock_settings: AppSettings, mock_request_data: ProxyRequestData
    ) -> None:
        """Test handling request with unknown provider."""
        async with ProxyService(mock_settings) as service:
            # Unknown provider
            mock_request_data.body.model = "unknown__gpt-4"  # type: ignore

            # Handle request (should raise error)
            with pytest.raises(ProviderProxyError, match="Unable to extract provider"):
                await service.handle_request(mock_request_data, ProxyEndpoint.CHAT_COMPLETION)

    @pytest.mark.anyio
    async def test_handle_request_cancellation(
        self,
        mock_settings: AppSettings,
        mock_request_data: ProxyRequestData,
        mock_http_client: AsyncMock,
    ) -> None:
        """Test handling cancellation request."""
        async with ProxyService(mock_settings) as service:
            # Replace service's HTTP client with our mock
            service._http_client = mock_http_client

            # Add completion ID
            mock_request_data.completion_id = "test-completion"

            # Mock response
            mock_response = AsyncMock(spec=httpx.Response)
            mock_response.status_code = 200
            mock_response.content = b'{"status": "cancelled"}'
            mock_response.headers = {"Content-Type": "application/json"}
            mock_http_client.send.return_value = mock_response

            # Handle request
            response = await service.handle_request(
                mock_request_data, ProxyEndpoint.CANCEL_CHAT_COMPLETION
            )

            # Verify response
            assert isinstance(response, Response)
            assert response.status_code == 200
            assert response.body == b'{"status": "cancelled"}'

    @pytest.mark.anyio
    async def test_handle_request_cancellation_no_id(
        self, mock_settings: AppSettings, mock_request_data: ProxyRequestData
    ) -> None:
        """Test handling cancellation request without completion ID."""
        async with ProxyService(mock_settings) as service:
            # Handle request (should raise error)
            with pytest.raises(ProviderProxyError, match="completion_id is required"):
                await service.handle_request(
                    mock_request_data, ProxyEndpoint.CANCEL_CHAT_COMPLETION
                )


class TestIdeas:

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
