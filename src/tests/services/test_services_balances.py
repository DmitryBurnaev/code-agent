from unittest.mock import AsyncMock, call
from decimal import Decimal
import logging

import httpx
import pytest
from pydantic import SecretStr

from src.exceptions import BalanceProviderError, BalanceProviderNotConfiguredError
from src.services.balances import (
    SELECTEL_IDENTITY_URL,
    SelectelBalanceProvider,
    _balance_cache,
    _iam_token_cache,
)
from src.settings import AppSettings


@pytest.fixture
def selectel_settings() -> AppSettings:
    return AppSettings(
        app_secret_key=SecretStr("test-key"),
        vendor_encryption_key=SecretStr("test-encryption-key"),
        selectel_balance_url="https://billing.example.test/v3/balances",
        selectel_balance_token=SecretStr("selectel-token"),
    )


@pytest.fixture(autouse=True)
def clear_selectel_caches() -> None:
    """Keep process-local provider caches isolated between tests."""
    _balance_cache.clear()
    _iam_token_cache.clear()


@pytest.fixture
def selectel_payload() -> dict[str, object]:
    return {
        "status": "success",
        "data": {
            "settings": {"currency": "rub"},
            "billings": [{"final_sum": 12050}, {"final_sum": -1830}],
        },
    }


async def test_selectel_provider_fetches_and_normalizes_balance(
    selectel_settings: AppSettings, selectel_payload: dict[str, object]
) -> None:
    http_client = AsyncMock(spec=httpx.AsyncClient)
    http_client.get.return_value = httpx.Response(200, json=selectel_payload)

    balance = await SelectelBalanceProvider(selectel_settings, http_client).get_balance()

    assert balance.balance == Decimal("102.20")
    assert balance.currency == "RUB"
    http_client.get.assert_awaited_once_with(
        "https://billing.example.test/v3/balances",
        headers={"X-Token": "selectel-token"},
    )


async def test_selectel_provider_caches_balance_for_configured_ttl(
    selectel_settings: AppSettings, selectel_payload: dict[str, object]
) -> None:
    http_client = AsyncMock(spec=httpx.AsyncClient)
    http_client.get.return_value = httpx.Response(200, json=selectel_payload)
    provider = SelectelBalanceProvider(selectel_settings, http_client)

    first_balance = await provider.get_balance()
    second_balance = await provider.get_balance()

    assert first_balance == second_balance
    http_client.get.assert_awaited_once_with(
        "https://billing.example.test/v3/balances",
        headers={"X-Token": "selectel-token"},
    )


async def test_selectel_provider_can_disable_balance_cache(
    selectel_payload: dict[str, object],
) -> None:
    settings = AppSettings(
        app_secret_key=SecretStr("test-key"),
        vendor_encryption_key=SecretStr("test-encryption-key"),
        selectel_balance_url="https://billing.example.test/v3/balances",
        selectel_balance_token=SecretStr("selectel-token"),
        selectel_balance_cache_ttl_seconds=0,
    )
    http_client = AsyncMock(spec=httpx.AsyncClient)
    http_client.get.return_value = httpx.Response(200, json=selectel_payload)
    provider = SelectelBalanceProvider(settings, http_client)

    await provider.get_balance()
    await provider.get_balance()

    assert http_client.get.await_count == 2


async def test_selectel_provider_accepts_empty_billings_as_zero_balance(
    selectel_settings: AppSettings,
) -> None:
    http_client = AsyncMock(spec=httpx.AsyncClient)
    http_client.get.return_value = httpx.Response(
        200,
        json={"status": "success", "data": {"settings": {"currency": "RUB"}}},
    )

    balance = await SelectelBalanceProvider(selectel_settings, http_client).get_balance()

    assert balance.balance == Decimal("0.00")
    assert balance.currency == "RUB"
    assert balance.model_dump(mode="json")["balance"] == "0.00"


async def test_selectel_provider_accepts_missing_currency(
    selectel_settings: AppSettings,
) -> None:
    http_client = AsyncMock(spec=httpx.AsyncClient)
    http_client.get.return_value = httpx.Response(
        200,
        json={"status": "success", "data": {"settings": {}, "billings": [{"final_sum": 150}]}},
    )

    balance = await SelectelBalanceProvider(selectel_settings, http_client).get_balance()

    assert balance.balance == Decimal("1.50")
    assert balance.currency is None


async def test_selectel_provider_logs_safe_request_stages(
    selectel_settings: AppSettings,
    selectel_payload: dict[str, object],
    caplog: pytest.LogCaptureFixture,
) -> None:
    http_client = AsyncMock(spec=httpx.AsyncClient)
    http_client.get.return_value = httpx.Response(200, json=selectel_payload)
    caplog.set_level(logging.DEBUG, logger="src.services.balances")

    await SelectelBalanceProvider(selectel_settings, http_client).get_balance()

    messages = caplog.messages
    assert "Selectel balance: requesting billing data" in messages
    assert "Selectel balance: using configured static-token authentication" in messages
    assert "Selectel balance: billing data received" in messages
    assert "selectel-token" not in "\n".join(messages)
    levels_by_message = {record.message: record.levelno for record in caplog.records}
    assert levels_by_message["Selectel balance: requesting billing data"] == logging.DEBUG
    assert (
        levels_by_message["Selectel balance: using configured static-token authentication"]
        == logging.INFO
    )
    assert levels_by_message["Selectel balance: billing data received"] == logging.INFO


async def test_selectel_provider_uses_and_caches_service_account_iam_token(
    selectel_payload: dict[str, object],
) -> None:
    settings = AppSettings(
        app_secret_key=SecretStr("test-key"),
        vendor_encryption_key=SecretStr("test-encryption-key"),
        selectel_balance_url="https://billing.example.test/v3/balances",
        selectel_balance_token=SecretStr(""),
        selectel_balance_cache_ttl_seconds=0,
        selectel_balance_username="billing-service-user",
        selectel_balance_account_id="123456",
        selectel_balance_password=SecretStr("service-account-password"),
    )
    http_client = AsyncMock(spec=httpx.AsyncClient)
    http_client.post.return_value = httpx.Response(
        201,
        headers={"X-Subject-Token": "iam-token"},
    )
    http_client.get.return_value = httpx.Response(200, json=selectel_payload)
    provider = SelectelBalanceProvider(settings, http_client)

    await provider.get_balance()
    await provider.get_balance()

    http_client.post.assert_awaited_once_with(
        SELECTEL_IDENTITY_URL,
        json={
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": "billing-service-user",
                            "domain": {"name": "123456"},
                            "password": "service-account-password",
                        }
                    },
                },
                "scope": {"domain": {"name": "123456"}},
            }
        },
    )
    assert http_client.get.await_args_list == [
        call(
            "https://billing.example.test/v3/balances",
            headers={"X-Auth-Token": "iam-token"},
        ),
        call(
            "https://billing.example.test/v3/balances",
            headers={"X-Auth-Token": "iam-token"},
        ),
    ]


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
