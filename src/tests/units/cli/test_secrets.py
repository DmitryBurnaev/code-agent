import pytest
from unittest.mock import patch
from src.cli.secrets import main


@pytest.fixture
def mock_secrets():
    """Mock secrets.token_urlsafe to return predictable values for testing."""
    with patch("src.cli.secrets.secrets.token_urlsafe") as mock_token_urlsafe:
        # Return different predictable values for each call
        mock_token_urlsafe.side_effect = [
            "test-secret-key-32-chars-long-for-testing",
            "test-vendor-encryption-key-32-chars",
            "test-db-password-15",
            "test-admin-password-15",
        ]
        yield mock_token_urlsafe


def test_main_generates_and_displays_secrets(mock_secrets, capsys):
    # Call the main function
    main()

    # Capture stdout
    captured = capsys.readouterr()
    output = captured.out

    # Verify the output contains all expected secrets
    assert "Generating secure secrets..." in output
    assert "Add this to your .env file:" in output
    assert "SECRET_KEY=test-secret-key-32-chars-long-for-testing" in output
    assert "VENDOR_ENCRYPTION_KEY=test-vendor-encryption-key-32-chars" in output
    assert "DB_PASSWORD=test-db-password-15" in output
    assert "ADMIN_PASSWORD=test-admin-password-15" in output

    # Verify warning message is present
    assert "⚠️  Important:" in output
    assert "Keep this secrets secure and consistent across deployments" in output
    assert "If you change this secrets, existing encrypted API keys will become unusable" in output
    assert "Use at least 32 characters for strong security" in output

    # Verify secrets.token_urlsafe was called exactly 4 times with correct parameters
    assert mock_secrets.call_count == 4
    mock_secrets.assert_any_call(32)  # Called twice with 32
    mock_secrets.assert_any_call(15)  # Called twice with 15


def test_main_calls_secrets_token_urlsafe_with_correct_parameters(mock_secrets):
    main()

    # Verify the calls were made in the correct order with correct parameters
    expected_calls = [
        ((32,),),  # SECRET_KEY
        ((32,),),  # VENDOR_ENCRYPTION_KEY
        ((15,),),  # DB_PASSWORD
        ((15,),),  # ADMIN_PASSWORD
    ]

    assert mock_secrets.call_args_list == expected_calls
