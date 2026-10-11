"""Balance provider integrations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from src.exceptions import BalanceProviderError, BalanceProviderNotConfiguredError
from src.models import Balance
from src.services.http import VendorHTTPClient
from src.settings import AppSettings

logger = logging.getLogger(__name__)
SELECTEL_IDENTITY_URL = "https://cloud.api.selcloud.ru/identity/v3/auth/tokens"
IAM_TOKEN_CACHE_TTL = timedelta(hours=23)
MONEY_QUANTUM = Decimal("0.01")
MINOR_CURRENCY_UNIT = Decimal("100")


@dataclass(frozen=True)
class CachedIAMToken:
    """An account-scoped Selectel IAM token with its local expiry time."""

    value: str
    expires_at: datetime


_iam_token_cache: dict[tuple[str, str], CachedIAMToken] = {}


@dataclass(frozen=True)
class CachedBalance:
    """A normalized balance and its process-local expiry time."""

    value: Balance
    expires_at: datetime


_balance_cache: dict[tuple[str, str], CachedBalance] = {}


class BalanceProvider(ABC):
    """Base class for providers that normalize an upstream balance response."""

    def __init__(self, settings: AppSettings, http_client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http_client = http_client

    @property
    @abstractmethod
    def url(self) -> str:
        """Return the configured upstream URL."""

    @abstractmethod
    async def get_headers(self) -> dict[str, str]:
        """Return the provider-specific request headers."""

    async def get_balance(self) -> Balance:
        """Fetch and normalize the provider response."""
        try:
            response = await self._get_response()
        except httpx.HTTPError as exc:
            logger.warning("Balance provider request failed: %s", exc.__class__.__name__)
            raise BalanceProviderError("Balance provider is unavailable") from exc

        if response.status_code != httpx.codes.OK:
            logger.warning("Balance provider returned status %s", response.status_code)
            raise BalanceProviderError("Balance provider is unavailable")

        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning("Balance provider returned invalid JSON")
            raise BalanceProviderError("Balance provider returned an invalid response") from exc

        try:
            return self.postprocess(payload)
        except (TypeError, ValidationError, ValueError) as exc:
            logger.warning("Balance provider returned an invalid payload")
            raise BalanceProviderError("Balance provider returned an invalid response") from exc

    async def _get_response(self) -> httpx.Response:
        headers = await self.get_headers()
        if self._http_client is not None:
            return await self._http_client.get(self.url, headers=headers)

        async with VendorHTTPClient(self._settings) as http_client:
            return await http_client.get(self.url, headers=headers)

    async def post_json(self, url: str, payload: dict[str, object]) -> httpx.Response:
        """Post a JSON payload using the configured client or a short-lived client."""
        if self._http_client is not None:
            return await self._http_client.post(url, json=payload)

        async with VendorHTTPClient(self._settings) as http_client:
            return await http_client.post(url, json=payload)

    @abstractmethod
    def postprocess(self, payload: Any) -> Balance:
        """Convert an upstream JSON payload into the public balance contract."""


class SelectelBalanceSettings(BaseModel):
    """Relevant Selectel billing settings from the upstream response."""

    currency: str | None = None


class SelectelBilling(BaseModel):
    """A Selectel billing bucket contributing to the account balance."""

    final_sum: Decimal


class SelectelBalanceData(BaseModel):
    """The Selectel billing data needed by the normalized balance response."""

    settings: SelectelBalanceSettings
    billings: list[SelectelBilling] = Field(default_factory=list)


class SelectelBalancePayload(BaseModel):
    """The native Selectel Billing API response shape used by this integration."""

    status: str
    data: SelectelBalanceData


class SelectelBalanceProvider(BalanceProvider):
    """Fetches and normalizes balances from the Selectel Billing API."""

    async def get_balance(self) -> Balance:
        """Fetch the Selectel balance and record safe progress information."""
        cache_key = self._balance_cache_key()
        now = datetime.now(timezone.utc)
        cached_balance = _balance_cache.get(cache_key)
        if (
            self._settings.selectel_balance_cache_ttl_seconds > 0
            and cached_balance is not None
            and cached_balance.expires_at > now
        ):
            logger.debug("Selectel balance: using cached billing data")
            return cached_balance.value

        logger.debug("Selectel balance: requesting billing data")
        balance = await super().get_balance()
        if self._settings.selectel_balance_cache_ttl_seconds > 0:
            _balance_cache[cache_key] = CachedBalance(
                value=balance,
                expires_at=datetime.now(timezone.utc)
                + timedelta(seconds=self._settings.selectel_balance_cache_ttl_seconds),
            )
            logger.debug("Selectel balance: billing data cached")
        logger.info("Selectel balance: billing data received")
        return balance

    def _balance_cache_key(self) -> tuple[str, str]:
        """Return a safe cache key for this configured Selectel account."""
        token = self._settings.selectel_balance_token
        if token is not None and (token_value := token.get_secret_value()):
            auth_identity = sha256(token_value.encode()).hexdigest()
        else:
            auth_identity = (
                f"{self._settings.selectel_balance_username}:"
                f"{self._settings.selectel_balance_account_id}"
            )
        return self.url, auth_identity

    @property
    def url(self) -> str:
        url = self._settings.selectel_balance_url
        if not url:
            raise BalanceProviderNotConfiguredError(
                "Selectel balance integration is not configured"
            )
        return url

    async def get_headers(self) -> dict[str, str]:
        token = self._settings.selectel_balance_token
        if token is not None and (token_value := token.get_secret_value()):
            logger.info("Selectel balance: using configured static-token authentication")
            return {"X-Token": token_value}

        return {"X-Auth-Token": await self._get_iam_token()}

    async def _get_iam_token(self) -> str:
        username = self._settings.selectel_balance_username
        account_id = self._settings.selectel_balance_account_id
        password = self._settings.selectel_balance_password
        if not username or not account_id or password is None or not password.get_secret_value():
            raise BalanceProviderNotConfiguredError(
                "Selectel balance integration is not configured"
            )

        cache_key = (username, account_id)
        now = datetime.now(timezone.utc)
        cached_token = _iam_token_cache.get(cache_key)
        if cached_token is not None and cached_token.expires_at > now:
            logger.debug("Selectel balance: using cached IAM token")
            return cached_token.value

        payload: dict[str, object] = {
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": username,
                            "domain": {"name": account_id},
                            "password": password.get_secret_value(),
                        }
                    },
                },
                "scope": {"domain": {"name": account_id}},
            }
        }
        try:
            logger.info("Selectel balance: requesting IAM token for service account")
            response = await self.post_json(SELECTEL_IDENTITY_URL, payload)
        except httpx.HTTPError as exc:
            logger.warning("Selectel IAM request failed: %s", exc.__class__.__name__)
            raise BalanceProviderError("Selectel authentication is unavailable") from exc

        if response.status_code != httpx.codes.CREATED:
            logger.warning("Selectel IAM endpoint returned status %s", response.status_code)
            raise BalanceProviderError("Selectel authentication failed")

        iam_token = response.headers.get("X-Subject-Token")
        if not isinstance(iam_token, str) or not iam_token:
            logger.warning("Selectel IAM endpoint did not return a subject token")
            raise BalanceProviderError("Selectel authentication returned an invalid response")

        _iam_token_cache[cache_key] = CachedIAMToken(
            value=iam_token,
            expires_at=now + IAM_TOKEN_CACHE_TTL,
        )
        logger.debug("Selectel balance: IAM token received and cached")
        return iam_token

    def postprocess(self, payload: Any) -> Balance:
        response = SelectelBalancePayload.model_validate(payload)
        return Balance(
            balance=(
                sum((billing.final_sum for billing in response.data.billings), Decimal())
                / MINOR_CURRENCY_UNIT
            ).quantize(MONEY_QUANTUM),
            currency=(
                response.data.settings.currency.upper()
                if response.data.settings.currency is not None
                else None
            ),
        )
