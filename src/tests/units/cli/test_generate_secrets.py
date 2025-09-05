from typing import Generator, Any

import pytest
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

from _pytest.capture import CaptureFixture

from src.modules.cli.generate_secrets import main


@pytest.fixture
def mock_secrets() -> Generator[MagicMock, Any, None]:
    """Mock secrets.token_urlsafe to return predictable values for testing."""
    with patch("src.modules.cli.generate_secrets.secrets.token_urlsafe") as mock_token_urlsafe:
        # Return different predictable values for each call
        mock_token_urlsafe.side_effect = [
            "test-secret-key-32-chars-long-for-testing",
            "test-vendor-encryption-key-32-chars",
            "test-db-password-15",
            "test-admin-password-15",
        ]
        yield mock_token_urlsafe


@pytest.fixture
def mock_file_operations() -> Generator[MagicMock, Any, None]:
    """Mock file operations for testing .env file writing."""
    with patch("builtins.open", mock_open()) as mock_file:
        yield mock_file


def test_main_writes_secrets_to_env_file(
    mock_secrets: MagicMock,
    mock_file_operations: MagicMock,
    capsys: CaptureFixture[str],
) -> None:
    """Test that main function writes secrets to .env file."""
    main()

    mock_file_operations.assert_called_once_with(Path(".env"), "a", encoding="utf-8")

    file_handle = mock_file_operations()
    written_content = file_handle.write.call_args[0][0]

    expected_lines = [
        "",
        "# Generated secrets",
        "DB_PASSWORD=test-db-password-15",
        "ADMIN_PASSWORD=test-admin-password-15",
        "VENDOR_ENCRYPTION_KEY=test-vendor-encryption-key-32-chars",
        "APP_SECRET_KEY=test-secret-key-32-chars-long-for-testing",
        "",
    ]
    expected_content = "\n".join(expected_lines)
    assert written_content == expected_content

    captured = capsys.readouterr()
    assert "✅ Secrets written to .env" in captured.out


def test_main_changes_file_permissions_successfully(
    mock_secrets: MagicMock,
    mock_file_operations: MagicMock,
    capsys: CaptureFixture[str],
) -> None:
    """Test that main function successfully changes file permissions to 600."""
    with patch("os.chmod") as mock_chmod:
        main()

        # Verify chmod was called with correct parameters
        mock_chmod.assert_called_once_with(Path(".env"), 0o600)

        # Verify success message is displayed
        captured = capsys.readouterr()
        assert "✅ Permissions changed to 600 for .env" in captured.out


def test_main_handles_permission_change_error(
    mock_secrets: MagicMock,
    mock_file_operations: MagicMock,
    capsys: CaptureFixture[str],
) -> None:
    """Test that main function handles permission change errors gracefully."""
    with patch("os.chmod", side_effect=PermissionError("Permission denied")):
        main()

        # Verify error message is displayed
        captured = capsys.readouterr()
        assert "⚠️  Warning: Could not change permissions for .env:" in captured.out
        assert "Please change the permissions manually to 600" in captured.out

        # Verify file writing still succeeded
        assert "✅ Secrets written to .env" in captured.out


def test_main_handles_file_write_error(
    mock_secrets: MagicMock,
    mock_file_operations: MagicMock,
    capsys: CaptureFixture[str],
) -> None:
    """Test that main function handles file write errors gracefully."""
    with patch("builtins.open", side_effect=PermissionError("Permission denied")):
        main()

        # Verify error message is displayed
        captured = capsys.readouterr()
        assert "⚠️  Warning: Could not write to .env file:" in captured.out
        assert "✅ Permissions changed to 600 for .env" not in captured.out


def test_main_generates_and_not_displays_secrets(
    mock_secrets: MagicMock,
    mock_file_operations: MagicMock,
    capsys: CaptureFixture[str],
) -> None:
    """Test that main function generates and displays secrets correctly."""
    # Call the main function
    main()

    # Capture stdout
    captured = capsys.readouterr()
    output = captured.out

    # Verify the output contains all expected secrets
    assert "Generating secure secrets..." in output
    assert "APP_SECRET_KEY=test-secret-key-32-chars-long-for-testing" not in output
    assert "VENDOR_ENCRYPTION_KEY=test-vendor-encryption-key-32-chars" not in output
    assert "DB_PASSWORD=test-db-password-15" not in output
    assert "ADMIN_PASSWORD=test-admin-password-15" not in output

    # Verify secrets.token_urlsafe was called exactly 4 times with correct parameters
    assert mock_secrets.call_count == 4
    mock_secrets.assert_any_call(32)  # Called twice with 32
    mock_secrets.assert_any_call(15)  # Called twice with 15


def test_main_calls_secrets_token_urlsafe_with_correct_parameters(
    mock_secrets: MagicMock,
    mock_file_operations: MagicMock,
) -> None:
    """Test that secrets.token_urlsafe is called with correct parameters."""
    main()

    # Verify the calls were made in the correct order with correct parameters
    expected_calls = [
        ((32,),),  # APP_SECRET_KEY
        ((32,),),  # VENDOR_ENCRYPTION_KEY
        ((15,),),  # DB_PASSWORD
        ((15,),),  # ADMIN_PASSWORD
    ]

    assert mock_secrets.call_args_list == expected_calls


def test_mocks_prevent_real_file_writing(
    mock_secrets: MagicMock,
    mock_file_operations: MagicMock,
    tmp_path: Path,
) -> None:
    """Test that mocks prevent real file writing operations."""
    # Create a temporary .env file to test against
    test_env_file = tmp_path / ".env"
    test_env_file.write_text("EXISTING_CONTENT=test")

    # Store original content
    original_content = test_env_file.read_text()

    # Temporarily change working directory to temp path
    import os

    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        # Call main function - should use mocks, not real file operations
        main()

        # Verify file content hasn't changed
        assert test_env_file.read_text() == original_content

        # Verify mocks were called instead
        mock_file_operations.assert_called_once_with(Path(".env"), "a", encoding="utf-8")

    finally:
        # Restore original working directory
        os.chdir(original_cwd)
