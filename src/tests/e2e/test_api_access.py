"""Real Uvicorn + PostgreSQL; only external billing/LLM servers are fixtures."""

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
from threading import Thread
import time
from typing import Any
from uuid import uuid4

from alembic import command
from alembic.config import Config
import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from src.settings.db import DBSettings

ROOT = Path(__file__).resolve().parents[3]
FLAGS = (
    "can_access_admin",
    "can_access_system_api",
    "can_use_llm",
    "can_use_time_tracking",
    "can_access_billing",
)
ROLES = {
    "none": (),
    "system": ("can_access_system_api",),
    "billing": ("can_access_billing",),
    "llm": ("can_use_llm",),
    "admin_panel": ("can_access_admin",),
    "tracker": ("can_use_time_tracking",),
    "superuser": (),
}
OPERATIONS = (
    ("health", "GET", "/api/system/health/", "can_access_system_api"),
    ("info", "GET", "/api/system/info/", "can_access_system_api"),
    ("balance", "GET", "/api/billing/balance/", "can_access_billing"),
    ("models", "GET", "/api/ai-proxy/models", "can_use_llm"),
    ("chat", "POST", "/api/ai-proxy/chat/completions", "can_use_llm"),
    ("stream", "POST", "/api/ai-proxy/chat/completions", "can_use_llm"),
    ("cancel", "DELETE", "/api/ai-proxy/chat/completions/chatcmpl-e2e", "can_use_llm"),
)
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.getenv("RUN_API_E2E") != "1", reason="Set RUN_API_E2E=1 for real PostgreSQL/HTTP tests"
    ),
]


class UpstreamHandler(BaseHTTPRequestHandler):
    calls: list[tuple[str, str]] = []

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def handle_request(self) -> None:
        self.calls.append((self.command, self.path))
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length)) if length else {}
        body: dict[str, Any]
        if self.path == "/billing":
            assert self.headers.get("X-Token") == "e2e-billing-key"
            body = {
                "status": "ok",
                "data": {"settings": {"currency": "rub"}, "billings": [{"final_sum": 12345}]},
            }
        elif self.path == "/v1/models":
            assert self.headers.get("Authorization") == "Bearer e2e-llm-key"
            body = {"data": [{"id": "fixture-model"}]}
        elif self.command == "DELETE":
            body = {"id": "chatcmpl-e2e", "cancelled": True}
        else:
            assert payload.get("model") == "fixture-model"
            body = {
                "id": "chatcmpl-e2e",
                "model": "fixture-model",
                "created": 1,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "e2e-ok"},
                        "finish_reason": "stop",
                    }
                ],
            }
        if payload.get("stream"):
            content = ("data: " + json.dumps(body) + "\n\ndata: [DONE]\n\n").encode()
            content_type = "text/event-stream"
        else:
            content, content_type = json.dumps(body).encode(), "application/json"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    do_GET = handle_request
    do_POST = handle_request
    do_DELETE = handle_request


class TokenParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.token: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "input" and attributes.get("id") == "token-value-input":
            self.token = attributes.get("value")


@dataclass
class Account:
    id: int
    name: str
    token_id: int
    token: str = field(repr=False)


@dataclass
class Harness:
    dsn: str = field(repr=False)
    client: httpx.Client = field(repr=False)
    admin: httpx.Client = field(repr=False)
    artifacts: Path
    accounts: dict[str, Account] = field(default_factory=dict)
    results: list[dict[str, Any]] = field(default_factory=list)
    setup: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def query(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        async def execute() -> list[dict[str, Any]]:
            engine = create_async_engine(self.dsn)
            try:
                async with engine.begin() as connection:
                    rows = await connection.execute(sa.text(sql), params)
                    return [dict(row) for row in rows.mappings()] if rows.returns_rows else []
            finally:
                await engine.dispose()

        return asyncio.run(execute())

    def admin_post(self, path: str, data: dict[str, str], expected: int) -> httpx.Response:
        response = self.admin.post(path, data=data)
        self.setup.append({"method": "POST", "path": path, "status": response.status_code})
        assert response.status_code == expected, f"Provisioning {path}: {response.status_code}"
        return response

    def issue_token(self, user_id: int, name: str, expires: str = "") -> tuple[int, str]:
        response = self.admin_post(
            "/cadm/token/create",
            {
                "user": str(user_id),
                "name": name,
                "expires_at": expires,
                "save": "Save",
            },
            200,
        )
        parser = TokenParser()
        parser.feed(response.text)
        assert parser.token and parser.token != "None", "Issued token missing from create response"
        rows = self.query("SELECT id, token FROM tokens WHERE name = :name", name=name)
        assert len(rows) == 1
        assert rows[0]["token"] != parser.token and len(rows[0]["token"]) == 128
        return rows[0]["id"], parser.token

    def create_account(self, role: str, flags: tuple[str, ...] = ()) -> Account:
        name = f"e2e_{role}"
        data = {
            "username": name,
            "email": f"{name}@example.test",
            "new_password": secrets.token_urlsafe(24),
            "is_active": "y",
            "save": "Save",
        }
        data["repeat_password"] = data["new_password"]
        data.update({flag: "y" for flag in flags})
        if role == "superuser":
            data["is_admin"] = "y"
        self.admin_post("/cadm/user/create", data, 302)
        row = self.query("SELECT * FROM users WHERE username = :name", name=name)[0]
        assert row["is_admin"] is (role == "superuser")
        assert all(row[flag] is (flag in flags) for flag in FLAGS)
        token_id, token = self.issue_token(row["id"], name)
        account = Account(row["id"], name, token_id, token)
        self.accounts[role] = account
        return account

    def update_account(
        self,
        account: Account,
        flags: tuple[str, ...] = (),
        *,
        active: bool = True,
        superuser: bool = False,
    ) -> None:
        data = {"email": f"{account.name}@example.test", "save": "Save"}
        data.update({flag: "y" for flag in flags})
        if active:
            data["is_active"] = "y"
        if superuser:
            data["is_admin"] = "y"
        self.admin_post(f"/cadm/user/edit/{account.id}", data, 302)
        row = self.query("SELECT * FROM users WHERE id = :id", id=account.id)[0]
        assert row["is_active"] is active and row["is_admin"] is superuser
        assert all(row[flag] is (flag in flags) for flag in FLAGS)

    def request(
        self,
        case: str,
        role: str,
        operation: tuple[str, str, str, str],
        expected: int,
        *,
        authorization: str | None = None,
    ) -> httpx.Response:
        name, method, path, _ = operation
        headers = {} if authorization is None else {"Authorization": authorization}
        body = {
            "model": "openai:fixture-model",
            "messages": [{"role": "user", "content": "e2e"}],
            "stream": name == "stream",
        }
        count_before = len(UpstreamHandler.calls)
        response = self.client.request(
            method, path, headers=headers, json=body if method == "POST" else None
        )
        upstream_calls = len(UpstreamHandler.calls) - count_before
        result: dict[str, Any] = {
            "case": case,
            "role": role,
            "operation": name,
            "method": method,
            "path": path,
            "expected": expected,
            "actual": response.status_code,
            "upstream_calls": upstream_calls,
            "passed": False,
        }
        if "application/json" in response.headers.get("content-type", ""):
            result["body"] = response.json()
        else:
            result["body"] = response.text[:500]
        self.results.append(result)
        assert response.status_code == expected, f"{case}/{role}/{name}: {result}"
        if expected in (401, 403):
            assert upstream_calls == 0, "Denied request reached external provider"
            assert "e2e-ok" not in response.text and "123.45" not in response.text
        if expected == 200:
            if name == "balance":
                assert response.json() == {"balance": "123.45", "currency": "RUB"}
                assert upstream_calls == 1
            elif name == "models":
                assert response.json()["data"][0]["id"] == "openai:fixture-model"
            elif name == "health":
                assert response.json()["status"] == "healthy"
            elif name == "info":
                assert "openai" in response.json()["vendors"]
            elif name == "chat":
                assert response.json()["choices"][0]["message"]["content"] == "e2e-ok"
            elif name == "stream":
                assert "text/event-stream" in response.headers["content-type"]
                assert "[DONE]" in response.text and "e2e-ok" in response.text
            elif name == "cancel":
                assert response.json()["cancelled"] is True
        if expected == 204:
            assert response.content == b"" and upstream_calls == 0
        result["passed"] = True
        return response


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@pytest.fixture(scope="module")
def harness(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Harness]:
    work = tmp_path_factory.mktemp("api-access")
    artifacts = Path(os.getenv("E2E_ARTIFACT_DIR", str(work / "results"))).resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    database = "code_agent_e2e_" + uuid4().hex
    password = os.getenv("E2E_POSTGRES_PASSWORD", os.getenv("DB_PASSWORD"))
    if password is None:
        password = DBSettings().password
    connection = sa.URL.create(
        "postgresql+asyncpg",
        username=os.getenv("E2E_POSTGRES_USER", "postgres"),
        password=password,
        host=os.getenv("E2E_POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("E2E_POSTGRES_PORT", "5432")),
        database="postgres",
    )
    dsn = connection.set(database=database).render_as_string(hide_password=False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    UpstreamHandler.calls = []
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    upstream_url = f"http://127.0.0.1:{server.server_port}"
    admin_password = secrets.token_urlsafe(24)
    env = {
        "DB_HOST": connection.host or "127.0.0.1",
        "DB_PORT": str(connection.port),
        "DB_USER": connection.username or "postgres",
        "DB_PASSWORD": connection.password or "",
        "DB_NAME": database,
        "APP_SECRET_KEY": secrets.token_urlsafe(48),
        "VENDOR_ENCRYPTION_KEY": secrets.token_urlsafe(48),
        "ADMIN_USERNAME": "e2e_bootstrap",
        "ADMIN_PASSWORD": admin_password,
        "LOG_LEVEL": "WARNING",
        "LOG_FORMAT": "%(message)s",
        "WEB_SESSION_HTTPS_ONLY": "false",
        "FLAG_OFFLINE_MODE": "false",
        "SELECTEL_BALANCE_URL": upstream_url + "/billing",
        "SELECTEL_BALANCE_TOKEN": "e2e-billing-key",
        "SELECTEL_BALANCE_CACHE_TTL_SECONDS": "0",
        "PYTHONPATH": str(ROOT),
        "API_DOCS_ENABLED": "false",
    }
    previous = {name: os.environ.get(name) for name in env}
    previous_directory = Path.cwd()
    os.environ.update(env)
    # Both migrations and Uvicorn load settings from a clean directory, never the project's .env.
    os.chdir(work)

    async def manage_database(create: bool) -> None:
        assert database.startswith("code_agent_e2e_") and len(database) == 47
        engine = create_async_engine(connection, isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as conn:
                sql = (
                    f'CREATE DATABASE "{database}"'
                    if create
                    else f'DROP DATABASE "{database}" WITH (FORCE)'
                )
                await conn.exec_driver_sql(sql)
        finally:
            await engine.dispose()

    async def migrate() -> None:
        engine = create_async_engine(dsn)
        try:
            async with engine.begin() as conn:

                def upgrade(sync_connection: sa.Connection) -> None:
                    config = Config()
                    config.set_main_option("script_location", str(ROOT / "src" / "migrations"))
                    config.attributes["connection"] = sync_connection
                    command.upgrade(config, "head")

                await conn.run_sync(upgrade)
        finally:
            await engine.dispose()

    process: subprocess.Popen[bytes] | None = None
    created = False
    api = httpx.Client(base_url=f"http://127.0.0.1:{free_port()}", timeout=15, trust_env=False)
    admin = httpx.Client(base_url=api.base_url, timeout=15, trust_env=False)
    run = Harness(dsn, api, admin, artifacts)
    run.metadata.update(
        {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "database": database,
            "test_process": os.getpid(),
            "api_url": str(api.base_url),
            "external_providers": "local HTTP fixtures",
        }
    )
    try:
        asyncio.run(manage_database(True))
        created = True
        asyncio.run(migrate())
        run.metadata["postgres_version"] = run.query("SELECT version() AS version")[0]["version"]
        run.metadata["alembic_head"] = run.query("SELECT version_num FROM alembic_version")[0][
            "version_num"
        ]
        uvicorn = Path(sys.executable).parent / "uvicorn"
        with (work / "app.log").open("wb") as log:
            process = subprocess.Popen(
                [
                    str(uvicorn),
                    "src.main:make_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(api.base_url.port),
                    "--no-access-log",
                ],
                cwd=work,
                env=os.environ.copy(),
                stdout=log,
                stderr=log,
            )
        run.metadata["app_process"] = process.pid
        for _ in range(100):
            assert process.poll() is None, (work / "app.log").read_text()[-4000:]
            try:
                if api.get("/api/system/health/").status_code == 401:
                    break
            except httpx.ConnectError:
                pass
            time.sleep(0.1)
        else:
            pytest.fail("Uvicorn did not become ready")
        run.admin_post(
            "/cadm/login", {"username": "e2e_bootstrap", "password": admin_password}, 302
        )
        vendor_id = run.query("SELECT id FROM vendors WHERE slug = 'openai'")[0]["id"]
        run.admin_post(
            f"/cadm/vendor/edit/{vendor_id}",
            {
                "slug": "openai",
                "api_url": upstream_url + "/v1/",
                "new_api_key": "e2e-llm-key",
                "is_active": "y",
                "save": "Save",
            },
            302,
        )
        for role, flags in ROLES.items():
            run.create_account(role, flags)
        yield run
    finally:
        api.close()
        admin.close()
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        if created:
            asyncio.run(manage_database(False))
            run.metadata["temporary_database_removed"] = True
        os.chdir(previous_directory)
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        run.metadata["completed_at"] = datetime.now(timezone.utc).isoformat()
        run.metadata["upstream_requests"] = len(UpstreamHandler.calls)
        (artifacts / "results.json").write_text(
            json.dumps(
                {"metadata": run.metadata, "provisioning": run.setup, "requests": run.results},
                indent=2,
            ),
            encoding="utf-8",
        )


@pytest.mark.parametrize("role", list(ROLES))
@pytest.mark.parametrize("operation", OPERATIONS, ids=[operation[0] for operation in OPERATIONS])
def test_role_matrix(harness: Harness, role: str, operation: tuple[str, str, str, str]) -> None:
    allowed = role == "superuser" or operation[3] in ROLES[role]
    token = "Bearer " + harness.accounts[role].token
    if allowed and operation[0] == "cancel":
        harness.request("seed-cancel", role, OPERATIONS[5], 200, authorization=token)
    harness.request("role-matrix", role, operation, 200 if allowed else 403, authorization=token)


@pytest.fixture(scope="module")
def invalid_tokens(harness: Harness) -> dict[str, str | None]:
    inactive = harness.create_account(
        "inactive", ("can_access_system_api", "can_access_billing", "can_use_llm")
    )
    harness.update_account(inactive, active=False, superuser=True)
    disabled = harness.create_account("disabled_token", ("can_access_system_api",))
    response = harness.admin.get(f"/cadm/token/action/deactivate?pks={disabled.token_id}")
    assert response.status_code in (302, 303, 307)
    unknown = harness.create_account("deleted_token", ("can_access_system_api",))
    response = harness.admin.delete(f"/cadm/token/delete?pks={unknown.token_id}")
    assert response.status_code == 200
    _, expired = harness.issue_token(
        harness.accounts["superuser"].id, "expired", "2020-01-01 00:00:00"
    )
    valid = harness.accounts["system"].token
    tampered = valid[:-4] + ("B" if valid[-4] == "A" else "A") + valid[-3:]
    return {
        "missing": None,
        "empty": "",
        "bare-bearer": "Bearer",
        "malformed": "not-a-token",
        "tampered": "Bearer " + tampered,
        "expired": "Bearer " + expired,
        "disabled-token": "Bearer " + disabled.token,
        "deleted-token": "Bearer " + unknown.token,
        "inactive-superuser": "Bearer " + inactive.token,
    }


@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "empty",
        "bare-bearer",
        "malformed",
        "tampered",
        "expired",
        "disabled-token",
        "deleted-token",
        "inactive-superuser",
    ],
)
@pytest.mark.parametrize("operation", OPERATIONS, ids=[operation[0] for operation in OPERATIONS])
def test_invalid_authentication(
    harness: Harness,
    invalid_tokens: dict[str, str | None],
    kind: str,
    operation: tuple[str, str, str, str],
) -> None:
    harness.request(
        "invalid-authentication", kind, operation, 401, authorization=invalid_tokens[kind]
    )


def test_grants_revocation_and_superuser_use_existing_token(harness: Harness) -> None:
    account = harness.create_account("mutable", ("can_access_system_api",))
    auth = "Bearer " + account.token
    steps = [
        (("can_access_system_api",), False, 200, 403),
        (("can_access_system_api", "can_access_billing"), False, 200, 200),
        (("can_access_billing",), False, 403, 200),
        ((), False, 403, 403),
        ((), True, 200, 200),
        ((), False, 403, 403),
    ]
    for number, (flags, superuser, system_status, billing_status) in enumerate(steps):
        harness.update_account(account, flags, superuser=superuser)
        harness.request(
            f"existing-token-{number}", "mutable", OPERATIONS[0], system_status, authorization=auth
        )
        harness.request(
            f"existing-token-{number}", "mutable", OPERATIONS[2], billing_status, authorization=auth
        )
    assert (
        harness.query("SELECT count(*) AS count FROM tokens WHERE user_id = :id", id=account.id)[0][
            "count"
        ]
        == 1
    )


def test_token_deactivation_and_reactivation(harness: Harness) -> None:
    account = harness.create_account("reactivate", ("can_access_system_api",))
    auth = "Bearer " + account.token
    harness.request("before-token-disable", "reactivate", OPERATIONS[0], 200, authorization=auth)
    for action, expected in (("deactivate", 401), ("activate", 200)):
        response = harness.admin.get(f"/cadm/token/action/{action}?pks={account.token_id}")
        assert response.status_code in (302, 303, 307)
        harness.request(action, "reactivate", OPERATIONS[0], expected, authorization=auth)


@pytest.mark.parametrize("path", ["/api/ai-proxy/models", "/api/ai-proxy/chat/completions"])
def test_cors_preflight_is_public_and_has_no_data(harness: Harness, path: str) -> None:
    harness.request("cors-preflight", "anonymous", ("preflight", "OPTIONS", path, ""), 204)


def test_database_schema_and_permission_defaults(harness: Harness) -> None:
    rows = harness.query(
        "SELECT column_name, is_nullable, column_default FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'users' AND column_name LIKE 'can_%'"
    )
    assert {row["column_name"] for row in rows} == set(FLAGS)
    assert all(row["is_nullable"] == "NO" and row["column_default"] == "false" for row in rows)
    assert harness.metadata["alembic_head"] == "0006"
