from typing import Any, Generator
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from starlette.exceptions import HTTPException

from src.tests.mocks import MockAPIToken, MockUser

type GenMockPair = Generator[tuple[MagicMock, AsyncMock], Any, None]


@pytest.fixture
def mock_make_token() -> Generator[MagicMock, Any, None]:
    """Mock make_api_token function."""
    with patch("src.modules.auth.tokens.make_api_token") as mock:
        mock.return_value = MagicMock(value="test-token-value", hashed_value="test-hash")
        yield mock


@pytest.fixture
def mock_decode_token() -> Generator[MagicMock, Any, None]:
    """Mock decode_api_token function."""
    with patch("src.modules.auth.tokens.decode_api_token") as mock:
        mock.return_value = MagicMock(sub="test-user-id")
        yield mock


@pytest.fixture
def mock_hash_token() -> Generator[MagicMock, Any, None]:
    """Mock hash_token function."""
    with patch("src.modules.auth.tokens.hash_token") as mock:
        mock.return_value = "test-hash"
        yield mock


@pytest.fixture
def mock_api_token_inactive() -> Generator[MockAPIToken, Any, None]:
    """Mock TokenRepository with inactive token."""
    with patch("src.db.repositories.TokenRepository.get_by_token") as mock_get_by_token:
        mock_token = MockAPIToken(is_active=False, user=MockUser(id=1, is_active=True))
        mock_get_by_token.return_value = mock_token
        yield mock_token


@pytest.fixture
def mock_api_token_user_inactive() -> Generator[MockAPIToken, Any, None]:
    """Mock TokenRepository with inactive token."""
    with patch("src.db.repositories.TokenRepository.get_by_token") as mock_get_by_token:
        mock_token = MockAPIToken(is_active=True, user=MockUser(id=1, is_active=False))
        mock_get_by_token.return_value = mock_token
        yield mock_token


@pytest.fixture
def mock_api_token_unknown() -> Generator[AsyncMock, Any, None]:
    """Mock TokenRepository with inactive token."""
    with patch("src.db.repositories.TokenRepository.get_by_token") as mock_get_by_token:
        mock_get_by_token.return_value = None
        yield mock_get_by_token


@pytest.fixture
def mock_repository_db_error() -> Generator[AsyncMock, Any, None]:
    """Mock TokenRepository with inactive token."""
    with patch("src.db.repositories.TokenRepository.get_by_token") as mock_get_by_token:
        mock_get_by_token.side_effect = RuntimeError("Database error")
        yield mock_get_by_token


@pytest.fixture
def mock_token_repository_inactive_token() -> GenMockPair:
    """Mock TokenRepository with inactive token."""
    with patch("src.db.repositories.TokenRepository") as mock_repo_class:
        mock_repo = AsyncMock()
        mock_token = MagicMock()
        mock_token.is_active = False
        mock_repo.get_by_token.return_value = mock_token
        mock_repo_class.return_value = mock_repo
        yield mock_repo_class, mock_repo


@pytest.fixture
def mock_token_repository_inactive_user() -> GenMockPair:
    """Mock TokenRepository with inactive user."""
    with patch("src.db.repositories.TokenRepository") as mock_repo_class:
        mock_repo = AsyncMock()
        mock_token = MagicMock()
        mock_token.is_active = True
        mock_token.user.is_active = False
        mock_repo.get_by_token.return_value = mock_token
        mock_repo_class.return_value = mock_repo
        yield mock_repo_class, mock_repo


@pytest.fixture
def mock_token_repository_unknown_token() -> GenMockPair:
    """Mock TokenRepository with unknown token."""
    with patch("src.db.repositories.TokenRepository") as mock_repo_class:
        mock_repo = AsyncMock()
        mock_repo.get_by_token.return_value = None
        mock_repo_class.return_value = mock_repo
        yield mock_repo_class, mock_repo


@pytest.fixture
def mock_decode_token_no_identity() -> Generator[MagicMock, Any, None]:
    """Mock decode_api_token function with no identity."""
    with patch("src.modules.auth.tokens.decode_api_token") as mock:
        mock.return_value = MagicMock(sub="")
        yield mock


@pytest.fixture
def mock_decode_token_none_identity() -> Generator[MagicMock, Any, None]:
    """Mock decode_api_token function with None identity."""
    with patch("src.modules.auth.tokens.decode_api_token") as mock:
        mock.return_value = MagicMock(sub=None)
        yield mock


@pytest.fixture
def mock_decode_token_error() -> Generator[MagicMock, Any, None]:
    """Mock decode_api_token function that raises error."""
    with patch("src.modules.auth.tokens.decode_api_token") as mock:
        mock.side_effect = HTTPException(status_code=401, detail="Invalid token")
        yield mock
