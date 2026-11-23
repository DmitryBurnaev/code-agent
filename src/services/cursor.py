"""Cursor subscription adapter and Chat Completions response translation."""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Sequence
import json
import logging
import time
from typing import TYPE_CHECKING, Annotated, TypeVar
from uuid import uuid4

import httpx
from anyio import CancelScope
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.types import Receive, Scope, Send

from agents.protocol import (
    MAX_CURSOR_HISTORY_BYTES,
    CursorDelta,
    CursorDone,
    CursorErrorCode,
    CursorFailure,
    CursorLogin,
    CursorMessage,
    CursorModels,
    CursorRun,
    CursorStatus,
    is_cursor_login_url,
)

if TYPE_CHECKING:
    from src.models import ChatRequest
    from src.settings import AppSettings

logger = logging.getLogger(__name__)
EVENT: TypeAdapter[CursorDelta | CursorDone | CursorFailure] = TypeAdapter(
    Annotated[CursorDelta | CursorDone | CursorFailure, Field(discriminator="type")]
)
ModelT = TypeVar("ModelT", bound=BaseModel)
ResultT = TypeVar("ResultT")
CURSOR_COMPLETION_PREFIX = "chatcmpl-cursor-"
ERRORS = {
    CursorErrorCode.DISCONNECTED: (503, "Connect the Cursor subscription in the admin panel."),
    CursorErrorCode.NOT_CONFIGURED: (
        503,
        "Set CURSOR_AGENTS_SECRET in the application environment and restart code-agent.",
    ),
    CursorErrorCode.AUTH_FAILED: (
        503,
        "The Cursor service rejected its credentials. Check that both services use the same "
        "CURSOR_AGENTS_SECRET.",
    ),
    CursorErrorCode.UNAVAILABLE: (
        503,
        "The Cursor service is unreachable. Start the agents profile and check CURSOR_AGENTS_URL.",
    ),
    CursorErrorCode.PROTOCOL: (
        502,
        "The Cursor service returned an invalid or incomplete response.",
    ),
    CursorErrorCode.TIMEOUT: (504, "The Cursor request timed out."),
    CursorErrorCode.BUSY: (429, "The Cursor service is busy."),
    CursorErrorCode.LIMIT: (429, "The Cursor subscription usage limit was reached."),
    CursorErrorCode.MODEL_NOT_FOUND: (404, "The requested Cursor model is unavailable."),
}


class CursorError(Exception):
    def __init__(self, code: CursorErrorCode) -> None:
        self.code = code
        self.status, self.message = ERRORS[code]
        super().__init__(code)

    def response(self) -> JSONResponse:
        return cursor_error_response(self.status, self.code, self.message)


def cursor_error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message, "type": code}}, status_code=status
    )


class CursorClient:
    """Use only the authenticated internal HTTP interface."""

    def __init__(self, settings: "AppSettings") -> None:
        self.settings = settings

    def _http(self) -> httpx.AsyncClient:
        secret = self.settings.cursor_agents_secret
        if secret is None or not secret.get_secret_value().strip():
            raise CursorError(CursorErrorCode.NOT_CONFIGURED)
        return httpx.AsyncClient(
            base_url=self.settings.cursor_agents_url,
            headers={"Authorization": f"Bearer {secret.get_secret_value()}"},
            timeout=httpx.Timeout(130, connect=5),
            trust_env=False,
        )

    @staticmethod
    def _check(response: httpx.Response) -> None:
        if response.is_success:
            return
        if response.status_code in (401, 403):
            raise CursorError(CursorErrorCode.AUTH_FAILED)
        try:
            failure = CursorFailure.model_validate(response.json())
        except ValidationError, ValueError:
            raise CursorError(CursorErrorCode.UNAVAILABLE) from None
        raise CursorError(failure.code)

    async def _json(self, method: str, path: str, model: type[ModelT]) -> ModelT:
        try:
            async with self._http() as http:
                response = await http.request(method, path)
                self._check(response)
                return model.model_validate_json(response.content)
        except httpx.TimeoutException:
            raise CursorError(CursorErrorCode.TIMEOUT) from None
        except httpx.HTTPError:
            raise CursorError(CursorErrorCode.UNAVAILABLE) from None
        except ValidationError:
            raise CursorError(CursorErrorCode.PROTOCOL) from None

    async def status(self) -> CursorStatus:
        return await self._json("GET", "/auth/status", CursorStatus)

    async def login(self) -> str:
        login = await self._json("POST", "/auth/login", CursorLogin)
        if not is_cursor_login_url(login.url):
            raise CursorError(CursorErrorCode.PROTOCOL)
        return login.url

    async def logout(self) -> CursorStatus:
        return await self._json("POST", "/auth/logout", CursorStatus)

    async def models(self, refresh: bool = False) -> list[str]:
        path = "/models?refresh=true" if refresh else "/models"
        catalog = await self._json("GET", path, CursorModels)
        return catalog.models

    async def run(self, request: CursorRun) -> AsyncGenerator[CursorDelta | CursorDone]:
        try:
            async with self._http() as http:
                async with http.stream("POST", "/run", json=request.model_dump()) as response:
                    if not response.is_success:
                        await response.aread()
                        self._check(response)
                    async for line in response.aiter_lines():
                        event = EVENT.validate_json(line)
                        if isinstance(event, CursorFailure):
                            raise CursorError(event.code)
                        yield event
                        if isinstance(event, CursorDone):
                            return
        except httpx.TimeoutException:
            raise CursorError(CursorErrorCode.TIMEOUT) from None
        except httpx.HTTPError:
            raise CursorError(CursorErrorCode.UNAVAILABLE) from None
        except ValidationError:
            raise CursorError(CursorErrorCode.PROTOCOL) from None
        raise CursorError(CursorErrorCode.PROTOCOL)


class CursorStreamResponse(StreamingResponse):
    def __init__(
        self,
        content: AsyncGenerator[str],
        events: AsyncGenerator[CursorDelta | CursorDone],
    ) -> None:
        super().__init__(
            content,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
        self.events = events

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with CancelScope(shield=True):
                await self.events.aclose()


async def until_disconnect(operation: Awaitable[ResultT], request: Request | None) -> ResultT:
    """Stop upstream work even if the caller disconnects before a response starts."""
    if request is None:
        return await operation

    async def watch() -> None:
        while (await request.receive())["type"] != "http.disconnect":
            pass

    work = asyncio.ensure_future(operation)
    disconnect = asyncio.create_task(watch())
    try:
        finished, _ = await asyncio.wait((work, disconnect), return_when=asyncio.FIRST_COMPLETED)
        if work not in finished:
            raise CursorError(CursorErrorCode.UNAVAILABLE)
        return await work
    finally:
        for task in (work, disconnect):
            if not task.done():
                task.cancel()
        await asyncio.gather(work, disconnect, return_exceptions=True)


async def cursor_chat(
    client: CursorClient,
    chat: "ChatRequest",
    model_id: str,
    allowed_models: Sequence[str],
    request: Request | None,
    user_id: int | None,
) -> Response:
    if model_id not in allowed_models:
        return CursorError(CursorErrorCode.MODEL_NOT_FOUND).response()
    fields = set(await request.json()) if request is not None else chat.model_fields_set
    unsupported = fields - {"model", "messages", "stream"}
    if unsupported:
        return cursor_error_response(
            400,
            "unsupported_parameters",
            f"Unsupported parameters: {', '.join(sorted(unsupported))}",
        )
    if sum(len(message.content.encode()) for message in chat.messages) > MAX_CURSOR_HISTORY_BYTES:
        return cursor_error_response(413, "history_too_large", "The text history is too large.")
    try:
        payload = CursorRun(
            model=model_id,
            messages=[
                CursorMessage.model_validate(message.model_dump()) for message in chat.messages
            ],
        )
    except ValidationError:
        return cursor_error_response(
            400, "invalid_messages", "Send a nonempty list of text messages."
        )

    async def start() -> bool:
        return model_id in await client.models()

    logger.info("Cursor chat requested user_id=%s", user_id)
    try:
        if not await until_disconnect(start(), request):
            raise CursorError(CursorErrorCode.MODEL_NOT_FOUND)
        events = client.run(payload)
        completion: dict[str, str | int] = {
            "id": f"{CURSOR_COMPLETION_PREFIX}{uuid4().hex}",
            "model": chat.model,
            "created": int(time.time()),
        }
        if chat.stream:
            try:
                first = await until_disconnect(anext(events), request)
            except BaseException:
                with CancelScope(shield=True):
                    await events.aclose()
                raise
            return CursorStreamResponse(cursor_sse(first, events, completion, user_id), events)
        try:
            text = await until_disconnect(_collect_text(events), request)
        finally:
            with CancelScope(shield=True):
                await events.aclose()
        return JSONResponse(
            completion
            | {
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": text},
                        "finish_reason": "stop",
                    }
                ],
            }
        )
    except CursorError as exc:
        logger.warning("Cursor chat failed user_id=%s code=%s", user_id, exc.code)
        return exc.response()


async def _collect_text(events: AsyncGenerator[CursorDelta | CursorDone]) -> str:
    return "".join([event.text async for event in events if isinstance(event, CursorDelta)])


async def cursor_sse(
    first: CursorDelta | CursorDone,
    events: AsyncGenerator[CursorDelta | CursorDone],
    completion: dict[str, str | int],
    user_id: int | None,
) -> AsyncGenerator[str]:
    def chunk(delta: dict[str, str], finish: str | None = None) -> str:
        value = completion | {
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        return f"data: {json.dumps(value, ensure_ascii=False)}\n\n"

    yield chunk({"role": "assistant"})
    event = first
    try:
        while isinstance(event, CursorDelta):
            yield chunk({"content": event.text})
            event = await anext(events)
    except CursorError as exc:
        logger.warning("Cursor stream failed user_id=%s code=%s", user_id, exc.code)
        body = json.dumps({"error": {"code": exc.code, "message": exc.message, "type": exc.code}})
        yield f"data: {body}\n\n"
        return
    yield chunk({}, "stop")
    yield "data: [DONE]\n\n"
