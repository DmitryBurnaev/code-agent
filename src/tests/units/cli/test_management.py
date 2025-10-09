from typing import Any, Callable, Generator
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner, Result
from _pytest.capture import CaptureFixture

from src.db import User
from src.modules.cli.management import (
    update_user,
    change_admin_password,
    MIN_PASSWORD_LENGTH,
    DEFAULT_PASSWORD_LENGTH,
)


@pytest.fixture
def mock_user() -> Generator[MagicMock, Any, None]:
    mock_user = MagicMock(spec=User)
    mock_user.username = "test-user"
    mock_user.password = "old-hashed-password"
    mock_user.make_password.return_value = "new-hashed-password"
    with patch("src.modules.cli.management.User.make_password") as mock_make_password:
        mock_make_password.return_value = "new-hashed-password"
        yield mock_user


@pytest.fixture
def mock_uow() -> Generator[MagicMock, Any, None]:
    with patch("src.modules.cli.management.SASessionUOW") as mock_uow_class:
        mock_uow = MagicMock()
        mock_uow_class.return_value.__aenter__.return_value = mock_uow
        mock_uow_class.return_value.__aexit__.return_value = None
        yield mock_uow


@pytest.fixture
def mock_user_repo() -> Generator[MagicMock, Any, None]:
    with patch("src.modules.cli.management.UserRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        yield mock_repo


@pytest.fixture
def mock_get_user_by_username(mock_user: MagicMock) -> Generator[MagicMock, Any, None]:
    with patch("src.modules.cli.management.UserRepository.get_by_username") as _mock:
        _mock.return_value = mock_user
        yield _mock


@pytest.fixture(autouse=True)
def mock_db_operations() -> Generator[tuple[MagicMock, MagicMock], Any, None]:
    with (
        patch("src.modules.cli.management.initialize_database") as mock_init,
        patch("src.modules.cli.management.close_database") as mock_close,
    ):
        yield mock_init, mock_close


@pytest.fixture
def mock_secrets() -> Generator[MagicMock, Any, None]:
    with patch("src.modules.cli.management.secrets.token_urlsafe") as mock_token:
        mock_token.return_value = "test-generated-password-32-chars"
        yield mock_token


class CliRunnerTypeHinted(CliRunner):

    def invoke(self, cli: Callable[..., Any], *args: Any, **kwargs: Any) -> Result:
        result = super().invoke(cli, *args, **kwargs)  # type: ignore
        return result


@pytest.fixture
def cli_runner() -> CliRunnerTypeHinted:
    return CliRunnerTypeHinted()


class TestUpdateUser:
    """Test update_user function."""

    @pytest.mark.asyncio
    async def test_update_user_success(
        self,
        mock_uow: MagicMock,
        mock_get_user_by_username: MagicMock,
        mock_user: MagicMock,
        capsys: CaptureFixture[str],
    ) -> None:
        result = await update_user("test-user", "newpassword")

        assert result is True
        assert mock_user.password == User.make_password("newpassword")

        mock_get_user_by_username.assert_called_once_with("test-user")
        mock_uow.mark_for_commit.assert_called_once()

        captured = capsys.readouterr()
        assert "Found user test-user. Lets update him password" in captured.out

    @pytest.mark.asyncio
    async def test_update_user_not_found(
        self,
        mock_uow: MagicMock,
        mock_get_user_by_username: MagicMock,
        capsys: CaptureFixture[str],
    ) -> None:
        mock_get_user_by_username.return_value = None

        result = await update_user("nonexistent", "newpassword")

        assert result is False
        mock_get_user_by_username.assert_called_once_with("nonexistent")
        mock_uow.mark_for_commit.assert_not_called()

        captured = capsys.readouterr()
        assert "User nonexistent not found." in captured.out


class TestChangeAdminPassword:
    """Test change_admin_password click command."""

    def test_change_admin_password_with_random_password(
        self,
        mock_uow: MagicMock,
        mock_get_user_by_username: MagicMock,
        mock_user: MagicMock,
        mock_secrets: MagicMock,
        capsys: CaptureFixture[str],
        cli_runner: CliRunnerTypeHinted,
    ) -> None:
        result = cli_runner.invoke(change_admin_password, ["--random-password"])

        assert result.exit_code == 0
        assert "Changing admin password..." in result.output
        assert "Generating a random password..." in result.output
        assert "Password for user 'admin' updated." in result.output
        assert "New password: 'test-generated-password-32-chars'" in result.output

        mock_secrets.assert_called_once_with(DEFAULT_PASSWORD_LENGTH)

    def test_change_admin_password_with_custom_random_length(
        self,
        mock_uow: MagicMock,
        mock_get_user_by_username: MagicMock,
        mock_user: MagicMock,
        mock_secrets: MagicMock,
        cli_runner: CliRunnerTypeHinted,
    ) -> None:
        result = cli_runner.invoke(
            change_admin_password, ["--random-password", "--random-password-length", "20"]
        )

        assert result.exit_code == 0
        mock_secrets.assert_called_once_with(20)

    def test_change_admin_password_with_manual_input(
        self,
        mock_uow: MagicMock,
        mock_get_user_by_username: MagicMock,
        mock_user: MagicMock,
        cli_runner: CliRunnerTypeHinted,
    ) -> None:
        # Simulate user input for password
        result = cli_runner.invoke(
            change_admin_password, input="manual-password-123\nmanual-password-123\n"
        )

        assert result.exit_code == 0
        assert "Set a new password for admin" in result.output
        assert "Password for user 'admin' updated." in result.output

    def test_change_admin_password_short_password_error(
        self, cli_runner: CliRunnerTypeHinted
    ) -> None:
        # Simulate user input with short password
        result = cli_runner.invoke(change_admin_password, input="short\nshort\n")

        assert result.exit_code != 0
        assert f"Password must be at least {MIN_PASSWORD_LENGTH} characters long." in result.output

    def test_change_admin_password_user_not_found(
        self,
        mock_uow: MagicMock,
        mock_get_user_by_username: MagicMock,
        cli_runner: CliRunnerTypeHinted,
    ) -> None:
        mock_get_user_by_username.return_value = None

        result = cli_runner.invoke(change_admin_password, ["--random-password"])

        assert result.exit_code == 0
        assert "Password for user 'admin' wasn't updated." in result.output

    def test_change_admin_password_with_custom_username(
        self,
        mock_uow: MagicMock,
        mock_get_user_by_username: MagicMock,
        mock_user: MagicMock,
        cli_runner: CliRunnerTypeHinted,
    ) -> None:
        result = cli_runner.invoke(
            change_admin_password, ["--username", "custom-user", "--random-password"]
        )

        assert result.exit_code == 0
        assert "Password for user 'custom-user' updated." in result.output
        mock_get_user_by_username.assert_called_once_with("custom-user")

    def test_change_admin_password_help_option(self, cli_runner: CliRunnerTypeHinted) -> None:
        result = cli_runner.invoke(change_admin_password, ["--help"])

        assert result.exit_code == 0
        assert "Change the admin password." in result.output
        assert "--username" in result.output
        assert "--random-password" in result.output
        assert "--random-password-length" in result.output


class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_update_user_db_connection_error(
        self,
        mock_db_operations: tuple[MagicMock, MagicMock],
    ) -> None:
        mock_init, mock_close = mock_db_operations
        mock_init.side_effect = Exception("Connection failed")

        with pytest.raises(Exception, match="Connection failed"):
            await update_user("test-user", "password")

    def test_change_admin_password_db_error_during_update(
        self,
        mock_uow: MagicMock,
        mock_get_user_by_username: MagicMock,
        mock_user: MagicMock,
        cli_runner: CliRunnerTypeHinted,
    ) -> None:
        mock_uow.mark_for_commit.side_effect = Exception("DB commit failed")

        result = cli_runner.invoke(change_admin_password, ["--random-password"])

        # Should still show success message even if DB operation fails
        # because the error handling is in the async context
        assert result.exit_code == 0
