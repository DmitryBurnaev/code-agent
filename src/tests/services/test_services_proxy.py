"""Tests for proxy service."""

from typing import Any, AsyncGenerator, AsyncIterator
from unittest.mock import Mock, AsyncMock

import pytest
import httpx
import json
from fastapi import Response
from fastapi.responses import StreamingResponse

from src.constants import Vendor
from src.services.proxy import ProxyService, ProxyRequestData, ProxyEndpoint
from src.models import ChatRequest, Message
from src.settings import AppSettings
from src.exceptions import ProviderProxyError

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_request_data() -> ProxyRequestData:
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
def mock_streaming_request_data() -> ProxyRequestData:
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
def mock_response() -> AsyncMock:
    """Return mock response."""
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.content = b'{"response": "Hello!"}'
    mock_response.headers = {"Content-Type": "application/json"}
    return mock_response


@pytest.fixture
def mock_http_client(mock_response: AsyncMock) -> AsyncMock:
    """Return mock HTTP client."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.build_request = Mock(return_value=Mock(spec=httpx.Request))
    mock_client.send = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.fixture
async def proxy_service(
    mock_settings: AppSettings, mock_http_client: AsyncMock
) -> AsyncGenerator[ProxyService, Any]:
    """Return proxy service instance."""
    async with ProxyService(mock_settings, mock_http_client) as service:
        yield service


class TestProxyService:
    """Tests for ProxyService."""

    async def test_handle_request_regular(
        self,
        mock_request_data: ProxyRequestData,
        proxy_service: ProxyService,
        mock_response: AsyncMock,
    ) -> None:
        """Test handling regular (non-streaming) request."""
        mock_response.content = b'{"response": "Hello!"}'

        response = await proxy_service.handle_request(
            mock_request_data, ProxyEndpoint.CHAT_COMPLETION
        )

        assert isinstance(response, Response)
        assert response.status_code == 200
        assert response.body == b'{"response": "Hello!"}'
        assert response.headers["Content-Type"] == "application/json"

    async def test_handle_request_streaming(
        self,
        mock_streaming_request_data: ProxyRequestData,
        proxy_service: ProxyService,
        mock_response: AsyncMock,
    ) -> None:
        """Test handling streaming request."""
        mock_response.content = b'{"response": "Hello!"}'

        response = await proxy_service.handle_request(
            mock_streaming_request_data, ProxyEndpoint.CHAT_COMPLETION
        )

        assert isinstance(response, StreamingResponse)
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "text/event-stream"
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["Connection"] == "keep-alive"
        # assert response.body == b'{"response": "Hello!"}'
        # assert list(await response.body_iterator) == "None"

    async def test_handle_request_no_body(
        self,
        proxy_service: ProxyService,
    ) -> None:
        """Test handling request without body."""
        request_data = ProxyRequestData(
            method="POST",
            headers={},
            query_params={},
            body=None,
        )

        with pytest.raises(ProviderProxyError, match="Request body is required"):
            await proxy_service.handle_request(request_data, ProxyEndpoint.CHAT_COMPLETION)

    async def test_handle_request_invalid_model(
        self,
        mock_request_data: ProxyRequestData,
        proxy_service: ProxyService,
    ) -> None:
        """Test handling request with an invalid model format."""
        mock_request_data.body.model = "invalid-model"  # type: ignore

        with pytest.raises(ProviderProxyError, match="Invalid model format"):
            await proxy_service.handle_request(mock_request_data, ProxyEndpoint.CHAT_COMPLETION)

    async def test_handle_request_unknown_provider(
        self,
        mock_request_data: ProxyRequestData,
        proxy_service: ProxyService,
    ) -> None:
        """Test handling request with an unknown provider."""
        mock_request_data.body.model = "unknown__gpt-4"  # type: ignore

        with pytest.raises(ProviderProxyError, match="Unable to extract provider"):
            await proxy_service.handle_request(mock_request_data, ProxyEndpoint.CHAT_COMPLETION)

    async def test_handle_request_cancellation(
        self,
        mock_request_data: ProxyRequestData,
        proxy_service: ProxyService,
        mock_http_client: AsyncMock,
        mock_response: AsyncMock,
    ) -> None:
        """Test handling cancellation request."""
        completion_id = "test-completion"
        proxy_service._cache.set(completion_id, Vendor.OPENAI)

        mock_response.content = b'{"status": "cancelled"}'
        mock_http_client.send.return_value = mock_response

        mock_request_data.completion_id = completion_id
        response = await proxy_service.handle_request(
            mock_request_data, ProxyEndpoint.CANCEL_CHAT_COMPLETION
        )

        assert isinstance(response, Response)
        assert response.status_code == 200
        assert response.body == b'{"status": "cancelled"}'

    async def test_handle_request_cancellation_no_id(
        self,
        mock_request_data: ProxyRequestData,
        proxy_service: ProxyService,
    ) -> None:
        """Test handling cancellation request without completion ID."""
        with pytest.raises(ProviderProxyError, match="completion_id is required"):
            await proxy_service.handle_request(
                mock_request_data, ProxyEndpoint.CANCEL_CHAT_COMPLETION
            )

    async def test_handle_request_streaming_error(
        self,
        mock_streaming_request_data: ProxyRequestData,
        proxy_service: ProxyService,
        mock_response: AsyncMock,
    ) -> None:
        """Test handling streaming request with error in stream."""

        async def mock_aiter_bytes() -> AsyncIterator[bytes]:
            yield b'data: {"id": "test-1", "choices": [{"delta": {"content": "Hello"}}]}\n\n'
            raise RuntimeError("Stream error")

        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.headers = {"Content-Type": "text/event-stream"}

        response = await proxy_service.handle_request(
            mock_streaming_request_data, ProxyEndpoint.CHAT_COMPLETION
        )

        assert isinstance(response, StreamingResponse)
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "text/event-stream"

    async def test_handle_request_streaming_empty(
        self,
        mock_streaming_request_data: ProxyRequestData,
        proxy_service: ProxyService,
        mock_response: AsyncMock,
    ) -> None:
        """Test handling streaming request with empty stream."""

        async def mock_aiter_bytes():
            if False:  # This ensures the generator is async
                yield b""

        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.headers = {"Content-Type": "text/event-stream"}

        response = await proxy_service.handle_request(
            mock_streaming_request_data, ProxyEndpoint.CHAT_COMPLETION
        )

        assert isinstance(response, StreamingResponse)
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "text/event-stream"

    async def test_handle_request_streaming_headers(
        self,
        mock_streaming_request_data: ProxyRequestData,
        proxy_service: ProxyService,
        mock_response: AsyncMock,
    ) -> None:
        """Test handling streaming request with custom headers."""
        mock_response.headers = {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Custom-Header": "test",
        }

        response = await proxy_service.handle_request(
            mock_streaming_request_data, ProxyEndpoint.CHAT_COMPLETION
        )

        assert isinstance(response, StreamingResponse)
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "text/event-stream"
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["Connection"] == "keep-alive"
        assert response.headers["X-Custom-Header"] == "test"

    async def test_handle_request_timeout(
        self,
        mock_request_data: ProxyRequestData,
        proxy_service: ProxyService,
        mock_http_client: AsyncMock,
    ) -> None:
        """Test handling request with timeout."""
        # Set timeout for the request
        mock_request_data.timeout = 0.1
        mock_http_client.send.side_effect = httpx.TimeoutException("Request timed out")

        with pytest.raises(ProviderProxyError, match="Request timeout"):
            await proxy_service.handle_request(mock_request_data, ProxyEndpoint.CHAT_COMPLETION)

    async def test_handle_request_streaming_timeout(
        self,
        mock_streaming_request_data: ProxyRequestData,
        proxy_service: ProxyService,
        mock_http_client: AsyncMock,
    ) -> None:
        """Test handling streaming request with timeout."""
        # Set timeout for the request
        mock_streaming_request_data.timeout = 0.1
        mock_http_client.send.side_effect = httpx.TimeoutException("Stream timed out")

        with pytest.raises(ProviderProxyError, match="Stream timeout"):
            await proxy_service.handle_request(
                mock_streaming_request_data, ProxyEndpoint.CHAT_COMPLETION
            )

    async def test_handle_request_error_status(
        self,
        mock_request_data: ProxyRequestData,
        proxy_service: ProxyService,
        mock_response: AsyncMock,
    ) -> None:
        """Test handling request with error status code."""
        mock_response.status_code = 429  # Too Many Requests
        mock_response.content = json.dumps(
            {
                "error": {
                    "message": "Rate limit exceeded",
                    "type": "rate_limit_error",
                }
            }
        ).encode()
        mock_response.headers = {"Content-Type": "application/json"}

        response = await proxy_service.handle_request(
            mock_request_data, ProxyEndpoint.CHAT_COMPLETION
        )

        assert isinstance(response, Response)
        assert response.status_code == 429
        assert response.headers["Content-Type"] == "application/json"
        assert json.loads(response.body)["error"]["type"] == "rate_limit_error"

    async def test_handle_request_streaming_error_status(
        self,
        mock_streaming_request_data: ProxyRequestData,
        proxy_service: ProxyService,
        mock_response: AsyncMock,
    ) -> None:
        """Test handling streaming request with error status code."""
        mock_response.status_code = 503  # Service Unavailable
        mock_response.headers = {"Content-Type": "text/event-stream"}

        async def mock_aiter_bytes():
            yield b'data: {"error": {"message": "Service unavailable", "type": "service_error"}}\n\n'

        mock_response.aiter_bytes = mock_aiter_bytes

        response = await proxy_service.handle_request(
            mock_streaming_request_data, ProxyEndpoint.CHAT_COMPLETION
        )

        assert isinstance(response, StreamingResponse)
        assert response.status_code == 503
        assert response.headers["Content-Type"] == "text/event-stream"


#
# class TestIdeas:
#
#     def test_create_chat_completion__streaming_single_chunk(
#         self,
#         client: TestClient,
#         mock_proxy_service: AsyncMock,
#     ) -> None:
#         """Test streaming response with single chunk."""
#         # Create mock streaming response with single chunk
#         mock_response = AsyncMock(spec=httpx.Response)
#         mock_response.status_code = 200
#         mock_response.headers = {"Content-Type": "text/event-stream"}
#
#         # Single chunk
#         chunks = [
#             b'data: {"id": "test-1", "choices": [{"delta": {"content": "Hello World!"}}]}\n\n',
#         ]
#
#         async def mock_aiter_bytes():
#             for chunk in chunks:
#                 yield chunk
#
#         mock_response.aiter_bytes = mock_aiter_bytes
#
#         # Setup mock service
#         mock_proxy_service.handle_request.return_value = StreamingResponse(
#             content=mock_response.aiter_bytes(),
#             status_code=200,
#             headers={"Content-Type": "text/event-stream"},
#         )
#
#         # Make request
#         chat_request = ChatRequest(
#             messages=[Message(role="user", content="Ping")],
#             model="openai__gpt-4",
#             stream=True,
#         )
#
#         response = client.post(
#             "/api/ai-proxy/chat/completions",
#             json=chat_request.model_dump(),
#             headers={"accept": "text/event-stream"},
#         )
#
#         # Verify response
#         assert response.status_code == 200
#         assert response.headers["content-type"] == "text/event-stream"
#
#         # Verify content
#         content = response.text
#         assert "Hello World!" in content
#
#         # Verify service cleanup
#         mock_proxy_service.close.assert_awaited_once()
#
#     def test_create_chat_completion__streaming_empty(
#         self,
#         client: TestClient,
#         mock_proxy_service: AsyncMock,
#     ) -> None:
#         """Test streaming response with empty stream."""
#         # Create mock streaming response with no chunks
#         mock_response = AsyncMock(spec=httpx.Response)
#         mock_response.status_code = 200
#         mock_response.headers = {"Content-Type": "text/event-stream"}
#
#         # Empty chunks
#         chunks = []
#
#         async def mock_aiter_bytes():
#             for chunk in chunks:
#                 yield chunk
#
#         mock_response.aiter_bytes = mock_aiter_bytes
#
#         # Setup mock service
#         mock_proxy_service.handle_request.return_value = StreamingResponse(
#             content=mock_response.aiter_bytes(),
#             status_code=200,
#             headers={"Content-Type": "text/event-stream"},
#         )
#
#         # Make request
#         chat_request = ChatRequest(
#             messages=[Message(role="user", content="Ping")],
#             model="openai__gpt-4",
#             stream=True,
#         )
#
#         response = client.post(
#             "/api/ai-proxy/chat/completions",
#             json=chat_request.model_dump(),
#             headers={"accept": "text/event-stream"},
#         )
#
#         # Verify response
#         assert response.status_code == 200
#         assert response.headers["content-type"] == "text/event-stream"
#         assert response.text == ""
#
#         # Verify service cleanup
#         mock_proxy_service.close.assert_awaited_once()
#
#     def test_create_chat_completion__streaming_error(
#         self,
#         client: TestClient,
#         mock_proxy_service: AsyncMock,
#     ) -> None:
#         """Test streaming response with error in stream."""
#         # Create mock streaming response that raises error
#         mock_response = AsyncMock(spec=httpx.Response)
#         mock_response.status_code = 200
#         mock_response.headers = {"Content-Type": "text/event-stream"}
#
#         async def mock_aiter_bytes():
#             yield b'data: {"id": "test-1", "choices": [{"delta": {"content": "Hello"}}]}\n\n'
#             raise RuntimeError("Stream error")
#
#         mock_response.aiter_bytes = mock_aiter_bytes
#
#         # Setup mock service
#         mock_proxy_service.handle_request.return_value = StreamingResponse(
#             content=mock_response.aiter_bytes(),
#             status_code=200,
#             headers={"Content-Type": "text/event-stream"},
#         )
#
#         # Make request
#         chat_request = ChatRequest(
#             messages=[Message(role="user", content="Ping")],
#             model="openai__gpt-4",
#             stream=True,
#         )
#
#         response = client.post(
#             "/api/ai-proxy/chat/completions",
#             json=chat_request.model_dump(),
#             headers={"accept": "text/event-stream"},
#         )
#
#         # Verify response
#         assert response.status_code == 200
#         assert response.headers["content-type"] == "text/event-stream"
#
#         # Verify partial content
#         content = response.text
#         assert "Hello" in content
#
#         # Verify service cleanup
#         mock_proxy_service.close.assert_awaited_once()
#
#     def test_create_chat_completion__streaming_headers(
#         self,
#         client: TestClient,
#         mock_proxy_service: AsyncMock,
#     ) -> None:
#         """Test streaming response headers."""
#         # Create mock streaming response
#         mock_response = AsyncMock(spec=httpx.Response)
#         mock_response.status_code = 200
#         mock_response.headers = {
#             "Content-Type": "text/event-stream",
#             "Cache-Control": "no-cache",
#             "Connection": "keep-alive",
#             "X-Custom-Header": "test",
#         }
#
#         # Single chunk
#         chunks = [
#             b'data: {"id": "test-1", "choices": [{"delta": {"content": "Hello"}}]}\n\n',
#         ]
#
#         async def mock_aiter_bytes():
#             for chunk in chunks:
#                 yield chunk
#
#         mock_response.aiter_bytes = mock_aiter_bytes
#
#         # Setup mock service
#         mock_proxy_service.handle_request.return_value = StreamingResponse(
#             content=mock_response.aiter_bytes(),
#             status_code=200,
#             headers=mock_response.headers,
#         )
#
#         # Make request
#         chat_request = ChatRequest(
#             messages=[Message(role="user", content="Ping")],
#             model="openai__gpt-4",
#             stream=True,
#         )
#
#         response = client.post(
#             "/api/ai-proxy/chat/completions",
#             json=chat_request.model_dump(),
#             headers={"accept": "text/event-stream"},
#         )
#
#         # Verify response headers
#         assert response.status_code == 200
#         assert response.headers["content-type"] == "text/event-stream"
#         assert response.headers["cache-control"] == "no-cache"
#         assert response.headers["connection"] == "keep-alive"
#         assert response.headers["x-custom-header"] == "test"
#
#         # Verify service cleanup
#         mock_proxy_service.close.assert_awaited_once()
#
#     def test_create_chat_completion__timeout(
#         self,
#         client: TestClient,
#         mock_proxy_service: AsyncMock,
#     ) -> None:
#         """Test non-streaming response with timeout."""
#         # Create mock response that takes too long
#         mock_response = AsyncMock(spec=httpx.Response)
#         mock_response.status_code = 200
#         mock_response.headers = {"Content-Type": "application/json"}
#
#         async def mock_content():
#             await asyncio.sleep(0.3)  # Simulate long processing > client timeout
#             return json.dumps({"error": "timeout"}).encode()
#
#         mock_response.content = mock_content()
#
#         # Setup mock service
#         mock_proxy_service.handle_request.return_value = Response(
#             content=mock_response.content,
#             status_code=200,
#             headers=mock_response.headers,
#         )
#
#         # Make request with short timeout
#         chat_request = ChatRequest(
#             messages=[Message(role="user", content="Ping")],
#             model="openai__gpt-4",
#         )
#
#         with pytest.raises(httpx.ReadTimeout):
#             client.post(
#                 "/api/ai-proxy/chat/completions",
#                 json=chat_request.model_dump(),
#                 timeout=0.1,  # Very short timeout < sleep time
#             )
#
#         # Verify service cleanup
#         mock_proxy_service.close.assert_awaited_once()
#
#     def test_create_chat_completion__error_status(
#         self,
#         client: TestClient,
#         mock_proxy_service: AsyncMock,
#     ) -> None:
#         """Test non-streaming response with error status code."""
#         # Create mock error response
#         mock_response = AsyncMock(spec=httpx.Response)
#         mock_response.status_code = 429  # Too Many Requests
#         mock_response.headers = {"Content-Type": "application/json"}
#         mock_response.content = json.dumps(
#             {
#                 "error": {
#                     "message": "Rate limit exceeded",
#                     "type": "rate_limit_error",
#                 }
#             }
#         ).encode()
#
#         # Setup mock service
#         mock_proxy_service.handle_request.return_value = Response(
#             content=mock_response.content,
#             status_code=mock_response.status_code,
#             headers=mock_response.headers,
#         )
#
#         # Make request
#         chat_request = ChatRequest(
#             messages=[Message(role="user", content="Ping")],
#             model="openai__gpt-4",
#         )
#
#         response = client.post(
#             "/api/ai-proxy/chat/completions",
#             json=chat_request.model_dump(),
#         )
#
#         # Verify error response
#         assert response.status_code == 429
#         assert response.json()["error"]["type"] == "rate_limit_error"
#
#         # Verify service cleanup
#         mock_proxy_service.close.assert_awaited_once()
#
#     def test_create_chat_completion__streaming_timeout(
#         self,
#         client: TestClient,
#         mock_proxy_service: AsyncMock,
#     ) -> None:
#         """Test streaming response with timeout."""
#         # Create mock streaming response that takes too long
#         mock_response = AsyncMock(spec=httpx.Response)
#         mock_response.status_code = 200
#         mock_response.headers = {"Content-Type": "text/event-stream"}
#
#         async def mock_aiter_bytes():
#             yield b'data: {"id": "test-1", "choices": [{"delta": {"content": "Hello"}}]}\n\n'
#             await asyncio.sleep(0.3)  # Simulate long processing > client timeout
#             yield b'data: {"id": "test-2", "choices": [{"delta": {"content": " World"}}]}\n\n'
#
#         mock_response.aiter_bytes = mock_aiter_bytes
#
#         # Setup mock service
#         mock_proxy_service.handle_request.return_value = StreamingResponse(
#             content=mock_response.aiter_bytes(),
#             status_code=200,
#             headers={"Content-Type": "text/event-stream"},
#         )
#
#         # Make request with short timeout
#         chat_request = ChatRequest(
#             messages=[Message(role="user", content="Ping")],
#             model="openai__gpt-4",
#             stream=True,
#         )
#
#         with pytest.raises(httpx.ReadTimeout):
#             client.post(
#                 "/api/ai-proxy/chat/completions",
#                 json=chat_request.model_dump(),
#                 headers={"accept": "text/event-stream"},
#                 timeout=0.1,  # Very short timeout < sleep time
#             )
#
#         # Verify service cleanup
#         mock_proxy_service.close.assert_awaited_once()
#
#     def test_create_chat_completion__streaming_error_status(
#         self,
#         client: TestClient,
#         mock_proxy_service: AsyncMock,
#     ) -> None:
#         """Test streaming response with error status code."""
#         # Create mock streaming error response
#         mock_response = AsyncMock(spec=httpx.Response)
#         mock_response.status_code = 503  # Service Unavailable
#         mock_response.headers = {"Content-Type": "text/event-stream"}
#
#         async def mock_aiter_bytes():
#             yield b'data: {"error": {"message": "Service unavailable", "type": "service_error"}}\n\n'
#
#         mock_response.aiter_bytes = mock_aiter_bytes
#
#         # Setup mock service
#         mock_proxy_service.handle_request.return_value = StreamingResponse(
#             content=mock_response.aiter_bytes(),
#             status_code=503,
#             headers={"Content-Type": "text/event-stream"},
#         )
#
#         # Make request
#         chat_request = ChatRequest(
#             messages=[Message(role="user", content="Ping")],
#             model="openai__gpt-4",
#             stream=True,
#         )
#
#         response = client.post(
#             "/api/ai-proxy/chat/completions",
#             json=chat_request.model_dump(),
#             headers={"accept": "text/event-stream"},
#         )
#
#         # Verify error response
#         assert response.status_code == 503
#         content = response.text
#         assert "service_error" in content
#         assert "Service unavailable" in content
#
#         # Verify service cleanup
#         mock_proxy_service.close.assert_awaited_once()
