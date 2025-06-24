import hashlib
import uuid
from typing import NamedTuple


class TokenInfo(NamedTuple):
    value: str
    hashed_value: str


def make_token() -> TokenInfo:
    """Generates token, and it hashed value (requires for storage)"""
    token = uuid.uuid4().hex
    hashed = hashlib.sha512(token.encode()).hexdigest()
    return TokenInfo(value=token, hashed_value=hashed)
