import time
import logging
import urllib.parse
from enum import Enum
from dataclasses import dataclass
from typing import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse

from src.exceptions import ProviderProxyError, ProviderError
from src.models import ChatRequest
from src.services.http import AIProviderHTTPClient
from src.settings import AppSettings, LLMProvider
from src.services.providers import ProviderService, AIModel

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

    def __init__(self, settings: AppSettings):
        self._settings = settings
        self._http_client = AIProviderHTTPClient(settings)
        self._provider_service = ProviderService(settings, self._http_client)

    async def handle_request(
        self,
        request_data: ProxyRequestData,
        endpoint: ProxyEndpoint,
    ) -> Response | StreamingResponse | list[AIModel]:
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
    ) -> Response | StreamingResponse | list[AIModel]:
        if not request_data.body:
            raise ProviderProxyError(f"Request body is required for {endpoint}")

        match endpoint:
            case ProxyEndpoint.CHAT_COMPLETION:
                logger.info("ProxyService: Chat completion requested | %s", request_data.body.model)
                provider, actual_model = self._extract_provider_requested(request_data.body.model)
                request_data.body.model = actual_model

            case ProxyEndpoint.CANCEL_CHAT_COMPLETION:
                logger.info("ProxyService: Chat canceling requested | %s", request_data.body.model)
                provider, _ = self._extract_provider_requested(request_data.body.model)

            case ProxyEndpoint.LIST_MODELS:
                logger.info("ProxyService: List models requested | %s", request_data.body.model)
                provider, _ = self._extract_provider_requested(request_data.body.model)
                return await self._provider_service.get_list_models()

            case _:
                raise ProviderProxyError(f"Unknown endpoint {endpoint}")

        # Prepare request data
        url = self._build_target_url(provider, endpoint, request_data)
        headers = self._prepare_headers(provider, request_data.headers)
        is_streaming = False
        body = None

        if request_data.body:
            is_streaming = request_data.body.stream
            body = {
                **request_data.body.model_dump(),
                **request_data.body.get_provider_params(),
            }

        logger.info("ProxyService: Sending proxy %s request to %s", request_data.method, url)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("ProxyService: Requested body: '%s'", request_data.body)

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

    def _build_target_url(
        self,
        provider: LLMProvider,
        endpoint: ProxyEndpoint,
        request_data: ProxyRequestData,
    ) -> str:
        """Build a provider-specific path for the endpoint."""
        path = self._ENDPOINT_PATHS[endpoint]

        # Replace path parameters if needed
        if endpoint == ProxyEndpoint.CANCEL_CHAT_COMPLETION:
            if not request_data.completion_id:
                raise ProviderProxyError("completion_id is required for cancellation")

            path = path.format(completion_id=request_data.completion_id)

        return urllib.parse.urljoin(provider.base_url, path)

    def _extract_provider_requested(self, model: str) -> tuple[LLMProvider, str]:
        """Extract provider and actual model name from the composite model identifier."""
        try:
            provider, model_name = model.split("__", 1)
            llm_provider = self._settings.provider_by_vendor[provider.lower()]
        except ValueError as exc:
            raise ProviderProxyError(
                "Invalid model format. Expected 'provider__model_name', " "e.g. 'openai__gpt-4'"
            ) from exc

        except KeyError as exc:
            raise ProviderProxyError("Unable to extract provider from model name") from exc

        else:
            logger.debug(
                "ProxyService: detected provider %s | source model: %s", llm_provider, model
            )

        return llm_provider, model_name

    @staticmethod
    def _prepare_headers(provider: LLMProvider, headers: dict[str, str]) -> dict[str, str]:
        """Prepare headers for proxy request with auth if configured."""
        clean_headers = {
            k: v for k, v in headers.items() if k.lower() not in ("host", "connection")
        }
        return clean_headers | provider.auth_headers

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

                # response = JSONResponse(
                #     content=json.dumps(
                #         {
                #             "data": [
                #                 {
                #                     "id": model.full_name,
                #                     "name": model.name,
                #                     "provider": model.provider,
                #                 }
                #                 for model in models
                #             ]
                #         }
                #     ),
                #     media_type="application/json",
                # )
