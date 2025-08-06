import pytest
from unittest.mock import patch, MagicMock

from src.db.models import Vendor
from src.settings import AppSettings
from src.modules.encrypt.encryption import VendorKeyEncryption


class TestVendorEncryption:

    def test_decrypted_api_key_returns_original(self, app_settings_test: AppSettings) -> None:
        encryption = VendorKeyEncryption(app_settings_test.vendor_encryption_key)
        original_key = "sk-test123456789"
        vendor = Vendor(
            slug="deepseek",
            api_key=encryption.encrypt(original_key),
        )
        assert vendor.decrypted_api_key == original_key

    @patch("src.modules.encrypt.encryption.VendorKeyEncryption.decrypt")
    def test_decrypted_api_key_raises_on_decryption_error(
        self, mock_decrypt: MagicMock, app_settings_test: AppSettings
    ) -> None:
        mock_decrypt.side_effect = ValueError("Failed to decrypt API key")
        encryption = VendorKeyEncryption(app_settings_test.vendor_encryption_key)
        original_key = "sk-test123456789"
        vendor = Vendor(
            slug="deepseek",
            api_key=encryption.encrypt(original_key),
        )
        with pytest.raises(Exception) as exc:
            _ = vendor.decrypted_api_key

        assert "Failed to decrypt API key for vendor 'deepseek'" in str(exc.value)
