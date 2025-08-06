import json
from typing import Any, Generator, AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import Headers
from fastapi.testclient import TestClient
from starlette.responses import Response, StreamingResponse

from src.services.vendors import VendorService
from src.models import ChatRequest, Message, AIModel
from src.services.proxy import ProxyService, ProxyRequestData, ProxyEndpoint


@pytest.fixture
def mock_vendor_service() -> Generator[AsyncMock, Any, None]:
    mock_service = AsyncMock(spec=VendorService)
    mock_service.get_list_models.return_value = [
        AIModel(id="openai__gpt-4", vendor="openai", vendor_id="gpt-4"),
        AIModel(id="deepseek__deepseek-1", vendor="deepseek", vendor_id="deepseek-1"),
    ]
    with patch("src.api.proxy.VendorService", return_value=mock_service):
        yield mock_service


@pytest.fixture
def mock_proxy_service() -> Generator[AsyncMock, Any, None]:
    service = AsyncMock(spec=ProxyService)
    service.handle_request.return_value = AsyncMock()
    with patch("src.api.proxy.ProxyService", return_value=service):
        yield service


class TestProxyAPI:

    def test_list_models(self, client: TestClient, mock_vendor_service: AsyncMock) -> None:
        response = client.get("/api/ai-proxy/models")
        assert response.status_code == 200
        data = response.json()
        assert data == {
            "data": [
                {"id": "openai__gpt-4", "vendor": "openai", "vendor_id": "gpt-4"},
                {"id": "deepseek__deepseek-1", "vendor": "deepseek", "vendor_id": "deepseek-1"},
            ]
        }
        mock_vendor_service.get_list_models.assert_awaited_once()

    def test_create_chat_completion(
        self,
        client: TestClient,
        auth_test_token: str,
        mock_proxy_service: AsyncMock,
    ) -> None:
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
                    "authorization": f"Bearer {auth_test_token}",
                    "user-agent": "testclient",
                    "content-length": "197",
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
        self,
        client: TestClient,
        auth_test_token: str,
        mock_proxy_service: AsyncMock,
        stream_words: list[str],
    ) -> None:
        chat_request = ChatRequest(
            messages=[Message(role="user", content="Ping")],
            model="openai__gpt-4",
            stream=True,
        )
        response_headers = Headers(
            {
                "content-type": "text/event-stream",
                "cache-control": "no-cache",
                "connection": "keep-alive",
                "access-control-allow-origin": "*",
                "access-control-allow-methods": "POST, OPTIONS",
                "access-control-allow-headers": "Content-Type, Authorization",
                "access-control-max-age": "86400",
            }
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
            headers=response_headers,
            status_code=200,
        )

        response = client.post(
            "/api/ai-proxy/chat/completions",
            json=chat_request.model_dump(),
            headers={"accept": "text/event-stream"},
        )

        # Verify response
        assert response.status_code == 200
        assert response.headers == response_headers

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
                    "authorization": f"Bearer {auth_test_token}",
                    "user-agent": "testclient",
                    "accept": "text/event-stream",
                    "content-length": "196",
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
        auth_test_token: str,
        mock_proxy_service: AsyncMock,
    ) -> None:
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
                    "authorization": f"Bearer {auth_test_token}",
                    "user-agent": "testclient",
                },
                query_params={},
                body=None,
                completion_id=completion_id,
            ),
            ProxyEndpoint.CANCEL_CHAT_COMPLETION,
        )
        mock_proxy_service.__aexit__.assert_awaited_once_with(None, None, None)

    def test_options_chat_completion(self, client: TestClient) -> None:
        response = client.options("/api/ai-proxy/chat/completions")

        assert response.status_code == 204
        assert response.headers["Access-Control-Allow-Origin"] == "*"
        assert response.headers["Access-Control-Allow-Methods"] == "POST, OPTIONS"
        assert response.headers["Access-Control-Allow-Headers"] == "Content-Type, Authorization"
        assert response.headers["Access-Control-Max-Age"] == "86400"
