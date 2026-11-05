"""Reject forged browser requests before reading forms or changing application state."""

from urllib.parse import urlsplit

from starlette._utils import get_route_path
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send


def _origin(value: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        port = parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)
        return parsed.scheme, parsed.hostname, port
    except ValueError:
        return None


class CSRFProtectionMiddleware:
    """Require a same-origin browser source for web/admin mutations.

    Origin takes precedence over Referer. Missing/opaque sources fail closed.
    API routes authenticate with Authorization, never with browser cookies.
    SQLAdmin also exposes GET actions and logout, so protect those explicitly.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = get_route_path(scope)
            api_request = path == "/api" or path.startswith("/api/")
            changes_state = scope["method"] not in {"GET", "HEAD", "OPTIONS"}
            admin_action = "/action/" in path or path.rstrip("/").endswith("/logout")
            if not api_request and (changes_state or admin_action):
                request = Request(scope)
                source = request.headers.get("origin")
                if source is None:
                    source = request.headers.get("referer", "")
                if (
                    request.headers.get("sec-fetch-site") == "cross-site"
                    or _origin(source) is None
                    or _origin(source) != _origin(str(request.base_url))
                ):
                    response = PlainTextResponse("CSRF verification failed", status_code=403)
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)
