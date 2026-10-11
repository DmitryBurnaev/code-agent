from unittest.mock import AsyncMock

from fastapi import status
import pytest
from starlette.testclient import TestClient

from src.exceptions import BalanceProviderError
from src.models import Balance
from src.services.balances import SelectelBalanceProvider


def test_get_balance_returns_normalized_selectel_balance(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        SelectelBalanceProvider,
        "get_balance",
        AsyncMock(return_value=Balance(balance="1000", currency="RUB")),
    )

    response = client.get("/api/billing/balance/")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"balance": "1000", "currency": "RUB"}


def test_get_balance_returns_safe_error_when_provider_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        SelectelBalanceProvider,
        "get_balance",
        AsyncMock(side_effect=BalanceProviderError("Balance provider is unavailable")),
    )

    response = client.get("/api/billing/balance/")

    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    assert response.json()["detail"] == "Balance provider is unavailable"
