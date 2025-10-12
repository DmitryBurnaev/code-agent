from typing import Generator, Any

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.exceptions import VendorEncryptionError
from src.main import CodeAgentAPP
from src.modules.admin.views.base import FormDataType
from src.modules.admin.views.vendors import VendorAdminView
from src.modules.encrypt.encryption import VendorKeyEncryption
from src.settings import AppSettings


@pytest.fixture
def vendor_admin_view(test_app: CodeAgentAPP) -> VendorAdminView:
    admin_view = VendorAdminView()
    admin_view.app = test_app
    return admin_view


@pytest.fixture
def mock_super_model_view_update() -> Generator[MagicMock, Any, None]:
    with patch("sqladmin.models.ModelView.update_model") as mock_super:
        yield mock_super


@pytest.fixture
def mock_super_model_view_insert() -> Generator[MagicMock, Any, None]:
    with patch("sqladmin.models.ModelView.insert_model") as mock_super:
        yield mock_super


@pytest.fixture
def original_api_key() -> str:
    return "sk-test123456789"


@pytest.fixture
def mock_encryption(
    app_settings_test: AppSettings,
    original_api_key: str,
) -> Generator[MagicMock, Any, None]:
    encryption = VendorKeyEncryption(app_settings_test.vendor_encryption_key)
    value = encryption.encrypt(original_api_key)

    with patch("src.modules.encrypt.encryption.VendorKeyEncryption.encrypt") as mock_encryption:
        mock_encryption.return_value = value
        yield mock_encryption


class TestVendorAdminEncryption:

    @staticmethod
    def _encrypt(settings: AppSettings, plaintext_key: str) -> str:
        encryption = VendorKeyEncryption(settings.vendor_encryption_key)
        return encryption.encrypt(plaintext_key)

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

    @patch("src.modules.admin.views.vendors.VendorAdminView._validate")
    async def test_insert_model_encrypts_api_key(
        self,
        mock_validate: AsyncMock,
        app_settings_test: AppSettings,
        vendor_admin_view: VendorAdminView,
        mock_request: MagicMock,
        mock_super_model_view_insert: MagicMock,
        mock_encryption: MagicMock,
        original_api_key: str,
    ) -> None:
        encrypted_key = mock_encryption.return_value
        update_data: FormDataType = {"new_api_key": original_api_key, "slug": "test"}
        mock_validate.return_value = update_data

        await vendor_admin_view.insert_model(mock_request, data=update_data)

        mock_super_model_view_insert.assert_awaited_once_with(
            mock_request, {"slug": "test", "api_key": encrypted_key}
        )

        encryption = VendorKeyEncryption(vendor_admin_view.app.settings.vendor_encryption_key)
        assert encryption.decrypt(encrypted_key) == original_api_key

    @patch("src.modules.admin.views.vendors.VendorAdminView._validate")
    async def test_update_model_encrypts_api_key(
        self,
        mock_validate: AsyncMock,
        app_settings_test: AppSettings,
        vendor_admin_view: VendorAdminView,
        mock_request: MagicMock,
        mock_super_model_view_update: MagicMock,
        mock_encryption: MagicMock,
        original_api_key: str,
    ) -> None:
        encrypted_api_key = mock_encryption.return_value
        update_data: FormDataType = {"new_api_key": original_api_key}
        mock_validate.return_value = update_data

        await vendor_admin_view.update_model(mock_request, "1", data=update_data)
        mock_super_model_view_update.assert_awaited_once_with(
            mock_request, "1", {"api_key": encrypted_api_key}
        )

        encryption = VendorKeyEncryption(vendor_admin_view.app.settings.vendor_encryption_key)
        assert encryption.decrypt(encrypted_api_key) == original_api_key

    @patch("src.modules.admin.views.vendors.VendorAdminView._validate")
    async def test_insert_model_no_new_api_key_skips_encryption(
        self,
        mock_validate: AsyncMock,
        vendor_admin_view: VendorAdminView,
        mock_request: MagicMock,
    ) -> None:
        mock_validate.return_value = {"new_api_key": None, "slug": "test"}

        # Mock the base insert_model method
        with patch.object(
            vendor_admin_view.__class__.__bases__[0], "insert_model", new_callable=AsyncMock
        ) as mock_base_insert:
            await vendor_admin_view.insert_model(mock_request, data={"slug": "test"})
            mock_base_insert.assert_awaited_once()
        assert "api_key" not in mock_base_insert.call_args_list[0].args[1]

    @patch("src.modules.admin.views.vendors.VendorAdminView._validate")
    async def test_update_model_no_new_api_key_skips_encryption(
        self,
        mock_validate: AsyncMock,
        vendor_admin_view: VendorAdminView,
        mock_request: MagicMock,
    ) -> None:
        mock_validate.return_value = {"new_api_key": None, "slug": "test"}

        # Mock the base update_model method
        with patch.object(
            vendor_admin_view.__class__.__bases__[0], "update_model", new_callable=AsyncMock
        ) as mock_base_update:
            await vendor_admin_view.update_model(mock_request, "1", data={"slug": "test"})
            mock_base_update.assert_awaited_once()
        assert "api_key" not in mock_base_update.call_args_list[0].args[2]
