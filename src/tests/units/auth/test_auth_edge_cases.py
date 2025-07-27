import datetime
import pytest
from unittest.mock import MagicMock
from pydantic import SecretStr
from starlette.exceptions import HTTPException

from src.modules.auth.tokens import (
    make_api_token,
    decode_api_token,
    hash_token,
    verify_api_token,
)
from src.modules.auth.hashers import (
    PBKDF2PasswordHasher,
    get_salt,
    get_random_hash,
)
from src.settings import AppSettings
from src.tests.units.auth.conftest import MockToken
from src.utils import utcnow


class TestTokenEdgeCases:
    """Tests for token edge cases and special scenarios."""

    @pytest.mark.parametrize(
        "secret_key",
        [
            pytest.param("", id="empty"),
            pytest.param("a" * 1000, id="long"),
            pytest.param("!@#$%^&*()_+-=[]{}|;:,.<>?`~", id="special-characters"),
            pytest.param("секретный-ключ", id="unicode"),
        ],
    )
    def test_token_with_various_secret_key(self, secret_key: str) -> None:
        app_settings = AppSettings(
            api_token=SecretStr("test-token"),
            admin_username="test-username",
            admin_password=SecretStr("test-password"),
            secret_key=SecretStr(secret_key),
            vendor_encryption_key=SecretStr(""),
            jwt_algorithm="HS256",
        )

        generated = make_api_token(expires_at=None, settings=app_settings)
        assert isinstance(generated.value, str)
        assert isinstance(generated.hashed_value, str)

        decoded = decode_api_token(generated.value, app_settings)
        assert decoded.sub is not None

    def test_token_with_minimal_expiration(self, app_settings_test: AppSettings) -> None:
        minimal_exp = utcnow(skip_tz=False) + datetime.timedelta(seconds=1)
        generated = make_api_token(expires_at=minimal_exp, settings=app_settings_test)

        # Should be decodable immediately
        decoded = decode_api_token(generated.value, app_settings_test)
        assert decoded.exp == minimal_exp.replace(microsecond=0)

    def test_token_with_maximum_expiration(self, app_settings_test: AppSettings) -> None:
        max_exp = datetime.datetime.max
        generated = make_api_token(expires_at=max_exp, settings=app_settings_test)

        decoded = decode_api_token(generated.value, app_settings_test)
        assert decoded.exp == max_exp.replace(microsecond=0, tzinfo=datetime.timezone.utc)

    def test_token_with_negative_expiration(self, app_settings_test: AppSettings) -> None:
        past_time = utcnow(skip_tz=False) - datetime.timedelta(hours=1)
        generated = make_api_token(expires_at=past_time, settings=app_settings_test)

        # Should raise exception when decoding
        with pytest.raises(HTTPException) as exc_info:
            decode_api_token(generated.value, app_settings_test)

        assert exc_info.value.status_code == 401
        assert "Token expired" in str(exc_info.value.detail)

    def test_token_with_exactly_current_time_expiration(
        self, app_settings_test: AppSettings
    ) -> None:
        current_time = utcnow(skip_tz=False)
        generated = make_api_token(expires_at=current_time, settings=app_settings_test)

        # Should raise exception when decoding (expired)
        with pytest.raises(HTTPException) as exc_info:
            decode_api_token(generated.value, app_settings_test)

        assert exc_info.value.status_code == 401
        assert "Token expired" in str(exc_info.value.detail)

    @pytest.mark.parametrize(
        "token_string,expected_detail_contains",
        [
            pytest.param("123", None, id="very_short_token"),
            pytest.param(
                "payload-signature-abc", "Invalid token signature", id="non_numeric_length_prefix"
            ),
            pytest.param("payload-signature999", None, id="invalid_length_prefix"),
            pytest.param("invalid-payload123", None, id="malformed_payload"),
            pytest.param("payload-signature001", None, id="wrong_signature_length"),
        ],
    )
    def test_token_with_malformed_inputs(
        self,
        app_settings_test: AppSettings,
        token_string: str,
        expected_detail_contains: str | None,
    ) -> None:
        with pytest.raises(HTTPException) as exc_info:
            decode_api_token(token_string, app_settings_test)

        assert exc_info.value.status_code == 401

        if expected_detail_contains:
            assert expected_detail_contains in str(exc_info.value.detail)

    @pytest.mark.parametrize(
        "input_string",
        [
            pytest.param("", id="empty_string"),
            pytest.param("a" * 10000, id="very_long_string"),
            pytest.param("тест-строка-测试字符串", id="unicode_string"),
            pytest.param("!@#$%^&*()_+-=[]{}|;:,.<>?`~", id="special_characters"),
            pytest.param(
                "\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09",
                id="binary_like_string",
            ),
        ],
    )
    def test_hash_token_edge_cases(self, input_string: str) -> None:
        hashed = hash_token(input_string)

        assert isinstance(hashed, str)
        assert len(hashed) == 128  # SHA-512 hex digest length


class TestPasswordHasherEdgeCases:
    """Tests for password hasher edge cases."""

    @pytest.fixture
    def hasher(self) -> PBKDF2PasswordHasher:
        """Return PBKDF2PasswordHasher instance."""
        return PBKDF2PasswordHasher()

    @pytest.mark.parametrize(
        "password",
        [
            pytest.param("", id="empty_password"),
            pytest.param(None, id="null_password"),
        ],
    )
    def test_encode_empty_password(
        self, hasher: PBKDF2PasswordHasher, password: str | None
    ) -> None:
        with pytest.raises(ValueError) as exc_info:
            hasher.encode(password=password)  # type: ignore

        assert exc_info.value.args[0] == "Password is required"

    @pytest.mark.parametrize(
        "password",
        [
            pytest.param("a" * 10000, id="very_long_password"),
            pytest.param("тест-пароль-с-юникодом-测试密码", id="unicode_char"),
            pytest.param("!@#$%^&*()_+-=[]{}|;:,.<>?`~", id="special_char"),
            pytest.param("password\x00with\x00nulls", id="null_bytes"),
        ],
    )
    def test_encode_password_edge_cases(self, hasher: PBKDF2PasswordHasher, password: str) -> None:
        encoded = hasher.encode(password)

        assert isinstance(encoded, str)
        assert encoded.startswith("pbkdf2_sha256$")

    @pytest.mark.parametrize(
        "password,encoded_password,expected_valid,expected_message_contains",
        [
            pytest.param(
                "test-password",
                "pbkdf2_sha256$180000$salt",
                False,
                "incompatible format: not enough values to unpack",
                id="missing_hash_part",
            ),
            pytest.param(
                "test-password",
                "pbkdf2_sha256$180000$salt$hash$extra",
                False,
                "extra parts detected",
                id="extra_parts",
            ),
            pytest.param(
                "test-password",
                "pbkdf2_sha256$999999$salt$hash",
                False,
                "",
                id="wrong_iterations",
            ),
            pytest.param(
                "test-password",
                "pbkdf2_sha256$invalid$salt$hash",
                False,
                "",
                id="incompatible_format",
            ),
        ],
    )
    def test_verify_password_edge_cases(
        self,
        hasher: PBKDF2PasswordHasher,
        password: str,
        encoded_password: str,
        expected_valid: bool,
        expected_message_contains: str,
    ) -> None:

        is_valid, message = hasher.verify(password, encoded_password)

        assert is_valid is expected_valid
        if expected_message_contains:
            assert expected_message_contains in message.lower()
        else:
            assert message == ""

    @pytest.mark.parametrize(
        "length,expected_length,description",
        [
            pytest.param(0, 0, "zero length", id="zero_length"),
            pytest.param(100, 100, "very long length", id="very_long_length"),
        ],
    )
    def test_salt_generation_edge_cases(
        self, length: int, expected_length: int, description: str
    ) -> None:
        salt = get_salt(length=length)

        if expected_length == 0:
            assert salt == ""
        else:
            assert len(salt) == expected_length
            assert salt.isalnum()

    @pytest.mark.parametrize(
        "size,expected_size,expected_error",
        [
            pytest.param(0, 0, True, id="zero_size"),
            pytest.param(1000, 1000, True, id="very_large_size"),
            pytest.param(1, 1, False, id="correct_min_size"),
            pytest.param(64, 64, False, id="correct_max_size"),
        ],
    )
    def test_random_hash_edge_cases(
        self, size: int, expected_size: int, expected_error: bool
    ) -> None:
        if expected_error:
            with pytest.raises(ValueError) as exc:
                get_random_hash(size=size)

            assert "digest_size must be between 1 and 64 bytes" in exc.value.args[0]

        else:
            hash_result = get_random_hash(size=size)
            assert len(hash_result) == expected_size
            assert all(c in "0123456789abcdef" for c in hash_result)


class TestAuthDependencyEdgeCases:
    """Tests for authentication dependency edge cases."""

    @pytest.mark.parametrize(
        "auth_token,should_raise,expected_detail_contains",
        [
            pytest.param("   ", True, "Not authenticated", id="whitespace_only"),
            pytest.param("\tBearer\t", True, "Not authenticated", id="tab_characters"),
            pytest.param("Bearer\n", True, "Not authenticated", id="newline_characters"),
            pytest.param("\u2003Bearer\u2003", True, "Not authenticated", id="unicode_whitespace"),
        ],
    )
    @pytest.mark.asyncio
    async def test_verify_api_token_with_whitespace_edge_cases(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        auth_token: str,
        should_raise: bool,
        expected_detail_contains: str,
    ) -> None:
        if should_raise:
            with pytest.raises(HTTPException) as exc_info:
                await verify_api_token(mock_request, app_settings_test, auth_token=auth_token)

            assert exc_info.value.status_code == 401
            assert expected_detail_contains in str(exc_info.value.detail)

    @pytest.mark.parametrize(
        "auth_token,description",
        [
            pytest.param("bearer test-token-value", "lowercase bearer", id="lowercase_bearer"),
            pytest.param("BeArEr test-token-value", "mixed case bearer", id="mixed_case_bearer"),
        ],
    )
    @pytest.mark.asyncio
    async def test_verify_api_token_with_case_insensitive_bearer(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_decode_token: MagicMock,
        mock_hash_token: MagicMock,
        mock_token: MockToken,
        auth_token: str,
        description: str,
    ) -> None:
        mock_token.is_active = True
        mock_token.user.is_active = True

        result = await verify_api_token(mock_request, app_settings_test, auth_token=auth_token)

        assert result == auth_token
