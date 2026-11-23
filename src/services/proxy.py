import json
import logging
import urllib.parse
from enum import Enum
from dataclasses import dataclass, field
from types import TracebackType
from typing import Self, AsyncIterator, Any, Callable

import httpx
from httpx import Headers
from starlette.requests import Request
from starlette.responses import StreamingResponse, Response

from src.constants import VENDOR_ID_SEPARATOR, VendorMode, VendorSlug
from src.db.diagnostics import failure_details
from src.db.models import User, Vendor
from src.db.repositories import VendorRepository
from src.db.services import SASessionUOW
from src.services.cache import CacheProtocol, InMemoryCache
from src.exceptions import VendorProxyError
from src.models import ChatRequest, LLMVendor
from src.modules.auth.permissions import Permission, has_permission
from agents.protocol import CursorErrorCode
from src.services.cursor import (
    CURSOR_COMPLETION_PREFIX,
    CursorClient,
    CursorError,
    cursor_chat,
    cursor_error_response,
)
from src.services.http import VendorHTTPClient
from src.settings import AppSettings

logger = logging.getLogger(__name__)


class ProxyEndpoint(Enum):
    """Available proxy endpoints."""

    CHAT_COMPLETION = "CHAT_COMPLETION"
    CANCEL_CHAT_COMPLETION = "CANCEL_CHAT_COMPLETION"


@dataclass
class ProxyRequestData:
    """Data required for proxy request."""

    method: str
    headers: dict[str, str] | Headers
    query_params: dict[str, str]
    body: ChatRequest | None = None
    completion_id: str | None = None
    timeout: float | None = None

    user: User | None = field(default=None, compare=False, repr=False)
    request: Request | None = field(default=None, compare=False, repr=False)


class ProxyService:
    """
    Service for proxying requests to AI vendors.

    Handles routing, request transformation and response streaming
    for different AI vendors like OpenAI, Anthropic, etc.

    Capabilities:
    - Route requests to appropriate vendor endpoints
    - Transform request/response data between vendors
    - Handle streaming responses

    Args:
        settings: Application settings containing vendor configurations

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
        self._http_client = http_client or VendorHTTPClient(settings)
        self._cache: CacheProtocol = InMemoryCache()

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
                "ProxyService: unable to finish proxy request: %s",
                failure_details(exc_value) if exc_value is not None else exc_type.__name__,
            )

        logger.info("ProxyService: closing resources and cleanup | client: %r", self._http_client)
        # TODO: think about normally closing transport
        # await self._http_client.aclose()

    async def handle_request(
        self,
        request_data: ProxyRequestData,
        endpoint: ProxyEndpoint,
    ) -> Response:
        """
        Handle an incoming proxy request by forwarding it to the appropriate vendor.

        Args:
            request_data: Encapsulated request data including method, headers, params and body
            endpoint: Which endpoint to proxy to (chat, models, etc.)

        Returns:
            Response from the vendor may be streaming or regular response

        Raises:
            HTTPException: If a vendor is not found or the request fails
            VendorProxyError: If request times out or other vendor errors occur
        """
        if not request_data.body and endpoint != ProxyEndpoint.CANCEL_CHAT_COMPLETION:
            raise VendorProxyError(f"Request body is required for {endpoint}")

        if (
            endpoint == ProxyEndpoint.CANCEL_CHAT_COMPLETION
            and request_data.completion_id
            and request_data.completion_id.startswith(CURSOR_COMPLETION_PREFIX)
        ):
            if not has_permission(request_data.user, Permission.AI_SUBSCRIPTIONS):
                return cursor_error_response(403, "permission_denied", "AI subscriptions required.")
            return cursor_error_response(
                501, "unsupported_operation", "Close the request to cancel a Cursor completion."
            )
        vendor, actual_model = await self._extract_vendor_requested(request_data, endpoint)
        if vendor.auth_mode == VendorMode.SUBSCRIPTION:
            if vendor.slug != VendorSlug.CURSOR:
                return cursor_error_response(
                    400,
                    "unsupported_vendor_mode",
                    "Subscription mode is only supported for Cursor.",
                )
            if not has_permission(request_data.user, Permission.AI_SUBSCRIPTIONS):
                return cursor_error_response(403, "permission_denied", "AI subscriptions required.")
            if not vendor.is_active:
                return CursorError(CursorErrorCode.DISCONNECTED).response()
            if request_data.body is None:
                return cursor_error_response(
                    501, "unsupported_operation", "Close the request to cancel."
                )
            return await cursor_chat(
                CursorClient(self._settings),
                request_data.body,
                actual_model,
                vendor.subscription_models,
                request_data.request,
                request_data.user.id if request_data.user else None,
            )
        llm_vendor = LLMVendor.from_vendor(vendor)

        # Prepare request data
        url = self._build_target_url(llm_vendor, endpoint, request_data)
        headers = self._prepare_headers(llm_vendor)
        is_streaming = False
        body = None
        if request_data.body:
            request_data.body.model = actual_model
            is_streaming = request_data.body.stream
            body = {
                **request_data.body.model_dump(),
                **request_data.body.get_extra_params(),
            }

        logger.info("ProxyService[%s]: %s", llm_vendor.slug, endpoint.name)
        request = self._http_client.build_request(
            method=request_data.method,
            url=url,
            headers=headers,
            json=body,
        )

        try:
            httpx_response = await self._http_client.send(request, stream=is_streaming)
            is_bad_response = not httpx_response.is_success
            plain_response_content = await self._read_response(
                httpx_response,
                vendor=llm_vendor.slug,
                stream=is_streaming,
            )
            logger.log(
                logging.WARNING if is_bad_response else logging.DEBUG,
                "ProxyService[%s]: upstream_status=%s streaming=%s",
                llm_vendor.slug,
                httpx_response.status_code,
                is_streaming,
            )

            if not is_bad_response and is_streaming:
                return await self._handle_stream(
                    httpx_response,
                    vendor=llm_vendor.slug,
                    endpoint=endpoint,
                )

            if endpoint == ProxyEndpoint.CANCEL_CHAT_COMPLETION:
                self._save_vendor(httpx_response.content, vendor=llm_vendor.slug, endpoint=endpoint)

            safe_headers = {
                k: v
                for k, v in httpx_response.headers.items()
                if k.lower()
                not in {"transfer-encoding", "content-encoding", "content-length", "connection"}
            }
            return Response(
                content=plain_response_content,
                status_code=httpx_response.status_code,
                headers=safe_headers,
            )

        except httpx.TimeoutException as exc:
            error_msg = "Stream timeout" if is_streaming else "Request timeout"
            raise VendorProxyError(error_msg) from exc

    async def _read_response(
        self, httpx_response: httpx.Response, vendor: str, stream: bool
    ) -> str:
        if stream:
            if httpx_response.is_success:
                # must be iterated in the StreamResponse later in our proxy logic
                plain_response_content = "--"
            else:
                body_iterator = self._stream_wrapper(httpx_response, vendor=vendor)
                content = b"".join([chunk async for chunk in body_iterator])
                plain_response_content = content.decode("utf-8")
        else:
            plain_response_content = httpx_response.content.decode("utf-8")

        return plain_response_content

    async def _stream_wrapper(
        self,
        httpx_response: httpx.Response,
        vendor: str,
        on_chunk_callback: Callable[[bytes], None] | None = None,
    ) -> AsyncIterator[bytes]:
        try:
            async for chunk in httpx_response.aiter_bytes():
                if on_chunk_callback is not None:
                    on_chunk_callback(chunk)
                yield chunk

        except httpx.TimeoutException as exc:
            raise VendorProxyError(f"ProxyService[{vendor}]: Stream timeout") from exc

        else:
            logger.info("ProxyService[%s]: stream iterations completed", vendor)

        finally:
            # Ensure service cleanup
            await self.aclose()

    async def _handle_stream(
        self,
        httpx_response: httpx.Response,
        vendor: str,
        endpoint: ProxyEndpoint,
    ) -> StreamingResponse:
        """Wraps the response in a StreamingResponse for correct closing connection"""

        logger.debug("ProxyService[%s]: stream iterations started", vendor)
        vendor_saved = False

        def save_vendor_callback(chunk: bytes) -> None:
            nonlocal vendor_saved
            if not vendor_saved:
                self._save_vendor(chunk, vendor=vendor, endpoint=endpoint)
                vendor_saved = True

        response_headers = dict(httpx_response.headers)
        response_headers.update(
            {
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
        result_response = StreamingResponse(
            content=self._stream_wrapper(
                httpx_response,
                vendor=vendor,
                on_chunk_callback=save_vendor_callback,
            ),
            status_code=httpx_response.status_code,
            headers=response_headers,
        )
        return result_response

    def _build_target_url(
        self,
        vendor: LLMVendor,
        endpoint: ProxyEndpoint,
        request_data: ProxyRequestData,
    ) -> str:
        """Build a vendor-specific path for the endpoint."""
        path = self._ENDPOINT_PATHS[endpoint]

        # Replace path parameters if needed
        if endpoint == ProxyEndpoint.CANCEL_CHAT_COMPLETION:
            if not request_data.completion_id:
                raise VendorProxyError("completion_id is required for cancellation")

            path = path.format(completion_id=request_data.completion_id)

        return urllib.parse.urljoin(vendor.base_url, path)

    async def _extract_vendor_requested(
        self,
        request_data: ProxyRequestData,
        endpoint: ProxyEndpoint,
    ) -> tuple[Vendor, str]:
        """Extract vendor and actual model name from the composite model identifier."""

        if endpoint == ProxyEndpoint.CANCEL_CHAT_COMPLETION:
            completion_id = request_data.completion_id
            if not completion_id:
                raise VendorProxyError("completion_id is required for cancellation")

            vendor_slug = self._cache_get_vendor(completion_id)
            if not vendor_slug:
                raise VendorProxyError(f"Unable to find vendor for {completion_id=}")

            model = f"{vendor_slug}:SKIP"

        else:
            model = request_data.body.model if request_data.body else ""

        try:
            vendor_slug, model_name = model.split(VENDOR_ID_SEPARATOR, 1)
            async with SASessionUOW() as uow:
                slug = vendor_slug.lower().strip()
                vendor = await VendorRepository(session=uow.session).get_by_slug(slug)
                if not vendor:
                    raise VendorProxyError(f"Unable to find vendor '{vendor_slug}'")

        except ValueError as exc:
            raise VendorProxyError(
                "Invalid model format. Expected 'vendor:model_id', e.g. 'openai:gpt-4'"
            ) from exc

        return vendor, model_name

    @staticmethod
    def _prepare_headers(vendor: LLMVendor) -> dict[str, str]:
        """Prepare headers for proxy request with auth if configured."""
        result_headers = {
            "accept": "application/json",
            "content-type": "application/json",
        }
        return result_headers | vendor.auth_headers

    def _save_vendor(
        self,
        resp_content: bytes | str,
        vendor: str,
        endpoint: ProxyEndpoint,
    ) -> None:
        if endpoint != ProxyEndpoint.CHAT_COMPLETION:
            logger.debug(
                "ProxyService[%s]: Skip saving vendor for non-completion request",
                vendor,
            )
            return

        completion_id = self._extract_completion_id(chunk_data=resp_content, vendor=vendor)
        self._cache_set_vendor(completion_id, vendor)
        logger.debug(
            "ProxyService[%s]: saved for completion_id %s for response",
            vendor,
            completion_id,
        )

    @staticmethod
    def _extract_completion_id(chunk_data: bytes | str, vendor: str) -> str:

        if isinstance(chunk_data, bytes):
            chunk_data = chunk_data.decode("utf-8")

        if chunk_data.startswith("data:"):
            first_chunk = chunk_data.split("\n\n")[0]
            chunk_data = first_chunk.removeprefix("data: ").removesuffix("\n\n")

        content: dict[str, Any]
        try:
            content = json.loads(chunk_data)
            completion_id = content["id"]
        except json.decoder.JSONDecodeError as exc:
            raise VendorProxyError("Unable to decode upstream streaming chunk") from exc
        except KeyError as exc:
            raise VendorProxyError("Missed completion_id in response") from exc

        return str(completion_id)

    def _cache_set_vendor(self, completion_id: str, vendor: str) -> None:
        key = f"completion__{completion_id}"
        self._cache.set(key, vendor)

    def _cache_get_vendor(self, completion_id: str) -> str | None:
        key = f"completion__{completion_id}"
        cached = self._cache.get(key)
        return str(cached) if cached else None
