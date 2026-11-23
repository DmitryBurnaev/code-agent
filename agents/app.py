"""Serve authenticated text requests through the pinned Cursor CLI."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import aclosing, asynccontextmanager, suppress
import hmac
import json
import logging
import os
from pathlib import Path
import re
import signal
import tempfile
from time import monotonic
from typing import Annotated, Literal

from anyio import CancelScope
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.types import Receive, Scope, Send

from agents.protocol import (
    MAX_CURSOR_HISTORY_BYTES,
    MODEL_ID,
    CursorDelta,
    CursorDone,
    CursorErrorCode,
    CursorFailure,
    CursorLogin,
    CursorModels,
    CursorRun,
    CursorStatus,
    is_cursor_login_url,
)

logger = logging.getLogger(__name__)
CLI_UID = 1008
RUN_TIMEOUT = 120
AUTH_PATHS = (".config/cursor/auth.json", ".cursor/auth.json")
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
CLI_MODEL_LINE = re.compile(rf"^({MODEL_ID.pattern})\s+-\s+\S")
RESTRICTIONS = {
    "version": 1,
    "editor": {"vimMode": False},
    "approvalMode": "allowlist",
    "sandbox": {"mode": "enabled", "networkAccess": "disabled", "readBoundary": "workspace"},
    "permissions": {
        "allow": [],
        "deny": [
            "Read(**)",
            "Read(/**)",
            "Write(**)",
            "Write(/**)",
            "Shell(*)",
            "WebFetch(*)",
            "Mcp(*:*)",
        ],
    },
}


class CLIError(Exception):
    def __init__(self, code: CursorErrorCode, status: int = 502) -> None:
        self.code = code
        self.status = status
        super().__init__(code)


def parse_models(output: str) -> list[str]:
    models = []
    for line in ANSI_ESCAPE.sub("", output).splitlines():
        if match := CLI_MODEL_LINE.match(line.strip()):
            models.append(match.group(1))
    if not models:
        raise CLIError(CursorErrorCode.PROTOCOL)
    return list(dict.fromkeys(models))


def cli_failure(output: bytes) -> CLIError:
    message = output.lower()
    if any(word in message for word in (b"usage limit", b"rate limit", b"quota exceeded")):
        return CLIError(CursorErrorCode.LIMIT, 429)
    if any(word in message for word in (b"not authenticated", b"not logged in", b"login required")):
        return CLIError(CursorErrorCode.DISCONNECTED, 503)
    if any(
        word in message for word in (b"unknown model", b"invalid model", b"model not available")
    ):
        return CLIError(CursorErrorCode.MODEL_NOT_FOUND, 404)
    return CLIError(CursorErrorCode.PROTOCOL)


class CursorCLI:
    def __init__(self, executable: Path, state: Path, uid: int = CLI_UID) -> None:
        self.executable = executable
        self.state = state
        self.uid = uid
        self.lock = asyncio.Lock()
        self.login_task: asyncio.Task[None] | None = None
        self.process: asyncio.subprocess.Process | None = None
        self.error: CursorErrorCode | None = None
        self.catalog: list[str] = []
        self.catalog_expires = 0.0
        self.logging_out = False

    def status(self) -> CursorStatus:
        if self.login_task is not None and not self.login_task.done():
            return CursorStatus(state="pending")
        connected = self._has_credentials()
        if self.error == CursorErrorCode.DISCONNECTED:
            connected = False
        state: Literal["logged_in", "error", "logged_out"] = (
            "logged_in" if connected else "error" if self.error else "logged_out"
        )
        return CursorStatus(state=state, error=self.error)

    def _stored_auth(self, path: str) -> Path:
        return self.state / path

    @asynccontextmanager
    async def _command(
        self, *args: str, merge_output: bool = False, save_auth: bool = True
    ) -> AsyncGenerator[asyncio.subprocess.Process]:
        with tempfile.TemporaryDirectory(prefix="cursor-") as directory:
            home = Path(directory).resolve()
            workspace = home / "workspace"
            config = home / ".cursor"
            workspace.mkdir()
            config.mkdir()
            (config / "cli-config.json").write_text(json.dumps(RESTRICTIONS), encoding="utf-8")
            for relative in AUTH_PATHS:
                saved = self._stored_auth(relative)
                if saved.is_file():
                    restored = home / relative
                    restored.parent.mkdir(parents=True, exist_ok=True)
                    restored.write_bytes(saved.read_bytes())
                    restored.chmod(0o600)
            if os.getuid() != self.uid:
                for path in (home, *home.rglob("*")):
                    os.chown(path, self.uid, self.uid)
            environment = {
                "HOME": str(home),
                "XDG_CONFIG_HOME": str(home / ".config"),
                "XDG_CACHE_HOME": str(home / ".cache"),
                "XDG_DATA_HOME": str(home / ".local" / "share"),
                "CURSOR_CONFIG_DIR": str(config),
                "NO_OPEN_BROWSER": "1",
                "NO_COLOR": "1",
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "LANG": "C.UTF-8",
            }
            try:
                process = await asyncio.create_subprocess_exec(
                    str(self.executable),
                    *args,
                    cwd=workspace,
                    env=environment,
                    user=self.uid if os.getuid() != self.uid else None,
                    group=self.uid if os.getuid() != self.uid else None,
                    extra_groups=[] if os.getuid() != self.uid else None,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT if merge_output else asyncio.subprocess.PIPE,
                    start_new_session=True,
                    limit=1024 * 1024,
                    umask=0o077,
                )
            except OSError:
                raise CLIError(CursorErrorCode.UNAVAILABLE, 503) from None
            self.process = process
            try:
                yield process
            finally:
                with CancelScope(shield=True):
                    self._stop()
                    # Drain the pipes too. A full pipe can keep Process.wait() pending.
                    await process.communicate()
                self.process = None
                if save_auth and not self.logging_out:
                    self._save_auth(home)

    def _save_auth(self, home: Path) -> None:
        for relative in AUTH_PATHS:
            source = home / relative
            if (
                not source.is_file()
                or source.is_symlink()
                or not source.resolve().is_relative_to(home)
            ):
                continue
            target = self._stored_auth(relative)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as file:
                file.write(source.read_bytes())
                temporary = Path(file.name)
            temporary.replace(target)

    def _stop(self) -> None:
        if self.process is not None:
            with suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGKILL)

    async def login(self) -> str:
        if (
            self.logging_out
            or self.lock.locked()
            or self.status().state in {"pending", "logged_in"}
        ):
            raise CLIError(CursorErrorCode.BUSY, 429)
        ready: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self.login_task = asyncio.create_task(self._login(ready))
        return await ready

    async def _login(self, ready: asyncio.Future[str]) -> None:
        self.error = None
        self.catalog_expires = 0
        try:
            async with (
                self.lock,
                asyncio.timeout(300),
                self._command("login", merge_output=True) as process,
            ):
                assert process.stdout is not None
                async for line in process.stdout:
                    if ready.done():
                        continue
                    output = ANSI_ESCAPE.sub("", line.decode(errors="replace"))
                    for link in re.findall(r"https://[^\s<>\"]+", output):
                        if is_cursor_login_url(link):
                            ready.set_result(link)
                            break
                if await process.wait() != 0 or not ready.done():
                    raise CLIError(CursorErrorCode.PROTOCOL)
            if not self._has_credentials():
                raise CLIError(CursorErrorCode.DISCONNECTED, 503)
        except (TimeoutError, CLIError, ValueError, OSError) as exc:
            error = (
                exc
                if isinstance(exc, CLIError)
                else CLIError(
                    (
                        CursorErrorCode.TIMEOUT
                        if isinstance(exc, TimeoutError)
                        else CursorErrorCode.PROTOCOL
                    ),
                    504 if isinstance(exc, TimeoutError) else 502,
                )
            )
            self.error = error.code
            logger.warning("Cursor login failed code=%s", error.code)
            if not ready.done():
                ready.set_exception(error)
        finally:
            if not ready.done():
                ready.cancel()

    def _has_credentials(self) -> bool:
        return any(self._stored_auth(path).is_file() for path in AUTH_PATHS)

    async def logout(self) -> CursorStatus:
        if self.logging_out:
            raise CLIError(CursorErrorCode.BUSY, 429)
        self.logging_out = True
        self.catalog_expires = 0
        self._stop()
        try:
            if self.login_task is not None and not self.login_task.done():
                self.login_task.cancel()
                await asyncio.gather(self.login_task, return_exceptions=True)
            async with self.lock:
                try:
                    if self._has_credentials():
                        async with (
                            asyncio.timeout(15),
                            self._command("logout", save_auth=False) as process,
                        ):
                            await process.communicate()
                            if process.returncode != 0:
                                logger.warning(
                                    "Cursor CLI logout failed; clearing local credentials"
                                )
                except CLIError, TimeoutError:
                    logger.warning("Cursor CLI logout unavailable; clearing local credentials")
                finally:
                    for relative in AUTH_PATHS:
                        self._stored_auth(relative).unlink(missing_ok=True)
                    self.error = None
        finally:
            self.logging_out = False
        return self.status()

    async def models(self, refresh: bool) -> list[str]:
        self._require_connected()
        if not refresh and self.catalog_expires > monotonic():
            return self.catalog
        if self.lock.locked():
            raise CLIError(CursorErrorCode.BUSY, 429)
        async with self.lock:
            try:
                async with asyncio.timeout(15), self._command("models") as process:
                    output, error = await process.communicate()
                    if process.returncode:
                        raise cli_failure(error or output)
                self.catalog = parse_models(output.decode(errors="replace"))
            except TimeoutError:
                self.catalog_expires = 0
                self.error = CursorErrorCode.TIMEOUT
                raise CLIError(self.error, 504) from None
            except CLIError as exc:
                self.catalog_expires = 0
                self.error = exc.code
                raise
            self.error = None
            self.catalog_expires = monotonic() + 60
            return self.catalog

    def _require_connected(self) -> None:
        if self.logging_out or self.status().state != "logged_in":
            raise CLIError(CursorErrorCode.DISCONNECTED, 503)

    async def run(self, payload: CursorRun) -> AsyncGenerator[str]:
        try:
            if payload.model not in await self.models(refresh=False):
                raise CLIError(CursorErrorCode.MODEL_NOT_FOUND, 404)
            if self.lock.locked():
                raise CLIError(CursorErrorCode.BUSY, 429)
            async with (
                self.lock,
                asyncio.timeout(RUN_TIMEOUT),
                self._command(
                    "--print",
                    "--mode",
                    "ask",
                    "--sandbox",
                    "enabled",
                    "--model",
                    payload.model,
                    "--output-format",
                    "stream-json",
                    "--stream-partial-output",
                ) as process,
            ):
                async with aclosing(self._read_turn(process, payload)) as events:
                    async for event in events:
                        yield event
            self.error = None
        except (TimeoutError, ValueError, KeyError, TypeError, OSError, CLIError) as exc:
            code = (
                exc.code
                if isinstance(exc, CLIError)
                else (
                    CursorErrorCode.TIMEOUT
                    if isinstance(exc, TimeoutError)
                    else CursorErrorCode.PROTOCOL
                )
            )
            if not self.logging_out and code not in {
                CursorErrorCode.BUSY,
                CursorErrorCode.MODEL_NOT_FOUND,
            }:
                self.error = code
            logger.warning("Cursor run failed code=%s", code)
            yield CursorFailure(code=code).model_dump_json() + "\n"

    async def _read_turn(
        self, process: asyncio.subprocess.Process, payload: CursorRun
    ) -> AsyncGenerator[str]:
        stdin, stdout, stderr = process.stdin, process.stdout, process.stderr
        assert stdin is not None and stdout is not None and stderr is not None

        async def send_prompt() -> None:
            history = json.dumps(
                [message.model_dump() for message in payload.messages], ensure_ascii=False
            )
            prompt = (
                "Continue this conversation. Return only the next assistant message as text.\n"
                f"{history}"
            )
            stdin.write(prompt.encode())
            await stdin.drain()
            stdin.close()

        async def drain_error() -> bytes:
            tail = b""
            while chunk := await stderr.read(4096):
                tail = (tail + chunk)[-8192:]
            return tail

        writer = asyncio.create_task(send_prompt())
        reader = asyncio.create_task(drain_error())
        authenticated = False
        streamed = False
        result: str | None = None
        try:
            async for line in stdout:
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise CLIError(CursorErrorCode.PROTOCOL)
                event_type = event.get("type")
                if event_type == "system" and event.get("subtype") == "init":
                    if event.get("apiKeySource") != "login":
                        raise CLIError(CursorErrorCode.DISCONNECTED, 503)
                    authenticated = True
                if event_type in {"tool_call", "tool_use"}:
                    raise CLIError(CursorErrorCode.PROTOCOL)
                if (
                    authenticated
                    and event_type == "assistant"
                    and ("timestamp_ms" in event and "model_call_id" not in event)
                ):
                    for content in event["message"]["content"]:
                        if content.get("type") == "text":
                            delta = CursorDelta(text=content["text"])
                            streamed = True
                            yield delta.model_dump_json() + "\n"
                if event_type == "result" and event.get("subtype") == "success":
                    if event.get("is_error") is False and isinstance(event.get("result"), str):
                        result = event["result"]
            exit_code = await process.wait()
            error_output = await reader
            if exit_code:
                raise cli_failure(error_output)
            await writer
            if not authenticated or result is None:
                raise CLIError(CursorErrorCode.PROTOCOL)
            if not streamed and result:
                yield CursorDelta(text=result).model_dump_json() + "\n"
            yield CursorDone().model_dump_json() + "\n"
        finally:
            with CancelScope(shield=True):
                for task in (writer, reader):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(writer, reader, return_exceptions=True)


class RunResponse(StreamingResponse):
    def __init__(self, events: AsyncGenerator[str]) -> None:
        super().__init__(events, media_type="application/x-ndjson")
        self.events = events

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with CancelScope(shield=True):
                await self.events.aclose()


def create_app(cli: CursorCLI, secret: str) -> FastAPI:
    async def check_secret(authorization: Annotated[str, Header()] = "") -> None:
        if not secret or not hmac.compare_digest(
            authorization.encode(), f"Bearer {secret}".encode()
        ):
            raise HTTPException(status_code=401, detail="Unauthorized")

    app = FastAPI(
        docs_url=None, redoc_url=None, openapi_url=None, dependencies=[Depends(check_secret)]
    )

    @app.exception_handler(CLIError)
    async def handle_cli_error(_request: Request, exc: CLIError) -> JSONResponse:
        return JSONResponse(CursorFailure(code=exc.code).model_dump(), status_code=exc.status)

    @app.get("/health")
    async def health() -> JSONResponse:
        available = os.access(cli.executable, os.X_OK)
        return JSONResponse({"cli_available": available}, status_code=200 if available else 503)

    @app.get("/auth/status")
    async def status() -> CursorStatus:
        return cli.status()

    @app.post("/auth/login")
    async def login() -> CursorLogin:
        return CursorLogin(url=await cli.login())

    @app.post("/auth/logout")
    async def logout() -> CursorStatus:
        return await cli.logout()

    @app.get("/models")
    async def models(refresh: bool = False) -> CursorModels:
        return CursorModels(models=await cli.models(refresh))

    @app.post("/run")
    async def run(payload: CursorRun) -> StreamingResponse:
        if (
            sum(len(message.content.encode()) for message in payload.messages)
            > MAX_CURSOR_HISTORY_BYTES
        ):
            raise HTTPException(status_code=413, detail="Text history is too large")
        return RunResponse(cli.run(payload))

    return app


def app_factory() -> FastAPI:
    cli = CursorCLI(Path("/opt/cursor/dist-package/cursor-agent"), Path("/var/lib/cursor-agent"))
    return create_app(cli, os.environ.get("CURSOR_AGENTS_SECRET", ""))
