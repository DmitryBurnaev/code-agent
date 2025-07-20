"""Tests for vendor admin view encryption functionality."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.modules.admin.views.vendors import VendorAdminView
from src.settings import AppSettings


class TestVendorAdminEncryption:
    """Tests for VendorAdminView encryption."""

    @patch("src.modules.admin.views.vendors.get_app_settings")
    def test_encrypt_api_key_encrypts_data(self, mock_get_settings: MagicMock) -> None:
        """Test that _encrypt_api_key encrypts the API key."""
        # Mock settings
        mock_settings = MagicMock(spec=AppSettings)
        mock_settings.vendor_encryption_key.get_secret_value.return_value = (
            "test-secret-key-32-chars-long"
        )
        mock_get_settings.return_value = mock_settings

        original_key = "sk-test123456789"
        encrypted = VendorAdminView._encrypt_api_key(original_key)

        # Check that the encrypted key is different from original
        assert encrypted != original_key
        assert len(encrypted) > len(original_key)

    def test_encrypt_api_key_empty_raises_error(self) -> None:
        """Test that _encrypt_api_key with empty key raises ValueError."""
        with pytest.raises(ValueError, match="API key cannot be empty"):
            VendorAdminView._encrypt_api_key("")

    @patch("src.modules.admin.views.vendors.get_app_settings")
    def test_encrypt_api_key_encryption_error(self, mock_get_settings: MagicMock) -> None:
        """Test that _encrypt_api_key handles encryption errors."""
        # Mock settings to cause encryption error
        mock_settings = MagicMock(spec=AppSettings)
        mock_settings.vendor_encryption_key.get_secret_value.side_effect = Exception(
            "Encryption error"
        )
        mock_get_settings.return_value = mock_settings

        with pytest.raises(ValueError, match="Failed to encrypt API key"):
            VendorAdminView._encrypt_api_key("sk-test123456789")

    @patch("src.modules.admin.views.vendors.VendorAdminView._encrypt_api_key")
    @patch("src.modules.admin.views.vendors.VendorAdminView._validate")
    async def test_insert_model_encrypts_api_key(
        self, mock_validate: AsyncMock, mock_encrypt: MagicMock
    ) -> None:
        """Test that insert_model encrypts API key before saving."""
        # Mock dependencies
        mock_validate.return_value = {"api_key": "sk-test123456789", "slug": "test"}
        mock_encrypt.return_value = "encrypted-key-here"

        # Mock super().insert_model
        with patch.object(VendorAdminView, "__bases__", (MagicMock,)):
            view = VendorAdminView()
            view.insert_model = AsyncMock()

            request = MagicMock()
            data = {"api_key": "sk-test123456789", "slug": "test"}

            await view.insert_model(request, data)

            # Check that encryption was called
            mock_encrypt.assert_called_once_with("sk-test123456789")

            # Check that data was updated with encrypted key
            assert data["api_key"] == "encrypted-key-here"

    @patch("src.modules.admin.views.vendors.VendorAdminView._encrypt_api_key")
    @patch("src.modules.admin.views.vendors.VendorAdminView._validate")
    async def test_update_model_encrypts_api_key(
        self, mock_validate: AsyncMock, mock_encrypt: MagicMock
    ) -> None:
        """Test that update_model encrypts API key before saving."""
        # Mock dependencies
        mock_validate.return_value = {"api_key": "sk-test123456789", "slug": "test"}
        mock_encrypt.return_value = "encrypted-key-here"

        # Mock super().update_model
        with patch.object(VendorAdminView, "__bases__", (MagicMock,)):
            view = VendorAdminView()
            view.update_model = AsyncMock()

            request = MagicMock()
            pk = "1"
            data = {"api_key": "sk-test123456789", "slug": "test"}

            await view.update_model(request, pk, data)

            # Check that encryption was called
            mock_encrypt.assert_called_once_with("sk-test123456789")

            # Check that data was updated with encrypted key
            assert data["api_key"] == "encrypted-key-here"

    @patch("src.modules.admin.views.vendors.VendorAdminView._validate")
    async def test_insert_model_no_api_key_skips_encryption(self, mock_validate: AsyncMock) -> None:
        """Test that insert_model skips encryption when no API key provided."""
        # Mock dependencies
        mock_validate.return_value = {"slug": "test"}

        # Mock super().insert_model
        with patch.object(VendorAdminView, "__bases__", (MagicMock,)):
            view = VendorAdminView()
            view.insert_model = AsyncMock()

            request = MagicMock()
            data = {"slug": "test"}

            await view.insert_model(request, data)

            # Check that data was not modified
            assert "api_key" not in data
