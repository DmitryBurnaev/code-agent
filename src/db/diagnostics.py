"""Safe database and startup failure details, without exception payloads."""

import errno
import json
from pathlib import Path
import re
import socket
from traceback import walk_tb

from sqlalchemy.exc import StatementError

SQLSTATE_REASONS = {
    "28P01": "invalid database password",
    "28000": "database authentication rejected",
    "3D000": "database does not exist",
    "23502": "not-null constraint violation",
    "23503": "foreign-key constraint violation",
    "23505": "unique constraint violation",
    "42501": "insufficient database privileges",
    "42601": "SQL syntax error",
    "42703": "undefined database column",
    "42P01": "undefined database table",
    "40001": "transaction serialization failure",
    "40P01": "database deadlock",
    "53300": "too many database connections",
    "57014": "database query cancelled",
    "57P03": "database is not accepting connections",
}


def failure_details(exc: BaseException) -> str:
    """Describe causes and stack locations without messages, SQL, locals or inputs.

    Driver messages and even exception str/repr can contain bound values or DSNs.
    Only validated diagnostic codes and code locations cross this boundary.
    SQLAlchemy's orig is followed because a wrapped driver error may not be chained.
    """
    causes: list[dict[str, object]] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        details: dict[str, object] = {"type": type(current).__name__}
        state = getattr(current, "sqlstate", None)
        if isinstance(state, str) and re.fullmatch(r"[0-9A-Z]{5}", state):
            details["sqlstate"] = state
            if reason := SQLSTATE_REASONS.get(state):
                details["reason"] = reason
            for name in ("schema_name", "table_name", "column_name", "constraint_name"):
                identifier = getattr(current, name, None)
                if isinstance(identifier, str) and re.fullmatch(
                    r"[A-Za-z_][A-Za-z0-9_]{0,62}", identifier
                ):
                    details[name] = identifier
        if isinstance(current, OSError) and current.errno is not None:
            details["errno"] = current.errno
            details["reason"] = (
                "hostname resolution failed"
                if isinstance(current, socket.gaierror)
                else errno.errorcode.get(current.errno, "operating system error")
            )
        details["frames"] = [
            f"{Path(frame.f_code.co_filename).name}:{lineno}:{frame.f_code.co_name}"
            for frame, lineno in walk_tb(current.__traceback__)
        ]
        causes.append(details)
        original = current.orig if isinstance(current, StatementError) else None
        current = original or current.__cause__ or current.__context__
    return json.dumps(causes)
