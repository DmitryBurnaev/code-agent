import datetime
import pytest
from pydantic import SecretStr
from unittest.mock import MagicMock
from starlette.exceptions import HTTPException

from src.utils import utcnow
from src.settings import AppSettings
from src.modules.auth.tokens import make_api_token, decode_api_token, hash_token, verify_api_token


class TestAuthIntegration:
    def test_full_token_lifecycle(self, app_settings_test: AppSettings) -> None:
        expires_at = utcnow() + datetime.timedelta(hours=1)
        generated = make_api_token(expires_at=expires_at, settings=app_settings_test)

        assert isinstance(generated.value, str)
        assert isinstance(generated.hashed_value, str)
        assert len(generated.value) > 0
        assert len(generated.hashed_value) > 0

        # Step 2: Decode token
        decoded = decode_api_token(generated.value, app_settings_test)

        assert decoded.sub is not None
        assert decoded.exp is not None
        assert decoded.exp == expires_at.replace(tzinfo=datetime.timezone.utc, microsecond=0)

        # Step 3: Verify token hash
        expected_hash = hash_token(decoded.sub)
        assert generated.hashed_value == expected_hash

    def test_token_format_consistency(self, app_settings_test: AppSettings) -> None:
        tokens = []

        for _ in range(5):
            generated = make_api_token(expires_at=None, settings=app_settings_test)
            tokens.append(generated.value)

        # All tokens should have the same format characteristics
        for token in tokens:
            # No dots (no header)
            assert "." not in token
            # Last 3 characters should be numeric (length prefix)
            length_prefix = token[-3:]
            assert length_prefix.isnumeric()
            # Token should be longer than just the length prefix
            assert len(token) > 3

    def test_token_uniqueness(self, app_settings_test: AppSettings) -> None:
        tokens = set()

        for _ in range(10):
            generated = make_api_token(expires_at=None, settings=app_settings_test)
            tokens.add(generated.value)

        # All tokens should be unique
        assert len(tokens) == 10

    def test_token_expiration_handling(self, app_settings_test: AppSettings) -> None:
        past_time = utcnow() - datetime.timedelta(hours=1)
        generated = make_api_token(expires_at=past_time, settings=app_settings_test)

        with pytest.raises(HTTPException, match="Token expired"):
            decode_api_token(generated.value, app_settings_test)

    @pytest.mark.asyncio
    async def test_auth_dependency_integration(
        self,
        mock_request: MagicMock,
        app_settings_test: AppSettings,
        mock_token_repository_active: MagicMock,
    ) -> None:
        generated = make_api_token(expires_at=None, settings=app_settings_test)
        # Verify token
        result = await verify_api_token(
            mock_request,
            app_settings_test,
            auth_token=f"Bearer {generated.value}",
        )

        assert result == generated.value

    @pytest.mark.parametrize(
        "expires_at",
        (
            pytest.param({"hours": 1}, id="expires_in_1_hour"),
            pytest.param({"hours": 2}, id="expires_in_2_hours"),
            pytest.param({"days": 1}, id="expires_in_1_day"),
        ),
    )
    def test_token_with_different_expiration_times(
        self,
        app_settings_test: AppSettings,
        expires_at: dict[str, int],
    ) -> None:
        exp = utcnow() + datetime.timedelta(**expires_at)
        token = make_api_token(expires_at=exp, settings=app_settings_test)
        decoded = decode_api_token(token.value, app_settings_test)
        assert decoded.exp == exp.replace(tzinfo=datetime.UTC, microsecond=0)

    def test_token_identifier_format(self, app_settings_test: AppSettings) -> None:
        generated = make_api_token(expires_at=None, settings=app_settings_test)
        decoded = decode_api_token(generated.value, app_settings_test)

        # Token identifier should be alphanumeric and have expected length
        token_id = decoded.sub
        assert token_id.isalnum()
        assert len(token_id) >= 9  # 3 digits + 6 hex chars

    def test_token_hash_consistency(self, app_settings_test: AppSettings) -> None:
        generated = make_api_token(expires_at=None, settings=app_settings_test)
        decoded = decode_api_token(generated.value, app_settings_test)

        # Hash the token identifier multiple times
        hash1 = hash_token(decoded.sub)
        hash2 = hash_token(decoded.sub)
        hash3 = hash_token(decoded.sub)

        # All hashes should be identical
        assert hash1 == hash2 == hash3 == generated.hashed_value

    def test_token_with_special_characters_in_settings(
        self, app_settings_test: AppSettings
    ) -> None:
        special_settings = AppSettings(
            admin_username="test-username",
            admin_password=SecretStr("test-password"),
            secret_key=SecretStr("test-secret-key-with-special-chars!@#$%^&*()"),
            vendor_encryption_key=SecretStr("test-vendor-encryption-key"),
            jwt_algorithm="HS256",
        )

        generated = make_api_token(expires_at=None, settings=special_settings)
        decoded = decode_api_token(generated.value, special_settings)

        assert decoded.sub is not None
        assert decoded.exp is not None

    @pytest.mark.parametrize("jwt_algorithm", ("HS256", "HS512"))
    def test_token_with_different_algorithms(
        self, app_settings_test: AppSettings, jwt_algorithm: str
    ) -> None:
        settings = AppSettings(
            admin_username="test-username",
            admin_password=SecretStr("test-password"),
            secret_key=SecretStr("test-secret-key"),
            vendor_encryption_key=SecretStr("test-vendor-encryption-key"),
            jwt_algorithm=jwt_algorithm,
        )
        token = make_api_token(expires_at=None, settings=settings)
        decoded = decode_api_token(token.value, settings)

        assert decoded.sub is not None

    def test_token_edge_cases(self, app_settings_test: AppSettings) -> None:
        short_exp = utcnow() + datetime.timedelta(seconds=1)
        token_short = make_api_token(expires_at=short_exp, settings=app_settings_test)

        decoded_short = decode_api_token(token_short.value, app_settings_test)
        assert decoded_short.exp == short_exp.replace(tzinfo=datetime.UTC, microsecond=0)

        long_exp = utcnow() + datetime.timedelta(days=365)
        token_long = make_api_token(expires_at=long_exp, settings=app_settings_test)

        decoded_long = decode_api_token(token_long.value, app_settings_test)
        assert decoded_long.exp == long_exp.replace(tzinfo=datetime.UTC, microsecond=0)

    @pytest.mark.asyncio
    async def test_auth_dependency_error_handling(
        self,
        mock_request: MagicMock,
        app_settings_test: AppSettings,
    ) -> None:

        with pytest.raises(HTTPException, match="Invalid token signature"):
            await verify_api_token(mock_request, app_settings_test, auth_token="malformed-token")

        past_time = utcnow() - datetime.timedelta(hours=1)
        expired_token = make_api_token(expires_at=past_time, settings=app_settings_test)

        with pytest.raises(HTTPException, match="Token expired"):
            await verify_api_token(
                mock_request, app_settings_test, auth_token=f"Bearer {expired_token.value}"
            )

    def test_token_serialization_consistency(self, app_settings_test: AppSettings) -> None:
        tokens = []

        for _ in range(5):
            generated = make_api_token(expires_at=None, settings=app_settings_test)
            tokens.append(generated.value)

        for token in tokens:
            decoded = decode_api_token(token, app_settings_test)
            assert decoded.sub is not None
            assert decoded.exp is not None

    def test_token_with_none_expiration(self, app_settings_test: AppSettings) -> None:
        token = make_api_token(expires_at=None, settings=app_settings_test)
        decoded = decode_api_token(token.value, app_settings_test)

        assert decoded.exp is not None
        assert decoded.exp == datetime.datetime.max.replace(
            tzinfo=datetime.timezone.utc, microsecond=0
        )
