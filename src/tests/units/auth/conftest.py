from typing import Any, Generator
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from starlette.exceptions import HTTPException

from src.tests.mocks import MockAPIToken, MockUser


@pytest.fixture
def mock_make_token() -> Generator[MagicMock, Any, None]:
    with patch("src.modules.auth.tokens.make_api_token") as mock:
        mock.return_value = MagicMock(value="test-token-value", hashed_value="test-hash")
        yield mock


@pytest.fixture
def mock_decode_token() -> Generator[MagicMock, Any, None]:
    with patch("src.modules.auth.tokens.decode_api_token") as mock:
        mock.return_value = MagicMock(sub="test-user-id")
        yield mock


@pytest.fixture
def mock_hash_token() -> Generator[MagicMock, Any, None]:
    with patch("src.modules.auth.tokens.hash_token") as mock:
        mock.return_value = "test-hash"
        yield mock


@pytest.fixture
def mock_db_api_token__inactive() -> Generator[MockAPIToken, Any, None]:
    with patch("src.db.repositories.TokenRepository.get_by_token") as mock_get_by_token:
        mock_token = MockAPIToken(is_active=False, user=MockUser(id=1, is_active=True))
        mock_get_by_token.return_value = mock_token
        yield mock_token


@pytest.fixture
def mock_db_api_token__user_inactive() -> Generator[MockAPIToken, Any, None]:
    with patch("src.db.repositories.TokenRepository.get_by_token") as mock_get_by_token:
        mock_token = MockAPIToken(is_active=True, user=MockUser(id=1, is_active=False))
        mock_get_by_token.return_value = mock_token
        yield mock_token


@pytest.fixture
def mock_db_api_token__unknown() -> Generator[AsyncMock, Any, None]:
    with patch("src.db.repositories.TokenRepository.get_by_token") as mock_get_by_token:
        mock_get_by_token.return_value = None
        yield mock_get_by_token


@pytest.fixture
def mock_db_api_token__repository_error() -> Generator[AsyncMock, Any, None]:
    with patch("src.db.repositories.TokenRepository.get_by_token") as mock_get_by_token:
        mock_get_by_token.side_effect = RuntimeError("Database error")
        yield mock_get_by_token


@pytest.fixture
def mock_decode_token__no_identity() -> Generator[MagicMock, Any, None]:
    with patch("src.modules.auth.tokens.decode_api_token") as mock:
        mock.return_value = MagicMock(sub="")
        yield mock


@pytest.fixture
def mock_decode_token__none_identity() -> Generator[MagicMock, Any, None]:
    with patch("src.modules.auth.tokens.decode_api_token") as mock:
        mock.return_value = MagicMock(sub=None)
        yield mock


@pytest.fixture
def mock_decode_token__error() -> Generator[MagicMock, Any, None]:
    with patch("src.modules.auth.tokens.decode_api_token") as mock:
        mock.side_effect = HTTPException(status_code=401, detail="Invalid token")
        yield mock
