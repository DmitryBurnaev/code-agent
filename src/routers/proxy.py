from typing import Annotated, Any
import httpx
from fastapi import APIRouter, Depends, Request, Response, HTTPException
from starlette.background import BackgroundTask

from src.dependencies import SettingsDep
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


@router.api_route("/{path:path}", methods=["GET", "HEAD", "OPTIONS"])
async def proxy_request(
    request: Request,
    path: str,
    settings: SettingsDep,
) -> Response:
    """Proxy incoming request to configured target."""
    # TODO: use given model name from requested data to get correct proxy route
    route = _find_matching_route(f"/proxy/{path}", settings.proxy_routes)
    if not route:
        raise HTTPException(status_code=404, detail="No matching proxy route found")

    url = _build_target_url(path, route)
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "connection")}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            response = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=await request.body(),
                params=request.query_params,
            )

            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers),
            )

        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Error proxying request: {str(exc)}")
