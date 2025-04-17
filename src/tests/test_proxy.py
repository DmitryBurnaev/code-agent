from typing import Any, AsyncGenerator
import json
import pytest
from fastapi.testclient import TestClient
from httpx import Request, Response
from pydantic import SecretStr

from src.settings import AppSettings, ProxyRoute


@pytest.fixture
def proxy_settings() -> AppSettings:
    """Create test settings with proxy routes."""
    return AppSettings(
        proxy_routes=[
            ProxyRoute(
                source_path="/proxy/test",
                target_url="http://test-api.com",
                strip_path=True,
                timeout=5.0,
            ),
            ProxyRoute(
                source_path="/proxy/chat",
                target_url="http://chat-api.com",
                strip_path=False,
                timeout=60.0,
                auth_token=SecretStr("test-token"),
                auth_type="Bearer",
            ),
            ProxyRoute(
                source_path="/proxy/custom",
                target_url="http://custom-api.com",
                strip_path=True,
                timeout=10.0,
                auth_token=SecretStr("api-key"),
                auth_type="ApiKey",
            ),
        ]
    )


@pytest.fixture
def client(proxy_settings) -> TestClient:
    """Create a test client with proxy settings."""
    from src.main import make_app
    from src.dependencies import get_app_settings

    app = make_app(settings=proxy_settings)
    app.dependency_overrides = {
        get_app_settings: lambda: proxy_settings,
    }
    return TestClient(app)


def test_proxy_route_not_found(client: TestClient) -> None:
    """Test proxy route with non-existent path."""
    response = client.get("/proxy/nonexistent/path")
    assert response.status_code == 404
    assert response.json()["detail"] == "No matching proxy route found"


def test_proxy_regular_post_request(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test regular POST request with JSON body."""
    test_request = {
        "model": "test-model",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": False,
    }
    expected_response = {"response": "Hello, world!"}

    def mock_request(self: Request, **kwargs: Any) -> Response:
        """Mock regular response from API."""
        assert kwargs["method"] == "POST"
        assert kwargs["url"] == "http://chat-api.com/completions"
        assert kwargs["json"] == test_request
        assert not kwargs["stream"]
        return Response(200, json=expected_response)

    monkeypatch.setattr("httpx.AsyncClient.request", mock_request)

    response = client.post(
        "/proxy/chat/completions",
        json=test_request,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json() == expected_response


def test_proxy_streaming_post_request(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test streaming POST request."""
    test_request = {
        "model": "test-model",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": True,
    }

    async def mock_stream() -> AsyncGenerator[bytes, None]:
        """Mock streaming response."""
        chunks = [
            b'data: {"chunk": 1}\n\n',
            b'data: {"chunk": 2}\n\n',
            b"data: [DONE]\n\n",
        ]
        for chunk in chunks:
            yield chunk

    def mock_request(self: Request, **kwargs: Any) -> Response:
        """Mock streaming response from API."""
        assert kwargs["method"] == "POST"
        assert kwargs["url"] == "http://chat-api.com/completions"
        assert kwargs["json"] == test_request
        assert kwargs["stream"]

        response = Response(200, stream=mock_stream)
        response.headers["Content-Type"] = "text/event-stream"
        return response

    monkeypatch.setattr("httpx.AsyncClient.request", mock_request)

    with client.stream(
        "POST",
        "/proxy/chat/completions",
        json=test_request,
        headers={"Content-Type": "application/json"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream"

        chunks = list(response.iter_lines())
        assert len(chunks) == 3
        assert json.loads(chunks[0].decode().replace("data: ", "")) == {"chunk": 1}
        assert json.loads(chunks[1].decode().replace("data: ", "")) == {"chunk": 2}
        assert chunks[2].decode() == "data: [DONE]"


def test_proxy_invalid_json(client: TestClient) -> None:
    """Test request with invalid JSON body."""
    response = client.post(
        "/proxy/chat/completions",
        data="invalid json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid JSON body"


def test_proxy_strip_path(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test proxy with path stripping."""

    def mock_request(self: Request, **kwargs: Any) -> Response:
        """Mock response to verify path stripping."""
        assert kwargs["url"] == "http://test-api.com/path"
        return Response(200, json={"status": "ok"})

    monkeypatch.setattr("httpx.AsyncClient.request", mock_request)

    response = client.get("/proxy/test/path")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_proxy_custom_timeout(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test proxy request with custom timeout."""

    def mock_request(self: Request, **kwargs: Any) -> Response:
        """Mock response and verify timeout."""
        assert kwargs["timeout"].read_timeout == 5.0  # From test route config
        return Response(200, json={"status": "ok"})

    monkeypatch.setattr("httpx.AsyncClient.request", mock_request)

    response = client.get("/proxy/test/endpoint")
    assert response.status_code == 200


def test_proxy_auth_token_bearer(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test proxy request with Bearer auth token."""

    def mock_request(self: Request, **kwargs: Any) -> Response:
        """Mock response and verify auth header."""
        assert kwargs["headers"]["Authorization"] == "Bearer test-token"
        return Response(200, json={"status": "authorized"})

    monkeypatch.setattr("httpx.AsyncClient.request", mock_request)

    response = client.get("/proxy/chat/endpoint")
    assert response.status_code == 200
    assert response.json() == {"status": "authorized"}


def test_proxy_auth_token_custom(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test proxy request with custom auth type."""

    def mock_request(self: Request, **kwargs: Any) -> Response:
        """Mock response and verify custom auth header."""
        assert kwargs["headers"]["Authorization"] == "ApiKey api-key"
        return Response(200, json={"status": "authorized"})

    monkeypatch.setattr("httpx.AsyncClient.request", mock_request)

    response = client.get("/proxy/custom/endpoint")
    assert response.status_code == 200
    assert response.json() == {"status": "authorized"}


def test_proxy_auth_token_override(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that route auth token overrides request auth header."""

    def mock_request(self: Request, **kwargs: Any) -> Response:
        """Mock response and verify auth header precedence."""
        assert kwargs["headers"]["Authorization"] == "Bearer test-token"  # From route config
        return Response(200, json={"status": "authorized"})

    monkeypatch.setattr("httpx.AsyncClient.request", mock_request)

    response = client.get(
        "/proxy/chat/endpoint",
        headers={"Authorization": "Bearer user-token"},  # Should be ignored
    )
    assert response.status_code == 200


def test_proxy_streaming_timeout(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that streaming requests use infinite timeout."""
    test_request = {
        "model": "test-model",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": True,
    }

    def mock_request(self: Request, **kwargs: Any) -> Response:
        """Mock response and verify timeout for streaming."""
        assert kwargs["timeout"] is None  # Should be None for streaming
        assert kwargs["stream"] is True

        async def mock_stream() -> AsyncGenerator[bytes, None]:
            yield b"data: test\n\n"

        response = Response(200, stream=mock_stream)
        response.headers["Content-Type"] = "text/event-stream"
        return response

    monkeypatch.setattr("httpx.AsyncClient.request", mock_request)

    with client.stream(
        "POST",
        "/proxy/chat/completions",
        json=test_request,
        headers={"Content-Type": "application/json"},
    ) as response:
        assert response.status_code == 200
