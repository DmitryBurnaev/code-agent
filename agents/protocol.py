"""Data exchanged between code-agent and the Cursor service."""

import re
from enum import StrEnum
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:+-]{0,199}")
MAX_CURSOR_HISTORY_BYTES = 1024 * 1024


class CursorErrorCode(StrEnum):
    DISCONNECTED = "subscription_not_connected"
    NOT_CONFIGURED = "agents_not_configured"
    AUTH_FAILED = "agents_auth_failed"
    UNAVAILABLE = "upstream_unavailable"
    PROTOCOL = "upstream_error"
    TIMEOUT = "upstream_timeout"
    BUSY = "agents_busy"
    LIMIT = "subscription_usage_limit"
    MODEL_NOT_FOUND = "model_not_found"


class CursorStatus(BaseModel):
    state: Literal["logged_out", "pending", "logged_in", "error"]
    error: CursorErrorCode | None = None


class CursorLogin(BaseModel):
    url: str


class CursorModels(BaseModel):
    models: list[str]


class CursorMessage(BaseModel):
    role: Literal["system", "developer", "user", "assistant"]
    content: str


class CursorRun(BaseModel):
    model: str = Field(pattern=rf"^{MODEL_ID.pattern}$")
    messages: list[CursorMessage] = Field(min_length=1)


class CursorDelta(BaseModel):
    type: Literal["delta"] = "delta"
    text: str


class CursorDone(BaseModel):
    type: Literal["done"] = "done"


class CursorFailure(BaseModel):
    type: Literal["error"] = "error"
    code: CursorErrorCode


def is_cursor_login_url(value: str) -> bool:
    try:
        url = urlsplit(value)
        return (
            url.scheme == "https"
            and (url.hostname in {"cursor.com", "www.cursor.com", "authenticator.cursor.sh"})
            and url.port in (None, 443)
            and url.username is None
            and url.password is None
            and not any(character.isspace() or character == "\\" for character in value)
        )
    except ValueError:
        return False
