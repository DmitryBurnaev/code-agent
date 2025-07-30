from typing import Any, Generator
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from starlette.exceptions import HTTPException

from src.tests.conftest import MockAPIToken, MockUser


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
def mock_session_uow() -> GenMockPair:
    """Mock SASessionUOW context manager."""
    with patch("src.db.services.SASessionUOW") as mock_uow:
        mock_session = AsyncMock()
        mock_uow.return_value.__aenter__.return_value.session = mock_session
        yield mock_uow, mock_session


@pytest.fixture
def mock_token_repository_active(mock_session_uow: GenMockPair) -> Generator[MagicMock, Any, None]:
    """Mock TokenRepository with active token and user."""
    with patch("src.db.repositories.TokenRepository.get_by_token") as mock_get_by_token:
        mock_token = MagicMock()
        mock_token.is_active = True
        mock_token.user.is_active = True
        mock_get_by_token.return_value = mock_token
        yield mock_get_by_token


#
# @dataclasses.dataclass
# class MockUser:
#     is_active: bool = False
#
#
# @dataclasses.dataclass
# class MockToken:
#     is_active: bool
#     user: MockUser


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


@pytest.fixture
def mock_session_uow_error() -> Generator[MagicMock, Any, None]:
    """Mock SASessionUOW context manager that raises error."""
    with patch("src.db.services.SASessionUOW") as mock_uow:
        mock_uow.side_effect = Exception("Database error")
        yield mock_uow


#
# @pytest.fixture
# def mock_make_token() -> Generator[MagicMock, None, None]:
#     """Mock make_api_token function."""
#     with patch("src.modules.auth.dependencies.make_api_token") as mock:
#         mock.return_value = MagicMock(value="test-token-value", hashed_value="test-hash")
#         yield mock
#
#
# @pytest.fixture
# def mock_decode_token() -> Generator[MagicMock, None, None]:
#     """Mock decode_api_token function."""
#     with patch("src.modules.auth.dependencies.decode_api_token") as mock:
#         mock.return_value = MagicMock(sub="test-user-id")
#         yield mock
#
#
# @pytest.fixture
# def mock_hash_token() -> Generator[MagicMock, None, None]:
#     """Mock hash_token function."""
#     with patch("src.modules.auth.dependencies.hash_token") as mock:
#         mock.return_value = "test-hash"
#         yield mock

#
# @pytest.fixture
# def mock_decode_token_no_identity() -> Generator[MagicMock, None, None]:
#     """Mock decode_api_token function with no identity."""
#     with patch("src.modules.auth.dependencies.decode_api_token") as mock:
#         mock.return_value = MagicMock(sub="")
#         yield mock
#
#
# @pytest.fixture
# def mock_decode_token_none_identity() -> Generator[MagicMock, None, None]:
#     """Mock decode_api_token function with None identity."""
#     with patch("src.modules.auth.dependencies.decode_api_token") as mock:
#         mock.return_value = MagicMock(sub=None)
#         yield mock
#
#
# @pytest.fixture
# def mock_decode_token_error() -> Generator[MagicMock, None, None]:
#     """Mock decode_api_token function that raises error."""
#     with patch("src.modules.auth.dependencies.decode_api_token") as mock:
#         mock.side_effect = Exception("Invalid token")
#         yield mock
#
#
# @pytest.fixture
# def mock_session_uow_error() -> Generator[MagicMock, None, None]:
#     """Mock SASessionUOW context manager that raises error."""
#     with patch("src.modules.auth.dependencies.SASessionUOW") as mock_uow:
#         mock_uow.side_effect = Exception("Database error")
#         yield mock_uow

# ==========
#  FROM test_auth_tokens
# ==========
# @pytest.fixture
# def mock_user() -> User:
#     """Return a mock user object."""
#     user = MagicMock(spec=User)
#     user.is_active = True
#     return user
#
#
# @pytest.fixture
# def mock_token(mock_user: User) -> Token:
#     """Return mock token object."""
#     token = MagicMock(spec=Token)
#     token.is_active = True
#     token.user = mock_user
#     return token
#
#
# @pytest.fixture
# def mock_session_uow() -> GenMockPair:
#     """Mock SASessionUOW context manager."""
#     with patch("src.modules.auth.tokens.SASessionUOW") as mock_uow:
#         mock_session = AsyncMock()
#         mock_uow.return_value.__aenter__.return_value.session = mock_session
#         yield mock_uow, mock_session
#
#
# @pytest.fixture
# def mock_token_repository(mock_token: Token) -> GenMockPair:
#     """Mock TokenRepository with active token."""
#     with patch("src.modules.auth.tokens.TokenRepository") as mock_repo_class:
#         mock_repo = AsyncMock()
#         mock_repo.get_by_token.return_value = mock_token
#         mock_repo_class.return_value = mock_repo
#         yield mock_repo_class, mock_repo
#
#
# @pytest.fixture
# def mock_token_repository_inactive_token(mock_user: User) -> GenMockPair:
#     """Mock TokenRepository with inactive token."""
#     with patch("src.modules.auth.tokens.TokenRepository") as mock_repo_class:
#         mock_repo = AsyncMock()
#         mock_token = MagicMock()
#         mock_token.is_active = False
#         mock_repo.get_by_token.return_value = mock_token
#         mock_repo_class.return_value = mock_repo
#         yield mock_repo_class, mock_repo
#
#
# @pytest.fixture
# def mock_token_repository_inactive_user(mock_user: User) -> GenMockPair:
#     """Mock TokenRepository with inactive user."""
#     with patch("src.modules.auth.tokens.TokenRepository") as mock_repo_class:
#         mock_repo = AsyncMock()
#         mock_token = MagicMock()
#         mock_token.is_active = True
#         mock_token.user.is_active = False
#         mock_repo.get_by_token.return_value = mock_token
#         mock_repo_class.return_value = mock_repo
#         yield mock_repo_class, mock_repo
#
#
# @pytest.fixture
# def mock_token_repository_unknown_token() -> GenMockPair:
#     """Mock TokenRepository with unknown token."""
#     with patch("src.modules.auth.tokens.TokenRepository") as mock_repo_class:
#         mock_repo = AsyncMock()
#         mock_repo.get_by_token.return_value = None
#         mock_repo_class.return_value = mock_repo
#         yield mock_repo_class, mock_repo
