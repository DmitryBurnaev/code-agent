import json
import time
import logging
from enum import Enum, auto
from dataclasses import dataclass
from typing import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse

from src.exceptions import ProviderProxyError, ProviderError
from src.models import ChatRequest
from src.settings import ProxyRoute, AppSettings
from src.services.providers import ProviderService

logger = logging.getLogger(__name__)


class ProxyEndpoint(Enum):
    """Available proxy endpoints."""

    CHAT_COMPLETION = "CHAT_COMPLETION"
    LIST_MODELS = "LIST_MODELS"
    CANCEL_CHAT_COMPLETION = "CANCEL_CHAT_COMPLETION"


@dataclass
class ProxyRequestData:
    """Data required for proxy request."""

    method: str
    headers: dict[str, str]
    query_params: dict[str, str]
    body: ChatRequest | None = None
    completion_id: str | None = None


class ProxyService:
    """
    Service for proxying requests to AI providers.

    Handles routing, request transformation and response streaming
    for different AI providers like OpenAI, Anthropic, etc.

    Capabilities:
    - Route requests to appropriate provider endpoints
    - Transform request/response data between providers
    - Handle streaming responses
    - Manage connection lifecycle and logging

    Args:
        settings: Application settings containing provider configurations

    Attributes:
        _settings: Stored settings instance
        _client: Lazy-loaded httpx client for making requests
    """

    # Mapping of endpoints to their paths
    _ENDPOINT_PATHS = {
        ProxyEndpoint.LIST_MODELS: "models",
        ProxyEndpoint.CHAT_COMPLETION: "chat/completions",
        ProxyEndpoint.CANCEL_CHAT_COMPLETION: "chat/completions/{completion_id}",
    }
    _DEFAULT_RETRY_DELAY: float = 1.0  # seconds
    _DEFAULT_MAX_RETRIES: int = 2

    def __init__(self, settings: AppSettings):
        self._settings = settings
        self._http_client = httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(retries=self._DEFAULT_MAX_RETRIES),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                # TODO: provide correct auth headers for each provider inside!
                # "Authorization": f"{self._provider.auth_type} {self._provider.api_key}",
            },
        )
        self._provider_service = ProviderService(settings, self._http_client)
        self._route: ProxyRoute | None = None

    async def handle_request(
        self,
        request_data: ProxyRequestData,
        endpoint: ProxyEndpoint,
    ) -> Response | StreamingResponse:
        """
        Handle an incoming proxy request by forwarding it to the appropriate provider.

        Args:
            request_data: Encapsulated request data including method, headers, params and body
            endpoint: Which endpoint to proxy to (chat, models, etc.)

        Returns:
            Response from the provider, may be streaming or regular response

        Raises:
            HTTPException: If provider is not found or the request fails
        """

        try:
            response = await self._do_handle(request_data, endpoint)
        except ProviderError as exc:
            logger.error("Provider proxy: unable to handle request: %r", exc)
            raise HTTPException(
                status_code=400,
                detail="Unable to handle request",
            )

        return response

    async def _do_handle(
        self,
        request_data: ProxyRequestData,
        endpoint: ProxyEndpoint,
    ) -> Response | StreamingResponse:
        match endpoint:
            case ProxyEndpoint.CHAT_COMPLETION:
                if not request_data.body:
                    raise ProviderProxyError("Request body is required for chat completion")

                provider, actual_model = self._extract_provider_from_model(request_data.body.model)
                request_data.body.model = actual_model

            case ProxyEndpoint.LIST_MODELS:
                provider, actual_model = self._extract_provider_from_model(request_data.body.model)

        # For chat requests, we need to extract provider and update model name
        if endpoint == ProxyEndpoint.CHAT_COMPLETION:
            if not request_data.body:
                raise HTTPException(
                    status_code=400,
                    detail="Request body is required for chat completion",
                )

            provider, actual_model = self._extract_provider_from_model(request_data.body.model)
            request_data.body.model = actual_model

        elif endpoint == ProxyEndpoint.CANCEL_CHAT_COMPLETION:
            if not request_data.body:
                raise HTTPException(
                    status_code=400,
                    detail="Request body is required for cancellation",
                )
            provider, _ = self._extract_provider_from_model(request_data.body.model)

        elif endpoint == ProxyEndpoint.LIST_MODELS:
            # Return aggregated list of models from all providers
            models = await self._provider_service.get_list_models()
            return Response(
                content=json.dumps(
                    {
                        "data": [
                            {
                                "id": model.full_name,
                                "name": model.name,
                                "provider": model.provider,
                            }
                            for model in models
                        ]
                    }
                ),
                media_type="application/json",
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="Unknown endpoint",
            )

        path = self._build_provider_path(provider, endpoint, request_data)
        self._find_matching_route(path)
        url = self._build_target_url(path)
        headers = self._prepare_headers(request_data.headers)

        # Prepare request body
        is_streaming = False
        body = None

        if request_data.body:
            is_streaming = request_data.body.stream
            body = {
                **request_data.body.model_dump(),
                **request_data.body.get_provider_params(),
            }

        logger.info(f"Proxying {request_data.method} request to {url}")

        async with self._get_client(is_streaming) as client:
            try:
                response = await client.request(
                    method=request_data.method,
                    url=url,
                    headers=headers,
                    json=body,
                    params=request_data.query_params,
                    stream=is_streaming,
                )

                if is_streaming:
                    response_headers = dict(response.headers)
                    response_headers.update(
                        {
                            "Content-Type": "text/event-stream",
                            "Cache-Control": "no-cache",
                            "Connection": "keep-alive",
                        }
                    )

                    return StreamingResponse(
                        self._stream_response(response),
                        status_code=response.status_code,
                        headers=response_headers,
                    )

                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                )

            except Exception as e:
                logger.error(f"Error during proxy request: {e}")
                raise HTTPException(status_code=500, detail="Internal Server Error")

    def _build_provider_path(
        self, provider: str, endpoint: ProxyEndpoint, request_data: ProxyRequestData
    ) -> str:
        """Build provider-specific path for the endpoint."""
        path = self._ENDPOINT_PATHS[endpoint]

        # Replace path parameters if needed
        if endpoint == ProxyEndpoint.CANCEL_CHAT_COMPLETION:
            if not request_data.completion_id:
                raise HTTPException(
                    status_code=400,
                    detail="completion_id is required for cancellation",
                )
            path = path.format(completion_id=request_data.completion_id)

        return f"/proxy/{provider}/{path}"

    def _extract_provider_from_model(self, model: str) -> tuple[str, str]:
        """Extract provider and actual model name from the composite model identifier."""
        try:
            provider, model_name = model.split("__", 1)
            provider = provider.lower()

            # Check if the provider is supported
            self._provider_service.get_client(provider)

            return provider, model_name

        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid model format. Expected 'provider__model_name', "
                    "e.g. 'openai__gpt-4' or 'anthropic__claude-3'"
                ),
            )

    def _find_matching_route(self, path: str) -> None:
        """Find matching proxy route for given path."""
        for route in self._settings.proxy_routes:
            if path.startswith(route.source_path):
                self._route = route
                return

        raise HTTPException(status_code=404, detail="No matching proxy route found")

    def _build_target_url(self, path: str) -> str:
        """Build target URL for proxy request."""
        return f"{self._route.target_url.rstrip('/')}/{path.lstrip('/')}"

    def _prepare_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """Prepare headers for proxy request with auth if configured."""
        clean_headers = {
            k: v for k, v in headers.items() if k.lower() not in ("host", "connection")
        }

        if self._route.auth_token:
            clean_headers["Authorization"] = (
                f"{self._route.auth_type} {self._route.auth_token.get_secret_value()}"
            )

        return clean_headers

    async def _stream_response(self, response: httpx.Response) -> AsyncGenerator[bytes, None]:
        """Stream response chunks with proper error handling."""
        try:
            async for chunk in response.aiter_bytes():
                if chunk.strip():
                    yield chunk
        except httpx.HTTPError as e:
            logger.error(f"Streaming error during proxy request: {e}")
            yield b"data: [DONE]\n\n"
        finally:
            await response.aclose()

    @asynccontextmanager
    async def _get_client(self, is_streaming: bool):
        """Context manager for httpx client with proper timeout configuration."""
        timeout = httpx.Timeout(None) if is_streaming else httpx.Timeout(self._route.timeout)
        start_time = time.monotonic()

        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            self._client = client
            logger.info(
                "Created httpx client [streaming=%s, timeout=%s]",
                is_streaming,
                "infinite" if is_streaming else self._route.timeout,
            )

            try:
                yield client
            finally:
                duration = time.monotonic() - start_time
                logger.debug(
                    "Closing httpx client connection [duration=%.2fs]",
                    duration,
                )
                self._client = None
