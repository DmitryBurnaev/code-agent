"""Tests for Vendor model encryption functionality."""

import pytest
from unittest.mock import patch, MagicMock

from src.db.models import Vendor
from src.modules.encrypt.encryption import VendorKeyEncryption
from src.settings import AppSettings


class TestVendorEncryption:
    """Tests for Vendor model encryption."""

    @patch("src.db.models.get_app_settings")
    def test_decrypted_api_key_returns_original(self, mock_get_settings: MagicMock) -> None:
        """Test that decrypted_api_key returns the original key."""
        # Mock settings
        mock_settings = MagicMock(spec=AppSettings)
        mock_settings.vendor_encryption_key.get_secret_value.return_value = (
            "test-secret-key-32-chars-long"
        )
        mock_get_settings.return_value = mock_settings

        vendor = Vendor()
        original_key = "sk-test123456789"

        encryption = VendorKeyEncryption(mock_settings.vendor_encryption_key)
        vendor.api_key = encryption.encrypt(original_key)

        decrypted = vendor.decrypted_api_key

        assert decrypted == original_key

    @patch("src.db.models.get_app_settings")
    def test_decrypted_api_key_raises_on_decryption_error(
        self, mock_get_settings: MagicMock
    ) -> None:
        """Test that decrypted_api_key raises error on decryption failure."""
        # Mock settings to cause decryption error
        mock_settings = MagicMock(spec=AppSettings)
        mock_settings.vendor_encryption_key.get_secret_value.side_effect = ValueError(
            "Decryption error"
        )
        mock_get_settings.return_value = mock_settings

        vendor = Vendor()
        vendor.slug = "test-vendor"
        vendor.api_key = "invalid-encrypted-data"

        # Should raise ValueError when decryption fails
        with pytest.raises(ValueError, match="Failed to decrypt API key for vendor test-vendor"):
            _ = vendor.decrypted_api_key
