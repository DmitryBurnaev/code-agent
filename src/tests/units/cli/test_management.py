from typing import Any, AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner
from _pytest.capture import CaptureFixture

# Import with patches to avoid DB initialization
with patch("src.modules.cli.management.initialize_database"), \
     patch("src.modules.cli.management.close_database"):
    from src.modules.cli.management import (
        db_connection,
        update_user,
        change_admin_password,
        DEFAULT_ADMIN_USERNAME,
        MIN_PASSWORD_LENGTH,
        DEFAULT_PASSWORD_LENGTH,
    )


@pytest.fixture
def mock_uow() -> Generator[MagicMock, Any, None]:
    """Mock SASessionUOW for testing."""
    with patch("src.modules.cli.management.SASessionUOW") as mock_uow_class:
        mock_uow = MagicMock()
        mock_uow_class.return_value.__aenter__.return_value = mock_uow
        mock_uow_class.return_value.__aexit__.return_value = None
        yield mock_uow


@pytest.fixture
def mock_user_repo() -> Generator[MagicMock, Any, None]:
    """Mock UserRepository for testing."""
    with patch("src.modules.cli.management.UserRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        yield mock_repo


@pytest.fixture
def mock_db_operations() -> Generator[tuple[MagicMock, MagicMock], Any, None]:
    """Mock database initialization and cleanup operations."""
    with patch("src.modules.cli.management.initialize_database") as mock_init, \
         patch("src.modules.cli.management.close_database") as mock_close:
        yield mock_init, mock_close


@pytest.fixture
def mock_secrets() -> Generator[MagicMock, Any, None]:
    """Mock secrets.token_urlsafe for predictable password generation."""
    with patch("src.modules.cli.management.secrets.token_urlsafe") as mock_token:
        mock_token.return_value = "test-generated-password-32-chars"
        yield mock_token


@pytest.fixture
def mock_user() -> Generator[MagicMock, Any, None]:
    """Mock User object for testing."""
    mock_user = MagicMock()
    mock_user.username = "testuser"
    mock_user.password = "old-hashed-password"
    mock_user.make_password = MagicMock(return_value="new-hashed-password")
    return mock_user


@pytest.mark.no_autouse_fixtures
class TestDbConnection:
    """Test db_connection context manager."""

    @pytest.mark.asyncio
    async def test_db_connection_success(
        self,
        mock_db_operations: tuple[MagicMock, MagicMock],
        mock_uow: MagicMock,
    ) -> None:
        """Test successful database connection."""
        mock_init, mock_close = mock_db_operations
        
        async with db_connection() as uow:
            assert uow == mock_uow
            mock_init.assert_called_once()
        
        mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_db_connection_handles_exception(
        self,
        mock_db_operations: tuple[MagicMock, MagicMock],
        capsys: CaptureFixture[str],
    ) -> None:
        """Test that db_connection handles exceptions gracefully."""
        mock_init, mock_close = mock_db_operations
        
        # Mock SASessionUOW to raise an exception
        with patch("src.modules.cli.management.SASessionUOW", side_effect=Exception("DB Error")):
            async with db_connection() as uow:
                # Should not reach here due to exception
                pass
        
        captured = capsys.readouterr()
        assert "Unable to make DB operation user: Exception('DB Error')" in captured.err
        mock_close.assert_called_once()


@pytest.mark.no_autouse_fixtures
class TestUpdateUser:
    """Test update_user function."""

    @pytest.mark.asyncio
    async def test_update_user_success(
        self,
        mock_db_operations: tuple[MagicMock, MagicMock],
        mock_uow: MagicMock,
        mock_user_repo: MagicMock,
        mock_user: MagicMock,
        capsys: CaptureFixture[str],
    ) -> None:
        """Test successful user update."""
        mock_user_repo.get_by_username.return_value = mock_user
        
        result = await update_user("testuser", "newpassword")
        
        assert result is True
        mock_user_repo.get_by_username.assert_called_once_with("testuser")
        mock_user.make_password.assert_called_once_with("newpassword")
        mock_uow.mark_for_commit.assert_called_once()
        
        captured = capsys.readouterr()
        assert "Found user testuser. Lets update him password :)" in captured.out

    @pytest.mark.asyncio
    async def test_update_user_not_found(
        self,
        mock_db_operations: tuple[MagicMock, MagicMock],
        mock_uow: MagicMock,
        mock_user_repo: MagicMock,
        capsys: CaptureFixture[str],
    ) -> None:
        """Test update_user when user is not found."""
        mock_user_repo.get_by_username.return_value = None
        
        result = await update_user("nonexistent", "newpassword")
        
        assert result is False
        mock_user_repo.get_by_username.assert_called_once_with("nonexistent")
        mock_uow.mark_for_commit.assert_not_called()
        
        captured = capsys.readouterr()
        assert "User nonexistent not found." in captured.out


@pytest.mark.no_autouse_fixtures
class TestChangeAdminPassword:
    """Test change_admin_password click command."""

    def test_change_admin_password_with_random_password(
        self,
        mock_db_operations: tuple[MagicMock, MagicMock],
        mock_uow: MagicMock,
        mock_user_repo: MagicMock,
        mock_user: MagicMock,
        mock_secrets: MagicMock,
        capsys: CaptureFixture[str],
    ) -> None:
        """Test change_admin_password with random password generation."""
        mock_user_repo.get_by_username.return_value = mock_user
        
        runner = CliRunner()
        result = runner.invoke(change_admin_password, ["--random-password"])
        
        assert result.exit_code == 0
        assert "Changing admin password..." in result.output
        assert "Generating a random password..." in result.output
        assert "Password for user 'admin' updated." in result.output
        assert "New password: 'test-generated-password-32-chars'" in result.output
        
        mock_secrets.assert_called_once_with(DEFAULT_PASSWORD_LENGTH)

    def test_change_admin_password_with_custom_random_length(
        self,
        mock_db_operations: tuple[MagicMock, MagicMock],
        mock_uow: MagicMock,
        mock_user_repo: MagicMock,
        mock_user: MagicMock,
        mock_secrets: MagicMock,
    ) -> None:
        """Test change_admin_password with custom random password length."""
        mock_user_repo.get_by_username.return_value = mock_user
        
        runner = CliRunner()
        result = runner.invoke(
            change_admin_password, 
            ["--random-password", "--random-password-length", "20"]
        )
        
        assert result.exit_code == 0
        mock_secrets.assert_called_once_with(20)

    def test_change_admin_password_with_manual_input(
        self,
        mock_db_operations: tuple[MagicMock, MagicMock],
        mock_uow: MagicMock,
        mock_user_repo: MagicMock,
        mock_user: MagicMock,
    ) -> None:
        """Test change_admin_password with manual password input."""
        mock_user_repo.get_by_username.return_value = mock_user
        
        runner = CliRunner()
        # Simulate user input for password
        result = runner.invoke(
            change_admin_password,
            input="manualpassword123\nmanualpassword123\n"
        )
        
        assert result.exit_code == 0
        assert "Set a new password for admin" in result.output
        assert "Password for user 'admin' updated." in result.output

    def test_change_admin_password_short_password_error(
        self,
        mock_db_operations: tuple[MagicMock, MagicMock],
    ) -> None:
        """Test change_admin_password with password too short."""
        runner = CliRunner()
        # Simulate user input with short password
        result = runner.invoke(
            change_admin_password,
            input="short\nshort\n"
        )
        
        assert result.exit_code != 0
        assert f"Password must be at least {MIN_PASSWORD_LENGTH} characters long." in result.output

    def test_change_admin_password_user_not_found(
        self,
        mock_db_operations: tuple[MagicMock, MagicMock],
        mock_uow: MagicMock,
        mock_user_repo: MagicMock,
    ) -> None:
        """Test change_admin_password when user is not found."""
        mock_user_repo.get_by_username.return_value = None
        
        runner = CliRunner()
        result = runner.invoke(change_admin_password, ["--random-password"])
        
        assert result.exit_code == 0
        assert "Password for user 'admin' wasn't updated." in result.output

    def test_change_admin_password_with_custom_username(
        self,
        mock_db_operations: tuple[MagicMock, MagicMock],
        mock_uow: MagicMock,
        mock_user_repo: MagicMock,
        mock_user: MagicMock,
    ) -> None:
        """Test change_admin_password with custom username."""
        mock_user_repo.get_by_username.return_value = mock_user
        
        runner = CliRunner()
        result = runner.invoke(
            change_admin_password, 
            ["--username", "customuser", "--random-password"]
        )
        
        assert result.exit_code == 0
        assert "Password for user 'customuser' updated." in result.output
        mock_user_repo.get_by_username.assert_called_once_with("customuser")

    def test_change_admin_password_help_option(self) -> None:
        """Test change_admin_password help option."""
        runner = CliRunner()
        result = runner.invoke(change_admin_password, ["--help"])
        
        assert result.exit_code == 0
        assert "Change the admin password." in result.output
        assert "--username" in result.output
        assert "--random-password" in result.output
        assert "--random-password-length" in result.output


@pytest.mark.no_autouse_fixtures
class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_update_user_db_connection_error(
        self,
        mock_db_operations: tuple[MagicMock, MagicMock],
        capsys: CaptureFixture[str],
    ) -> None:
        """Test update_user handles database connection errors."""
        mock_init, mock_close = mock_db_operations
        mock_init.side_effect = Exception("Connection failed")
        
        result = await update_user("testuser", "password")
        
        assert result is False
        captured = capsys.readouterr()
        assert "Unable to make DB operation user:" in captured.err

    def test_change_admin_password_db_error_during_update(
        self,
        mock_db_operations: tuple[MagicMock, MagicMock],
        mock_uow: MagicMock,
        mock_user_repo: MagicMock,
        mock_user: MagicMock,
    ) -> None:
        """Test change_admin_password handles database errors during update."""
        mock_user_repo.get_by_username.return_value = mock_user
        mock_uow.mark_for_commit.side_effect = Exception("DB commit failed")
        
        runner = CliRunner()
        result = runner.invoke(change_admin_password, ["--random-password"])
        
        # Should still show success message even if DB operation fails
        # because the error handling is in the async context
        assert result.exit_code == 0


@pytest.mark.no_autouse_fixtures
class TestConstants:
    """Test that constants are properly defined."""

    def test_default_constants(self) -> None:
        """Test that default constants have expected values."""
        assert DEFAULT_ADMIN_USERNAME == "admin"
        assert MIN_PASSWORD_LENGTH == 16
        assert DEFAULT_PASSWORD_LENGTH == 32

    def test_constants_from_env(self) -> None:
        """Test that constants can be overridden by environment variables."""
        with patch.dict("os.environ", {
            "ADMIN_USERNAME": "customadmin",
            "MIN_PASSWORD_LENGTH": "20",
            "DEFAULT_PASSWORD_LENGTH": "40"
        }):
            # Re-import to get updated values
            import importlib
            import src.modules.cli.management
            importlib.reload(src.modules.cli.management)
            
            assert src.modules.cli.management.DEFAULT_ADMIN_USERNAME == "customadmin"
            assert src.modules.cli.management.MIN_PASSWORD_LENGTH == 20
            assert src.modules.cli.management.DEFAULT_PASSWORD_LENGTH == 40
