"""Exercise the actual subprocess and private HTTP contract using a test executable."""

import asyncio
import json
import os
from pathlib import Path
import sys
import textwrap

import httpx
import pytest

from agents.app import CursorCLI, create_app
from agents.protocol import CursorMessage, CursorRun

FAKE_CLI = r"""
import json
import os
from pathlib import Path
import sys
import time

args = sys.argv[1:]
auth = Path(os.environ["XDG_CONFIG_HOME"]) / "cursor" / "auth.json"
if args == ["login"]:
    print("Open https://cursor.com/login?challenge=fixture", flush=True)
    auth.parent.mkdir(parents=True)
    auth.write_text('{"fixture": true}')
elif args == ["logout"]:
    auth.unlink()
elif args == ["models"]:
    assert auth.is_file()
    print("Available models\nfixture - Fixture\nauto - Auto")
else:
    assert auth.is_file()
    assert args[args.index("--model") + 1] == "fixture"
    assert args[args.index("--mode") + 1] == "ask"
    assert "CURSOR_AGENTS_SECRET" not in os.environ
    config = json.loads((Path(os.environ["CURSOR_CONFIG_DIR"]) / "cli-config.json").read_text())
    assert "Shell(*)" in config["permissions"]["deny"]
    instruction, history = sys.stdin.read().split("\n", 1)
    assert instruction.startswith("Continue this conversation.")
    messages = json.loads(history)
    print(json.dumps({"type": "system", "subtype": "init", "apiKeySource": "login"}), flush=True)
    print(json.dumps({
        "type": "assistant", "timestamp_ms": 1,
        "message": {"content": [{"type": "text", "text": "hello"}]},
    }), flush=True)
    match messages[-1]["content"]:
        case "hold":
            time.sleep(60)
        case "quota":
            print("subscription usage limit", file=sys.stderr)
            sys.exit(1)
        case "tool":
            print(json.dumps({"type": "tool_call", "subtype": "started"}), flush=True)
            sys.exit(1)
    print(json.dumps({
        "type": "assistant", "message": {"content": [{"type": "text", "text": "hello"}]},
    }), flush=True)
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "hello"}))
"""


@pytest.fixture
def cli(tmp_path: Path) -> CursorCLI:
    executable = tmp_path / "agent"
    executable.write_text(f"#!{sys.executable}\n{textwrap.dedent(FAKE_CLI)}")
    executable.chmod(0o700)
    return CursorCLI(executable, tmp_path / "auth-state", uid=os.getuid())


async def connect(cli: CursorCLI) -> None:
    assert await cli.login() == "https://cursor.com/login?challenge=fixture"
    assert cli.login_task is not None
    await asyncio.wait_for(cli.login_task, timeout=5)
    assert cli.status().state == "logged_in"


def run_request(prompt: str) -> CursorRun:
    return CursorRun(model="fixture", messages=[CursorMessage(role="user", content=prompt)])


async def test_private_api_login_catalog_run_and_logout(cli: CursorCLI) -> None:
    app = create_app(cli, "fixture-shared-secret")
    transport = httpx.ASGITransport(app)
    async with httpx.AsyncClient(transport=transport, base_url="http://agents") as client:
        assert (await client.get("/auth/status")).status_code == 401
        client.headers["Authorization"] = "Bearer fixture-shared-secret"
        login = await client.post("/auth/login")
        assert login.json() == {"url": "https://cursor.com/login?challenge=fixture"}
        assert cli.login_task is not None
        await asyncio.wait_for(cli.login_task, timeout=5)

        # A fresh runner can use only the persisted authentication state.
        restarted = CursorCLI(cli.executable, cli.state, uid=os.getuid())
        assert restarted.status().state == "logged_in"
        assert (await client.get("/models")).json() == {"models": ["fixture", "auto"]}
        response = await client.post("/run", json=run_request("test").model_dump())
        assert response.headers["content-type"] == "application/x-ndjson"
        assert [json.loads(line) for line in response.text.splitlines()] == [
            {"type": "delta", "text": "hello"},
            {"type": "done"},
        ]
        assert (await client.post("/auth/logout")).json()["state"] == "logged_out"
        assert restarted.status().state == "logged_out"
        assert (await client.get("/models")).status_code == 503


async def test_runner_rejects_parallel_work_and_cleans_up_cancelled_process(cli: CursorCLI) -> None:
    await connect(cli)
    run = cli.run(run_request("hold"))
    assert json.loads(await anext(run)) == {"type": "delta", "text": "hello"}
    process = cli.process
    assert process is not None
    assert [json.loads(line) async for line in cli.run(run_request("test"))] == [
        {"type": "error", "code": "agents_busy"}
    ]
    await run.aclose()
    assert process.returncode is not None
    assert cli.process is None
    assert not cli.lock.locked()


async def test_runner_reaps_process_on_timeout(
    cli: CursorCLI, monkeypatch: pytest.MonkeyPatch
) -> None:
    await connect(cli)
    monkeypatch.setattr("agents.app.RUN_TIMEOUT", 0.5)
    events = [json.loads(line) async for line in cli.run(run_request("hold"))]
    assert events[-1] == {"type": "error", "code": "upstream_timeout"}
    assert cli.process is None
    assert not cli.lock.locked()


@pytest.mark.parametrize(
    ("prompt", "code"), [("quota", "subscription_usage_limit"), ("tool", "upstream_error")]
)
async def test_runner_reports_terminal_failure(cli: CursorCLI, prompt: str, code: str) -> None:
    await connect(cli)
    events = [json.loads(line) async for line in cli.run(run_request(prompt))]
    assert events[-1] == {"type": "error", "code": code}
    assert cli.status().error == code
