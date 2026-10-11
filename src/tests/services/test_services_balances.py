from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr

from src.exceptions import BalanceProviderError, BalanceProviderNotConfiguredError
from src.services.balances import SelectelBalanceProvider
from src.settings import AppSettings


@pytest.fixture
def selectel_settings() -> AppSettings:
    return AppSettings(
        app_secret_key=SecretStr("test-key"),
        vendor_encryption_key=SecretStr("test-encryption-key"),
        selectel_balance_url="https://billing.example.test/v3/balances",
        selectel_balance_token=SecretStr("selectel-token"),
    )


@pytest.fixture
def selectel_payload() -> dict[str, object]:
    return {
        "status": "success",
        "data": {
            "settings": {"currency": "RUB"},
            "billings": [{"final_sum": 1200}, {"final_sum": -200}],
        },
    }


async def test_selectel_provider_fetches_and_normalizes_balance(
    selectel_settings: AppSettings, selectel_payload: dict[str, object]
) -> None:
    http_client = AsyncMock(spec=httpx.AsyncClient)
    http_client.get.return_value = httpx.Response(200, json=selectel_payload)

    balance = await SelectelBalanceProvider(selectel_settings, http_client).get_balance()

    assert balance.balance == "1000"
    assert balance.currency == "RUB"
    http_client.get.assert_awaited_once_with(
        "https://billing.example.test/v3/balances",
        headers={"X-Token": "selectel-token"},
    )


async def test_selectel_provider_accepts_empty_billings_as_zero_balance(
    selectel_settings: AppSettings,
) -> None:
    http_client = AsyncMock(spec=httpx.AsyncClient)
    http_client.get.return_value = httpx.Response(
        200,
        json={"status": "success", "data": {"settings": {"currency": "RUB"}}},
    )

    balance = await SelectelBalanceProvider(selectel_settings, http_client).get_balance()

    assert balance.balance == "0"
    assert balance.currency == "RUB"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, json={}),
        httpx.Response(200, json={"status": "success", "data": {}}),
    ],
)
async def test_selectel_provider_hides_upstream_failures(
    selectel_settings: AppSettings, response: httpx.Response
) -> None:
    http_client = AsyncMock(spec=httpx.AsyncClient)
    http_client.get.return_value = response

    with pytest.raises(BalanceProviderError) as error:
        await SelectelBalanceProvider(selectel_settings, http_client).get_balance()

    assert "selectel-token" not in str(error.value)


async def test_selectel_provider_requires_configuration() -> None:
    settings = AppSettings(
        app_secret_key=SecretStr("test-key"),
        vendor_encryption_key=SecretStr("test-encryption-key"),
    )

    with pytest.raises(BalanceProviderNotConfiguredError):
        await SelectelBalanceProvider(settings).get_balance()
