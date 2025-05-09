import json
import logging
import urllib.parse
from enum import Enum
from dataclasses import dataclass
from types import TracebackType
from typing import Self, AsyncIterator

import httpx
from starlette.responses import StreamingResponse, Response

from src.exceptions import ProviderProxyError
from src.models import ChatRequest, LLMProvider
from src.services.http import AIProviderHTTPClient
from src.settings import AppSettings
from src.services.providers import ProviderService
from src.utils import Cache

logger = logging.getLogger(__name__)


class ProxyEndpoint(Enum):
    """Available proxy endpoints."""

    CHAT_COMPLETION = "CHAT_COMPLETION"
    CANCEL_CHAT_COMPLETION = "CANCEL_CHAT_COMPLETION"


@dataclass
class ProxyRequestData:
    """Data required for proxy request."""

    method: str
    headers: dict[str, str]
    query_params: dict[str, str]
    body: ChatRequest | None = None
    completion_id: str | None = None
    timeout: float | None = None

    def __str__(self) -> str:
        return (
            f"Requested Proxy: method={self.method} | body={self.body} "
            f"| completion_id={self.completion_id}"
        )


class ProxyService:
    """
    Service for proxying requests to AI providers.

    Handles routing, request transformation and response streaming
    for different AI providers like OpenAI, Anthropic, etc.

    Capabilities:
    - Route requests to appropriate provider endpoints
    - Transform request/response data between providers
    - Handle streaming responses

    Args:
        settings: Application settings containing provider configurations

    Attributes:
        _settings: Stored settings instance
    """

    # Mapping of endpoints to their paths
    _ENDPOINT_PATHS = {
        ProxyEndpoint.CHAT_COMPLETION: "chat/completions",
        ProxyEndpoint.CANCEL_CHAT_COMPLETION: "chat/completions/{completion_id}",
    }

    def __init__(self, settings: AppSettings, http_client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http_client = http_client or AIProviderHTTPClient(settings)
        self._provider_service = ProviderService(settings, self._http_client)
        self._response: httpx.Response | None = None
        self._cache = Cache[str](ttl=settings.chat_completion_id_ttl)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        """
        Store exception info for logging in close
        """
        await self.aclose(exc_type=exc_type, exc_value=exc_value)

    async def aclose(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
    ) -> None:
        """Close all resources and cleanup."""

        logger.debug("ProxyService: closing resources and cleanup")

        # Log any errors that occurred during the request
        if exc_type is not None:
            logger.error(
                "ProxyService: unable to finish proxy request: %r",
                exc_value,
                exc_info=exc_value,
            )

        if self._response is not None:
            await self._response.aclose()
            self._response = None

        await self._http_client.aclose()
        await self._provider_service.close()

    async def handle_request(
        self,
        request_data: ProxyRequestData,
        endpoint: ProxyEndpoint,
    ) -> Response:
        """
        Handle an incoming proxy request by forwarding it to the appropriate provider.

        Args:
            request_data: Encapsulated request data including method, headers, params and body
            endpoint: Which endpoint to proxy to (chat, models, etc.)

        Returns:
            Response from the provider, may be streaming or regular response

        Raises:
            HTTPException: If a provider is not found or the request fails
            ProviderProxyError: If request times out or other provider errors occur
        """
        if not request_data.body and endpoint != ProxyEndpoint.CANCEL_CHAT_COMPLETION:
            raise ProviderProxyError(f"Request body is required for {endpoint}")

        logger.info("ProxyService: %s requested |  %s", endpoint, request_data)
        provider, actual_model = self._extract_provider_requested(request_data, endpoint)

        # Prepare request data
        url = self._build_target_url(provider, endpoint, request_data)
        headers = self._prepare_headers(provider, request_data.headers)
        is_streaming = False
        body = None
        if request_data.body:
            request_data.body.model = actual_model
            is_streaming = request_data.body.stream
            body = {
                **request_data.body.model_dump(),
                **request_data.body.get_extra_params(),
            }

        logger.info("ProxyService: Sending proxy %s request to %s", request_data.method, url)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("ProxyService: Requested body: '%s'", request_data.body)

        request = self._http_client.build_request(
            method=request_data.method,
            url=url,
            headers=headers,
            json=body,
        )

        try:
            httpx_response = await self._http_client.send(request, stream=is_streaming)
            if is_streaming:
                return await self._handle_stream(httpx_response)

            return Response(
                content=httpx_response.content,
                status_code=httpx_response.status_code,
                headers=dict(httpx_response.headers),
            )
        except httpx.TimeoutException as exc:
            error_msg = "Stream timeout" if is_streaming else "Request timeout"
            raise ProviderProxyError(error_msg) from exc

    async def _handle_stream(self, httpx_response: httpx.Response) -> StreamingResponse:
        """Wraps the response in a StreamingResponse for correct closing connection"""

        async def stream_wrapper() -> AsyncIterator[bytes]:
            try:
                async for chunk in httpx_response.aiter_bytes():
                    yield chunk
            except httpx.TimeoutException as exc:
                raise ProviderProxyError("Stream timeout") from exc
            finally:
                # Ensure service cleanup
                await self.aclose()

        response_headers = dict(httpx_response.headers)
        response_headers.update(
            {
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
        result_response = StreamingResponse(
            content=stream_wrapper(),
            status_code=httpx_response.status_code,
            headers=response_headers,
        )
        return result_response

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

    def _extract_provider_requested(
        self,
        request_data: ProxyRequestData,
        endpoint: ProxyEndpoint,
    ) -> tuple[LLMProvider, str]:
        """Extract provider and actual model name from the composite model identifier."""

        if endpoint == ProxyEndpoint.CANCEL_CHAT_COMPLETION:
            completion_id = request_data.completion_id
            if not completion_id:
                raise ProviderProxyError("completion_id is required for cancellation")

            # TODO: use DB storage for caching completion_id -> provider mapping
            provider = self._cache.get(completion_id)
            if not provider:
                raise ProviderProxyError(
                    f"Unable to find provider for completion_id {completion_id}"
                )

            model = f"{provider}__SKIP"

        else:
            model = request_data.body.model if request_data.body else ""

        try:
            provider, model_name = model.split("__", 1)
            llm_provider = self._settings.provider_by_vendor[provider.lower()]
        except ValueError as exc:
            raise ProviderProxyError(
                "Invalid model format. Expected 'provider__model_name', e.g. 'openai__gpt-4'"
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
