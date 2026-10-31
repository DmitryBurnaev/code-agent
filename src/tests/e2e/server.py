"""Bounded startup checks for the real e2e application process."""

from pathlib import Path
import subprocess
import time

import httpx
import pytest


def wait_for_server(
    process: subprocess.Popen[bytes],
    client: httpx.Client,
    log_path: Path,
    *,
    timeout: float = 60,
) -> None:
    deadline = time.monotonic() + timeout
    last_probe = "no HTTP response"
    while (remaining := deadline - time.monotonic()) > 0:
        if (exit_code := process.poll()) is not None:
            reason = f"Uvicorn exited with code {exit_code}"
            break
        try:
            response = client.get("/api/system/health/", timeout=min(1, remaining))
            last_probe = f"HTTP {response.status_code}"
            if response.status_code == 401:
                return
        except httpx.TransportError as exc:
            last_probe = f"{type(exc).__name__}: {exc}"
        time.sleep(min(0.1, max(0, deadline - time.monotonic())))
    else:
        reason = f"Uvicorn did not become ready within {timeout:g}s"
    pytest.fail(
        f"{reason}; last probe: {last_probe}\n"
        f"Application log ({log_path}):\n{log_path.read_text(errors='replace')[-4000:]}"
    )
