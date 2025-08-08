import datetime
import pytest
from unittest.mock import MagicMock, AsyncMock
from starlette.exceptions import HTTPException

from src.modules.auth.tokens import (
    JWTPayload,
    jwt_encode,
    jwt_decode,
    make_api_token,
    decode_api_token,
    hash_token,
    verify_api_token,
    GeneratedToken,
)
from src.settings import AppSettings
from src.tests.mocks import MockAPIToken
from src.utils import utcnow


class TestJWTPayload:

    def test_jwt_payload_creation(self) -> None:
        payload = JWTPayload(sub="test-user")
        assert payload.sub == "test-user"
        assert payload.exp is None

    def test_jwt_payload_with_expiration(self) -> None:
        exp_time = datetime.datetime.now() + datetime.timedelta(hours=1)
        payload = JWTPayload(sub="test-user", exp=exp_time)
        assert payload.sub == "test-user"
        assert payload.exp == exp_time

    def test_jwt_payload_as_dict(self) -> None:
        exp_time = datetime.datetime.now() + datetime.timedelta(hours=1)
        payload = JWTPayload(sub="test-user", exp=exp_time)
        payload_dict = payload.as_dict()

        assert payload_dict["sub"] == "test-user"
        assert payload_dict["exp"] == exp_time


class TestJWTEncodeDecode:

    def test_jwt_encode_basic(self, app_settings_test: AppSettings) -> None:
        payload = JWTPayload(sub="test-user")
        token = jwt_encode(payload, app_settings_test)

        assert isinstance(token, str)
        assert len(token.split(".")) == 3  # header.payload.signature

    def test_jwt_encode_with_expiration(self, app_settings_test: AppSettings) -> None:
        exp_time = datetime.datetime.now() + datetime.timedelta(hours=1)
        payload = JWTPayload(sub="test-user")
        token = jwt_encode(payload, app_settings_test, expires_at=exp_time)

        # Decode to verify expiration was set
        decoded = jwt_decode(token, app_settings_test)
        assert decoded.sub == "test-user"
        assert decoded.exp is not None

    def test_jwt_encode_no_expiration(self, app_settings_test: AppSettings) -> None:
        payload = JWTPayload(sub="test-user")
        token = jwt_encode(payload, app_settings_test)
        decoded = jwt_decode(token, app_settings_test)

        assert decoded.sub == "test-user"
        assert decoded.exp is not None

    def test_jwt_decode_invalid_token(self, app_settings_test: AppSettings) -> None:
        with pytest.raises(Exception):  # jwt.InvalidTokenError
            jwt_decode("invalid.token.here", app_settings_test)


class TestMakeAPIToken:

    def test_make_api_token_basic(self, app_settings_test: AppSettings) -> None:
        result = make_api_token(expires_at=None, settings=app_settings_test)

        assert isinstance(result, GeneratedToken)
        assert isinstance(result.value, str)
        assert isinstance(result.hashed_value, str)
        assert len(result.value) > 0
        assert len(result.hashed_value) > 0

    def test_make_api_token_with_expiration(self, app_settings_test: AppSettings) -> None:
        exp_time = utcnow(skip_tz=False) + datetime.timedelta(hours=1)
        result = make_api_token(expires_at=exp_time, settings=app_settings_test)

        # Token should be decodable
        decoded = decode_api_token(result.value, app_settings_test)
        assert decoded.exp is not None
        assert decoded.exp == exp_time.replace(microsecond=0)

    def test_make_api_token_custom_format(self, app_settings_test: AppSettings) -> None:
        result = make_api_token(expires_at=None, settings=app_settings_test)

        # Token should not contain dots (no header)
        assert "." not in result.value

        # Last 3 characters should be numeric (length prefix)
        length_prefix = result.value[-3:]
        assert length_prefix.isnumeric()

        # Token should be longer than just the length prefix
        assert len(result.value) > 3


class TestDecodeAPIToken:

    def test_decode_api_token_valid(self, app_settings_test: AppSettings) -> None:
        # Generate a token first
        generated = make_api_token(expires_at=None, settings=app_settings_test)

        # Decode it
        decoded = decode_api_token(generated.value, app_settings_test)

        assert isinstance(decoded, JWTPayload)
        assert decoded.sub is not None
        assert len(decoded.sub) > 0

    def test_decode_api_token_invalid_length_prefix(self, app_settings_test: AppSettings) -> None:
        with pytest.raises(HTTPException) as exc_info:
            decode_api_token("invalid-token", app_settings_test)

        assert exc_info.value.status_code == 401
        assert "Invalid token signature" in str(exc_info.value.detail)

    def test_decode_api_token_expired(self, app_settings_test: AppSettings) -> None:
        # Generate token with past expiration
        past_time = utcnow(skip_tz=False) - datetime.timedelta(hours=1)
        generated = make_api_token(expires_at=past_time, settings=app_settings_test)

        with pytest.raises(HTTPException) as exc_info:
            decode_api_token(generated.value, app_settings_test)

        assert exc_info.value.status_code == 401
        assert "Token expired" in str(exc_info.value.detail)

    def test_decode_api_token_malformed(self, app_settings_test: AppSettings) -> None:
        with pytest.raises(HTTPException) as exc_info:
            decode_api_token("malformed123", app_settings_test)

        assert exc_info.value.status_code == 401
        assert "Invalid token" in str(exc_info.value.detail)


class TestHashToken:

    def test_hash_token_basic(self) -> None:
        token = "test-token-123"
        hashed = hash_token(token)

        assert isinstance(hashed, str)
        assert len(hashed) == 128  # SHA-512 hex digest length
        assert hashed != token

    def test_hash_token_consistency(self) -> None:
        token = "test-token-123"
        hash1 = hash_token(token)
        hash2 = hash_token(token)

        assert hash1 == hash2

    def test_hash_token_different_tokens(self) -> None:
        token1 = "test-token-123"
        token2 = "test-token-456"

        hash1 = hash_token(token1)
        hash2 = hash_token(token2)

        assert hash1 != hash2

    def test_hash_token_empty_string(self) -> None:
        hashed = hash_token("")

        assert isinstance(hashed, str)
        assert len(hashed) == 128


@pytest.mark.asyncio
class TestVerifyAPIToken:

    async def test_verify_api_token_options_method(
        self, app_settings_test: AppSettings, mock_request: MagicMock
    ) -> None:
        mock_request.method = "OPTIONS"

        result = await verify_api_token(mock_request, app_settings_test, auth_token=None)

        assert result == ""

    async def test_verify_api_token_no_token(
        self, app_settings_test: AppSettings, mock_request: MagicMock
    ) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token=None)

        assert exc_info.value.status_code == 401
        assert "Not authenticated" in str(exc_info.value.detail)

    async def test_verify_api_token_with_bearer_prefix(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_db_api_token__active: MockAPIToken,
    ) -> None:
        generated_token = make_api_token(expires_at=None, settings=app_settings_test)
        result = await verify_api_token(
            mock_request,
            app_settings_test,
            auth_token=f"Bearer {generated_token.value}",
        )
        assert result == generated_token.value

    async def test_verify_api_token_inactive_token(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_db_api_token__inactive: MockAPIToken,
    ) -> None:
        generated = make_api_token(expires_at=None, settings=app_settings_test)
        auth_token = f"Bearer {generated.value}"

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token=auth_token)

        assert exc_info.value.status_code == 401
        assert "inactive token" in str(exc_info.value.detail)

    async def test_verify_api_token_inactive_user(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_db_api_token__user_inactive: MockAPIToken,
    ) -> None:
        generated = make_api_token(expires_at=None, settings=app_settings_test)
        auth_token = f"Bearer {generated.value}"

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token=auth_token)

        assert exc_info.value.status_code == 401
        assert "user is not active" in str(exc_info.value.detail)

    async def test_verify_api_token_unknown_token(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_db_api_token__unknown: AsyncMock,
    ) -> None:
        generated = make_api_token(expires_at=None, settings=app_settings_test)
        auth_token = f"Bearer {generated.value}"

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token=auth_token)

        assert exc_info.value.status_code == 401
        assert "unknown token" in str(exc_info.value.detail)
