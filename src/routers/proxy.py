import json
from typing import Any, AsyncGenerator

import httpx
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import StreamingResponse

from src.dependencies import SettingsDep
from src.models import RequestChatCompletion
from src.settings import ProxyRoute

__all__ = ["router"]


router = APIRouter(
    prefix="/ai-proxy",
    tags=["proxy"],
    responses={404: {"description": "Not found"}},
)


def _find_matching_route(path: str, routes: list[ProxyRoute]) -> ProxyRoute | None:
    """Find matching proxy route for given path."""
    for route in routes:
        if path.startswith(route.source_path):
            return route
    return None


def _build_target_url(path: str, route: ProxyRoute) -> str:
    """Build target URL for proxy request."""
    if route.strip_path:
        path = path.replace(route.source_path, "", 1)
    return f"{route.target_url.rstrip('/')}/{path.lstrip('/')}"


def _prepare_headers(request: Request, route: ProxyRoute) -> dict[str, str]:
    """Prepare headers for proxy request with auth if configured."""
    # Copy original headers excluding host and connection
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "connection")}

    # Add auth header if token is configured
    if route.auth_token:
        headers["Authorization"] = f"{route.auth_type} {route.auth_token.get_secret_value()}"

    return headers


async def _get_request_body(request: Request) -> tuple[Any, bool]:
    """
    Get request body and streaming flag based on content type and request data.
    Returns tuple of (body, is_streaming).
    """
    content_type = request.headers.get("content-type", "").lower()
    body = await request.body()

    if "application/json" in content_type:
        try:
            data = json.loads(body)
            # Check if streaming is requested
            is_streaming = isinstance(data, dict) and data.get("stream", False)
            return data, is_streaming
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON body")
    return body, False


async def _stream_response(response: httpx.Response) -> AsyncGenerator[bytes, None]:
    """Stream response chunks with proper error handling."""
    try:
        async for chunk in response.aiter_bytes():
            # Add proper SSE formatting if needed
            if chunk.strip():
                yield chunk
    except httpx.HTTPError as e:
        # Log error and close connection gracefully
        print(f"Streaming error: {e}")
        yield b"data: [DONE]\n\n"
    finally:
        await response.aclose()


@router.api_route(
    "/test/{path:path}", methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "DELETE", "PATCH"]
)
async def proxy_request(
    request: Request,
    path: str,
    settings: SettingsDep,
) -> Response | StreamingResponse:
    """
    Proxy incoming request to configured target.
    Supports all HTTP methods and handles both regular and streaming responses.
    """
    route = _find_matching_route(f"/proxy/{path}", settings.proxy_routes)
    if not route:
        raise HTTPException(status_code=404, detail="No matching proxy route found")

    url = _build_target_url(path, route)
    headers = _prepare_headers(request, route)

    # Get request body and check if streaming is requested
    body, is_streaming = (
        await _get_request_body(request)
        if request.method in ("POST", "PUT", "PATCH")
        else (None, False)
    )

    # Create httpx client with proper timeout for streaming
    timeout = httpx.Timeout(None) if is_streaming else httpx.Timeout(route.timeout)

    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        try:
            response = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                json=body if isinstance(body, (dict, list)) else None,
                content=body if not isinstance(body, (dict, list)) else None,
                params=request.query_params,
                stream=is_streaming,
            )

            if is_streaming:
                # Set up streaming response with appropriate headers
                response_headers = dict(response.headers)
                response_headers.update(
                    {
                        "Content-Type": "text/event-stream",
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                    }
                )

                return StreamingResponse(
                    _stream_response(response),
                    status_code=response.status_code,
                    headers=response_headers,
                )

            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers),
            )

        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Error proxying request: {str(exc)}")


@router.api_route("/{path:path}", methods=["POST"])
async def proxy_ai_request(
    request: Request,
    chat_completion_request: RequestChatCompletion,
    path: str,
    settings: SettingsDep,
) -> Response | StreamingResponse:
    """
    Proxy incoming request to configured target.
    Supports all HTTP methods and handles both regular and streaming responses.
    """
    route = _find_matching_route(f"/proxy/{path}", settings.proxy_routes)
    if not route:
        raise HTTPException(status_code=404, detail="No matching proxy route found")

    url = _build_target_url(path, route)
    headers = _prepare_headers(request, route)
    is_streaming = chat_completion_request.stream

    # Get request body and check if streaming is requested
    # body, is_streaming = (
    #     await _get_request_body(request)
    #     if request.method in ("POST", "PUT", "PATCH")
    #     else (None, False)
    # )

    # Create httpx client with proper timeout for streaming
    timeout = httpx.Timeout(None) if is_streaming else httpx.Timeout(route.timeout)

    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        try:
            response = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                json=chat_completion_request.model_dump(),
                params=request.query_params,
                # stream=is_streaming,
            )

            if is_streaming:
                # Set up streaming response with appropriate headers
                response_headers = dict(response.headers)
                response_headers.update(
                    {
                        "Content-Type": "text/event-stream",
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                    }
                )

                return StreamingResponse(
                    _stream_response(response),
                    status_code=response.status_code,
                    headers=response_headers,
                )

            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers),
            )

        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Error proxying request: {str(exc)}")
