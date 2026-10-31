from pathlib import Path
import subprocess
from unittest.mock import Mock

import httpx
import pytest

from src.tests.e2e import server


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    elapsed = [0.0]

    def sleep(seconds: float) -> None:
        elapsed[0] += seconds

    monkeypatch.setattr(server.time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(server.time, "sleep", sleep)
    return elapsed


@pytest.fixture
def process() -> Mock:
    child = Mock(spec=subprocess.Popen)
    child.poll.return_value = None
    return child


@pytest.fixture
def app_log(tmp_path: Path) -> Path:
    path = tmp_path / "app.log"
    path.write_text("Application startup diagnostics\n")
    return path


def test_slow_start_retries_connections_timeouts_and_unready_responses(
    clock: list[float], process: Mock, app_log: Path
) -> None:
    def probe(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/system/health/"
        assert request.extensions["timeout"]["read"] <= 1
        if clock[0] < 3:
            raise httpx.ConnectError("Starting", request=request)
        if clock[0] < 4:
            raise httpx.ReadTimeout("Not serving yet", request=request)
        return httpx.Response(503 if clock[0] < 12 else 401)

    with httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(probe)) as client:
        server.wait_for_server(process, client, app_log)
    assert 12 <= clock[0] < 13


def test_process_exit_fails_immediately_with_log(
    clock: list[float], process: Mock, app_log: Path
) -> None:
    process.poll.return_value = 3
    with httpx.Client(base_url="http://localhost") as client:
        with pytest.raises(pytest.fail.Exception, match="exited with code 3") as failure:
            server.wait_for_server(process, client, app_log)
    assert "Application startup diagnostics" in str(failure.value)
    assert clock[0] == 0


@pytest.mark.parametrize("status", [200, 403, 500])
def test_unexpected_http_status_times_out_with_log(
    clock: list[float], process: Mock, app_log: Path, status: int
) -> None:
    def probe(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status)

    with httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(probe)) as client:
        with pytest.raises(pytest.fail.Exception, match="within 0.25s") as failure:
            server.wait_for_server(process, client, app_log, timeout=0.25)
    assert f"last probe: HTTP {status}" in str(failure.value)
    assert "Application startup diagnostics" in str(failure.value)
    assert clock[0] == 0.25


def test_connection_failure_times_out_with_diagnostics(
    clock: list[float], process: Mock, app_log: Path
) -> None:
    def probe(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    with httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(probe)) as client:
        with pytest.raises(pytest.fail.Exception, match="within 0.25s") as failure:
            server.wait_for_server(process, client, app_log, timeout=0.25)
    assert "ConnectError: Connection refused" in str(failure.value)
    assert "Application startup diagnostics" in str(failure.value)
    assert clock[0] == 0.25
