"""Keep browser sessions separate from the mounted admin application."""

from starlette._utils import get_route_path
from starlette.middleware.sessions import SessionMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send
from typing import Any
import logging

from itsdangerous import BadSignature, SignatureExpired
from starlette.requests import HTTPConnection
from starlette.types import Message

logger = logging.getLogger(__name__)


class WebSessionMiddleware(SessionMiddleware):
    def __init__(self, app: ASGIApp, /, *, admin_path: str, **kwargs: Any) -> None:
        super().__init__(app, **kwargs)
        self.admin_path = admin_path.rstrip("/")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            path = get_route_path(scope)
            if path == self.admin_path or path.startswith(self.admin_path + "/"):
                # SQLAdmin owns the session on these routes. Wrapping it in another
                # SessionMiddleware would serialize its session into the web cookie.
                await self.app(scope, receive, send)
                return

            cookie = HTTPConnection(scope).cookies.get(self.session_cookie)
            if not path.startswith("/static/"):
                logger.info(
                    "[web-auth] Session request: method=%s path=%s scheme=%s cookie_present=%s",
                    scope.get("method", scope["type"]),
                    path,
                    scope["scheme"],
                    cookie is not None,
                )
            if cookie is not None:
                try:
                    self.signer.unsign(cookie.encode("utf-8"), max_age=self.max_age)
                except SignatureExpired:
                    logger.warning("[web-auth] Cookie rejected: reason=expired")
                except BadSignature:
                    logger.warning("[web-auth] Cookie rejected: reason=invalid_signature")

            async def diagnostic_send(message: Message) -> None:
                if (
                    message["type"] == "http.response.start"
                    and scope.get("method") == "POST"
                    and path == "/login"
                    and scope.get("session", {}).get("web_user_id") is not None
                    and scope["scheme"] == "http"
                    and "; secure" in self.security_flags
                ):
                    logger.warning(
                        "[web-auth] Login cookie is Secure on HTTP; browser may omit it. "
                        "For local HTTP set WEB_SESSION_HTTPS_ONLY=false and restart."
                    )
                await send(message)

            await super().__call__(scope, receive, diagnostic_send)
            return

        await super().__call__(scope, receive, send)
