"""Balance provider integrations."""

from abc import ABC, abstractmethod
import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from src.exceptions import BalanceProviderError, BalanceProviderNotConfiguredError
from src.models import Balance
from src.services.http import VendorHTTPClient
from src.settings import AppSettings

logger = logging.getLogger(__name__)


class BalanceProvider(ABC):
    """Base class for providers that normalize an upstream balance response."""

    def __init__(self, settings: AppSettings, http_client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http_client = http_client

    @property
    @abstractmethod
    def url(self) -> str:
        """Return the configured upstream URL."""

    @property
    @abstractmethod
    def headers(self) -> dict[str, str]:
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
        if self._http_client is not None:
            return await self._http_client.get(self.url, headers=self.headers)

        async with VendorHTTPClient(self._settings) as http_client:
            return await http_client.get(self.url, headers=self.headers)

    @abstractmethod
    def postprocess(self, payload: Any) -> Balance:
        """Convert an upstream JSON payload into the public balance contract."""


class SelectelBalanceSettings(BaseModel):
    """Relevant Selectel billing settings from the upstream response."""

    currency: str


class SelectelBilling(BaseModel):
    """A Selectel billing bucket contributing to the account balance."""

    final_sum: int


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

    @property
    def url(self) -> str:
        url = self._settings.selectel_balance_url
        if not url:
            raise BalanceProviderNotConfiguredError(
                "Selectel balance integration is not configured"
            )
        return url

    @property
    def headers(self) -> dict[str, str]:
        token = self._settings.selectel_balance_token
        if token is None:
            raise BalanceProviderNotConfiguredError(
                "Selectel balance integration is not configured"
            )
        return {"X-Token": token.get_secret_value()}

    def postprocess(self, payload: Any) -> Balance:
        response = SelectelBalancePayload.model_validate(payload)
        return Balance(
            balance=str(sum(billing.final_sum for billing in response.data.billings)),
            currency=response.data.settings.currency,
        )
