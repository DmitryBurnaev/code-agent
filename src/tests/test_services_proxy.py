"""Tests for proxy service."""
import json
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
        self, mock_settings: AppSettings, mock_request_data: ProxyRequestData, mock_http_client: AsyncMock
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
            response = await service.handle_request(mock_request_data, ProxyEndpoint.CHAT_COMPLETION)

            # Verify response
            assert isinstance(response, Response)
            assert response.status_code == 200
            assert response.body == b'{"response": "Hello!"}'
            assert response.headers["Content-Type"] == "application/json"

    @pytest.mark.anyio
    async def test_handle_request_streaming(
        self, mock_settings: AppSettings, mock_streaming_request_data: ProxyRequestData, mock_http_client: AsyncMock
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
        self, mock_settings: AppSettings, mock_request_data: ProxyRequestData, mock_http_client: AsyncMock
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