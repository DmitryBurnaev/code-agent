import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.exceptions import VendorEncryptionError
from src.main import CodeAgentAPP
from src.modules.admin.views.vendors import VendorAdminView
from src.modules.encrypt.encryption import VendorKeyEncryption


@pytest.fixture
def vendor_admin_view(test_app: CodeAgentAPP) -> VendorAdminView:
    admin_view = VendorAdminView()
    admin_view.app = test_app
    return admin_view


class TestVendorAdminEncryption:
    def test_encrypt_api_key_encrypts_data(
        self, test_app: CodeAgentAPP, vendor_admin_view: VendorAdminView
    ) -> None:
        encryption_key = test_app.settings.vendor_encryption_key
        original_key = "sk-test123456789"

        encrypted = vendor_admin_view._encrypt_api_key(original_key)
        assert encrypted != original_key

        encryption = VendorKeyEncryption(encryption_key)
        assert original_key == encryption.decrypt(encrypted)

    def test_encrypt_api_key_empty_raises_error(self, vendor_admin_view: VendorAdminView) -> None:
        with pytest.raises(ValueError, match="API key cannot be empty"):
            vendor_admin_view._encrypt_api_key("")

    @patch("src.modules.encrypt.encryption.VendorKeyEncryption.encrypt")
    def test_encrypt_api_key_encryption_error(
        self, mocked_encrypt: MagicMock, vendor_admin_view: VendorAdminView
    ) -> None:
        mocked_encrypt.side_effect = RuntimeError("Oops! Encryption error.")
        with pytest.raises(VendorEncryptionError, match="Failed to encrypt API key"):
            vendor_admin_view._encrypt_api_key("sk-test123456789")

    @patch("sqladmin.models.ModelView.insert_model")
    @patch("src.modules.admin.views.vendors.VendorAdminView._validate")
    async def test_insert_model_encrypts_api_key(
        self,
        mock_validate: AsyncMock,
        mock_base_insert: MagicMock,
        vendor_admin_view: VendorAdminView,
        mock_request: MagicMock,
    ) -> None:
        original_key = "sk-test123456789"
        mock_validate.return_value = {"new_api_key": original_key, "slug": "test"}

        await vendor_admin_view.insert_model(
            mock_request, data={"new_api_key": original_key, "slug": "test"}
        )
        mock_base_insert.assert_awaited_once()
        encrypted_api_key = mock_base_insert.call_args_list[0].args[1]["api_key"]
        assert encrypted_api_key != original_key

        encryption = VendorKeyEncryption(vendor_admin_view.app.settings.vendor_encryption_key)
        assert original_key == encryption.decrypt(encrypted_api_key)

    @patch("sqladmin.models.ModelView.update_model")
    @patch("src.modules.admin.views.vendors.VendorAdminView._validate")
    async def test_update_model_encrypts_api_key(
        self,
        mock_validate: AsyncMock,
        mock_base_update: MagicMock,
        vendor_admin_view: VendorAdminView,
        mock_request: MagicMock,
    ) -> None:
        original_key = "sk-test123456789"
        mock_validate.return_value = {"new_api_key": original_key, "slug": "test"}

        await vendor_admin_view.update_model(
            mock_request, "1", data={"new_api_key": original_key, "slug": "test"}
        )
        mock_base_update.assert_awaited_once()
        encrypted_api_key = mock_base_update.call_args_list[0].args[2]["api_key"]
        assert encrypted_api_key != original_key

        encryption = VendorKeyEncryption(vendor_admin_view.app.settings.vendor_encryption_key)
        assert original_key == encryption.decrypt(encrypted_api_key)

    @patch("sqladmin.models.ModelView.insert_model")
    @patch("src.modules.admin.views.vendors.VendorAdminView._validate")
    async def test_insert_model_no_new_api_key_skips_encryption(
        self,
        mock_validate: AsyncMock,
        mock_base_insert: MagicMock,
        vendor_admin_view: VendorAdminView,
        mock_request: MagicMock,
    ) -> None:
        mock_validate.return_value = {"new_api_key": None, "slug": "test"}

        await vendor_admin_view.insert_model(mock_request, data={"slug": "test"})
        mock_base_insert.assert_awaited_once()
        assert "api_key" not in mock_base_insert.call_args_list[0].args[1]

    @patch("sqladmin.models.ModelView.update_model")
    @patch("src.modules.admin.views.vendors.VendorAdminView._validate")
    async def test_update_model_no_new_api_key_skips_encryption(
        self,
        mock_validate: AsyncMock,
        mock_base_update: MagicMock,
        vendor_admin_view: VendorAdminView,
        mock_request: MagicMock,
    ) -> None:
        mock_validate.return_value = {"new_api_key": None, "slug": "test"}

        await vendor_admin_view.update_model(mock_request, "1", data={"slug": "test"})
        mock_base_update.assert_awaited_once()
        assert "api_key" not in mock_base_update.call_args_list[0].args[2]
