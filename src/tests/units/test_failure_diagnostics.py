"""Failure diagnostics must explain operational failures without logging inputs."""

import errno
import json
import logging
from typing import AsyncGenerator, Callable
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from starlette.requests import Request
from starlette.testclient import TestClient

from src.application import CodeAgentAPP
from src.db.dependencies import get_db_session, get_transactional_session
from src.db.services import SASessionUOW
from src.db.repositories import TokenRepository
from src.db.session import AsyncDBConnectors
from src.db.diagnostics import failure_details
from src.exceptions import StartupError
from src.main import lifespan
from src.utils import universal_exception_handler

PRIVATE_VALUE = "private-request-value"


class DriverUniqueViolationError(Exception):
    """The documented sqlstate interface of a PostgreSQL driver exception."""

    sqlstate = "23505"
    table_name = "users"
    constraint_name = "users_username_key"


def query_failure() -> IntegrityError:
    return IntegrityError(
        f"INSERT INTO users VALUES ('{PRIVATE_VALUE}')",
        {"password": PRIVATE_VALUE},
        DriverUniqueViolationError(f"Duplicate value: {PRIVATE_VALUE}"),
    )


def test_diagnostics_keep_driver_reason_and_stack_without_exception_payload() -> None:
    try:
        raise query_failure()
    except IntegrityError as exc:
        detail = failure_details(exc)
    causes = json.loads(detail)
    assert causes[0]["type"] == "IntegrityError"
    assert "test_diagnostics_keep_driver_reason_and_stack" in detail
    assert causes[1]["sqlstate"] == "23505"
    assert causes[1]["reason"] == "unique constraint violation"
    assert causes[1]["table_name"] == "users"
    assert causes[1]["constraint_name"] == "users_username_key"
    assert PRIVATE_VALUE not in detail
    assert "INSERT INTO" not in detail
    assert "password" not in detail


def test_diagnostics_keep_network_failure_and_handle_cyclic_causes() -> None:
    exc = ConnectionRefusedError(errno.ECONNREFUSED, PRIVATE_VALUE)
    wrapper = RuntimeError(PRIVATE_VALUE)
    wrapper.__cause__ = exc
    exc.__cause__ = wrapper
    detail = failure_details(wrapper)
    assert len(json.loads(detail)) == 2
    assert "ECONNREFUSED" in detail
    assert PRIVATE_VALUE not in detail


async def test_startup_failure_is_logged_without_raw_driver_traceback(
    test_app: CodeAgentAPP,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr("src.main.initialize_database", AsyncMock(side_effect=query_failure()))
    caplog.set_level(logging.INFO)
    with pytest.raises(StartupError) as caught:
        async with lifespan(test_app):
            pytest.fail("Startup must fail")
    assert "Application startup failed" in caplog.text
    assert "23505" in caplog.text
    assert "unique constraint violation" in caplog.text
    assert PRIVATE_VALUE not in caplog.text
    assert caught.value.__suppress_context__ is True
    assert any(record.levelno == logging.CRITICAL for record in caplog.records)


@pytest.mark.parametrize("debug", [False, True])
async def test_api_failure_logs_reason_and_location_without_private_data(
    caplog: pytest.LogCaptureFixture, debug: bool
) -> None:
    caplog.set_level(logging.DEBUG if debug else logging.INFO)
    request = Request({"type": "http", "method": "POST", "path": "/api/example", "headers": []})
    try:
        raise query_failure()
    except IntegrityError as exc:
        response = await universal_exception_handler(request, exc)
    assert response.status_code == 500
    assert b"Internal server error" in response.body
    assert PRIVATE_VALUE.encode() not in response.body
    assert "unique constraint violation" in caplog.text
    assert "test_api_failure_logs_reason_and_location" in caplog.text
    record = caplog.records[-1]
    assert record.__dict__["method"] == "POST"
    assert record.__dict__["path"] == "/api/example"
    assert record.exc_info is None
    assert PRIVATE_VALUE not in caplog.text
    assert "INSERT INTO" not in caplog.text


@pytest.mark.parametrize("operation", ["begin", "flush", "commit", "rollback", "close", "body"])
async def test_transaction_failures_remain_logged_and_propagated(
    operation: str,
    caplog: pytest.LogCaptureFixture,
    mock_db_session: AsyncMock,
    mock_db_session_factory: MagicMock,
) -> None:
    session = mock_db_session
    session.in_transaction.return_value = False
    failure = query_failure()
    if operation != "body":
        getattr(session, operation).side_effect = failure
    caplog.set_level(logging.INFO)
    with pytest.raises(IntegrityError) as caught:
        async with SASessionUOW() as uow:
            if operation == "body":
                raise failure
            if operation == "commit":
                await uow.commit()
            elif operation == "rollback":
                await uow.rollback()
    assert caught.value is failure
    assert "[DB]" in caplog.text
    assert "unique constraint violation" in caplog.text
    assert PRIVATE_VALUE not in caplog.text


@pytest.mark.parametrize("dependency", [get_db_session, get_transactional_session])
async def test_request_session_logs_query_failure_before_rollback(
    dependency: Callable[[], AsyncGenerator[AsyncSession, None]],
    mock_db_session_factory: MagicMock,
    mock_db_session: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    generator = dependency()
    await anext(generator)
    caplog.set_level(logging.INFO)
    with pytest.raises(IntegrityError):
        await generator.athrow(query_failure())
    mock_db_session.rollback.assert_awaited_once()
    mock_db_session.close.assert_awaited_once()
    assert "Request" in caplog.text
    assert "unique constraint violation" in caplog.text
    assert PRIVATE_VALUE not in caplog.text


def test_real_api_route_logs_database_failure_with_safe_response(
    test_app: CodeAgentAPP,
    auth_test_token: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(TokenRepository, "get_by_token", AsyncMock(side_effect=query_failure()))
    caplog.set_level(logging.DEBUG)
    client = TestClient(test_app)
    try:
        response = client.get(
            "/api/system/health/", headers={"Authorization": f"Bearer {auth_test_token}"}
        )
        assert response.status_code == 500
        assert "unique constraint violation" in caplog.text
        assert "GET /api/system/health/" in caplog.text
        assert PRIVATE_VALUE not in caplog.text
        assert auth_test_token not in caplog.text
        assert PRIVATE_VALUE not in response.text
    finally:
        client.close()


async def test_connection_check_logs_root_cause(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    engine = AsyncMock(spec=AsyncEngine)
    engine.connect.side_effect = ConnectionRefusedError(errno.ECONNREFUSED, PRIVATE_VALUE)
    connector = AsyncDBConnectors()
    monkeypatch.setattr(connector, "engine", engine)
    caplog.set_level(logging.INFO)
    with pytest.raises(Exception, match="Failed to ping database"):
        await connector._ping_connection()
    assert "Connection check failed" in caplog.text
    assert "ECONNREFUSED" in caplog.text
    assert PRIVATE_VALUE not in caplog.text
