"""Tests for proxy service."""

from typing import Any, AsyncGenerator, AsyncIterator
from unittest.mock import Mock, AsyncMock

import json
import httpx
import pytest
from fastapi import Response
from fastapi.responses import StreamingResponse

from src.constants import Vendor
from src.settings import AppSettings
from src.models import ChatRequest, Message
from src.exceptions import ProviderProxyError
from src.services.proxy import ProxyService, ProxyRequestData, ProxyEndpoint

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
def mock_stream_request_data() -> ProxyRequestData:
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
def mock_stream_response() -> AsyncMock:
    """Return mock response."""
    default_content = (
        b'data: {"id": "test-1", "choices": [{"delta": {"content": "Hello"}}]}\n\ndata: [DONE]\n\n'
    )

    async def mock_aiter_bytes() -> AsyncIterator[bytes]:
        content = resp.content or default_content
        for chunk in content.split(b"\n\n"):
            if chunk.startswith(b"ERROR: "):
                raise RuntimeError(chunk.lstrip(b"ERROR: "))
            if chunk:
                yield chunk + b"\n\n"

    resp = AsyncMock(spec=httpx.Response)
    resp.status_code = 201
    resp.aiter_bytes = mock_aiter_bytes
    resp.content = default_content
    resp.headers = {"Content-Type": "text/event-stream"}
    return resp


@pytest.fixture
def mock_http_client(mock_response: AsyncMock) -> AsyncMock:
    """Return mock HTTP client."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.build_request = Mock(return_value=Mock(spec=httpx.Request))
    mock_client.send = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.fixture
async def mock_proxy_service(
    mock_settings: AppSettings, mock_http_client: AsyncMock
) -> AsyncGenerator[ProxyService, Any]:
    """Return proxy service instance."""
    async with ProxyService(mock_settings, mock_http_client) as service:
        yield service


@pytest.fixture
def mock_stream_http_client(mock_stream_response: AsyncMock) -> AsyncMock:
    """Return mock HTTP client."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.build_request = Mock(return_value=Mock(spec=httpx.Request))
    mock_client.send = AsyncMock(return_value=mock_stream_response)
    return mock_client


@pytest.fixture
async def mock_stream_proxy_service(
    mock_settings: AppSettings, mock_stream_http_client: AsyncMock
) -> AsyncGenerator[ProxyService, Any]:
    """Return proxy service instance."""
    async with ProxyService(mock_settings, mock_stream_http_client) as service:
        yield service


class TestProxyService:
    """Tests for ProxyService."""

    async def test_handle_request_regular(
        self,
        mock_request_data: ProxyRequestData,
        mock_proxy_service: ProxyService,
        mock_response: AsyncMock,
    ) -> None:
        """Test handling regular (non-streaming) request."""
        mock_response.content = b'{"response": "Hello!"}'

        response = await mock_proxy_service.handle_request(
            mock_request_data, ProxyEndpoint.CHAT_COMPLETION
        )

        assert isinstance(response, Response)
        assert response.status_code == 200
        assert response.body == b'{"response": "Hello!"}'
        assert response.headers["Content-Type"] == "application/json"

    async def test_handle_request_streaming(
        self,
        mock_stream_request_data: ProxyRequestData,
        mock_stream_proxy_service: ProxyService,
        mock_stream_response: AsyncMock,
    ) -> None:
        """Test handling streaming request."""

        mock_stream_request_data.body = ChatRequest(
            messages=[Message(role="user", content="Hello")],
            model="deepseek__deepseek-chat",
            stream=True,
        )
        completion_id = "fdc42f0f-b8ac-434d-b921-018701b8c2ba"
        content = (
            "data: {"
            '"id":"$completion_id","object":"chat.completion.chunk","created":1748172086,'
            '"model":"deepseek-chat","system_fingerprint":"fp_8802369eaa_prod0425fp8",'
            '"choices":[{"index":0,"delta":{"content":"Deep: \xd0\xb2\xd0\xb5\xd1\x82"},'
            '"logprobs":null,"finish_reason":null}]'
            "}\n\n"
        )
        content = content.replace("$completion_id", completion_id)  # TODO: use Template instead
        mock_stream_response.content = content.encode()

        response = await mock_stream_proxy_service.handle_request(
            mock_stream_request_data,
            endpoint=ProxyEndpoint.CHAT_COMPLETION,
        )
        assert isinstance(response, StreamingResponse)
        assert response.status_code == 201
        assert response.headers["Content-Type"] == "text/event-stream"
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["Connection"] == "keep-alive"

        vendor = mock_stream_proxy_service._cache_get_vendor(completion_id)
        assert vendor == Vendor.DEEPSEEK

    async def test_handle_request_no_body(
        self,
        mock_proxy_service: ProxyService,
    ) -> None:
        """Test handling request without body."""
        request_data = ProxyRequestData(
            method="POST",
            headers={},
            query_params={},
            body=None,
        )

        with pytest.raises(ProviderProxyError, match="Request body is required"):
            await mock_proxy_service.handle_request(request_data, ProxyEndpoint.CHAT_COMPLETION)

    async def test_handle_request_invalid_model(
        self,
        mock_request_data: ProxyRequestData,
        mock_proxy_service: ProxyService,
    ) -> None:
        """Test handling request with an invalid model format."""
        mock_request_data.body.model = "invalid-model"  # type: ignore

        with pytest.raises(ProviderProxyError, match="Invalid model format"):
            await mock_proxy_service.handle_request(
                mock_request_data, ProxyEndpoint.CHAT_COMPLETION
            )

    async def test_handle_request_unknown_provider(
        self,
        mock_request_data: ProxyRequestData,
        mock_proxy_service: ProxyService,
    ) -> None:
        """Test handling request with an unknown provider."""
        mock_request_data.body.model = "unknown__gpt-4"  # type: ignore

        with pytest.raises(ProviderProxyError, match="Unable to extract provider"):
            await mock_proxy_service.handle_request(
                mock_request_data, ProxyEndpoint.CHAT_COMPLETION
            )

    async def test_handle_request_cancellation(
        self,
        mock_request_data: ProxyRequestData,
        mock_proxy_service: ProxyService,
        mock_http_client: AsyncMock,
        mock_response: AsyncMock,
    ) -> None:
        """Test handling cancellation request."""
        completion_id = "test-completion"
        mock_proxy_service._cache_set_vendor(completion_id, Vendor.OPENAI)

        mock_response.content = b'{"status": "cancelled"}'
        mock_http_client.send.return_value = mock_response

        mock_request_data.completion_id = completion_id
        response = await mock_proxy_service.handle_request(
            mock_request_data, ProxyEndpoint.CANCEL_CHAT_COMPLETION
        )

        assert isinstance(response, Response)
        assert response.status_code == 200
        assert response.body == b'{"status": "cancelled"}'

    async def test_handle_request_cancellation_no_id(
        self,
        mock_request_data: ProxyRequestData,
        mock_proxy_service: ProxyService,
    ) -> None:
        """Test handling cancellation request without completion ID."""
        with pytest.raises(ProviderProxyError, match="completion_id is required"):
            await mock_proxy_service.handle_request(
                mock_request_data, ProxyEndpoint.CANCEL_CHAT_COMPLETION
            )

    async def test_handle_request_streaming_error(
        self,
        mock_stream_request_data: ProxyRequestData,
        mock_stream_proxy_service: ProxyService,
        mock_stream_response: AsyncMock,
    ) -> None:
        """Test handling streaming request with error in stream."""
        content = [
            'data: {"id": "test-1", "choices": [{"delta": {"content": "Hello"}}]}\n\n',
            "ERROR: Stream error\n\n",
        ]
        mock_stream_response.content = "".join(content).encode()

        response = await mock_stream_proxy_service.handle_request(
            mock_stream_request_data, ProxyEndpoint.CHAT_COMPLETION
        )

        assert isinstance(response, StreamingResponse)
        assert response.status_code == 201
        assert response.headers["Content-Type"] == "text/event-stream"

    async def test_handle_request_streaming_empty(
        self,
        mock_stream_request_data: ProxyRequestData,
        mock_stream_proxy_service: ProxyService,
        mock_stream_response: AsyncMock,
    ) -> None:
        """Test handling streaming request with empty stream."""

        async def mock_aiter_bytes() -> AsyncGenerator[bytes]:
            # noinspection PyUnreachableCode
            if False:  # This ensures the generator is async
                yield b""

        mock_stream_response.aiter_bytes = mock_aiter_bytes

        with pytest.raises(ProviderProxyError, match="Stream ended before chunk received"):
            await mock_stream_proxy_service.handle_request(
                mock_stream_request_data,
                endpoint=ProxyEndpoint.CHAT_COMPLETION,
            )

    async def test_handle_request_streaming_headers(
        self,
        mock_stream_request_data: ProxyRequestData,
        mock_stream_proxy_service: ProxyService,
        mock_stream_response: AsyncMock,
    ) -> None:
        """Test handling streaming request with custom headers."""
        mock_stream_response.headers = {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Custom-Header": "test",
        }

        response = await mock_stream_proxy_service.handle_request(
            mock_stream_request_data, ProxyEndpoint.CHAT_COMPLETION
        )

        assert isinstance(response, StreamingResponse)
        assert response.status_code == 201
        assert response.headers["Content-Type"] == "text/event-stream"
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["Connection"] == "keep-alive"
        assert response.headers["X-Custom-Header"] == "test"

    async def test_handle_request_timeout(
        self,
        mock_request_data: ProxyRequestData,
        mock_proxy_service: ProxyService,
        mock_http_client: AsyncMock,
    ) -> None:
        """Test handling request with timeout."""
        mock_request_data.timeout = 0.1
        mock_http_client.send.side_effect = httpx.TimeoutException("Request timed out")

        with pytest.raises(ProviderProxyError, match="Request timeout"):
            await mock_proxy_service.handle_request(
                mock_request_data,
                endpoint=ProxyEndpoint.CHAT_COMPLETION,
            )

    async def test_handle_request_streaming_timeout(
        self,
        mock_stream_request_data: ProxyRequestData,
        mock_stream_proxy_service: ProxyService,
        mock_stream_http_client: AsyncMock,
        mock_stream_response: AsyncMock,
    ) -> None:
        """Test handling streaming request with timeout."""
        mock_stream_request_data.timeout = 0.1
        mock_stream_http_client.send.side_effect = httpx.TimeoutException("Stream timed out")

        with pytest.raises(ProviderProxyError, match="Stream timeout"):
            await mock_stream_proxy_service.handle_request(
                mock_stream_request_data,
                endpoint=ProxyEndpoint.CHAT_COMPLETION,
            )

    async def test_handle_request_error_status(
        self,
        mock_request_data: ProxyRequestData,
        mock_proxy_service: ProxyService,
        mock_response: AsyncMock,
    ) -> None:
        """Test handling request with error status code."""
        mock_response.status_code = 429
        mock_response.content = json.dumps(
            {
                "error": {
                    "message": "Rate limit exceeded",
                    "type": "rate_limit_error",
                }
            }
        ).encode()

        response = await mock_proxy_service.handle_request(
            mock_request_data,
            endpoint=ProxyEndpoint.CHAT_COMPLETION,
        )

        assert isinstance(response, Response)
        assert response.status_code == 429
        assert response.headers["Content-Type"] == "application/json"
        assert json.loads(response.body)["error"]["type"] == "rate_limit_error"

    async def test_handle_request_streaming_error_status(
        self,
        mock_stream_request_data: ProxyRequestData,
        mock_stream_proxy_service: ProxyService,
        mock_stream_http_client: AsyncMock,
        mock_stream_response: AsyncMock,
    ) -> None:
        """Test handling streaming request with error status code."""
        content = [
            'data: {"error": {"message": "Service unavailable", "type": "service_error"}}\n\n'
        ]
        mock_stream_response.content = "".join(content).encode()
        mock_stream_response.status_code = 503

        with pytest.raises(ProviderProxyError, match="Missed completion_id in response"):
            await mock_stream_proxy_service.handle_request(
                mock_stream_request_data,
                endpoint=ProxyEndpoint.CHAT_COMPLETION,
            )
