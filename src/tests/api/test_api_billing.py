from unittest.mock import AsyncMock
from decimal import Decimal

from fastapi import FastAPI, status
import pytest
from starlette.testclient import TestClient

from src.exceptions import BalanceProviderError
from src.models import Balance
from src.modules.api.billing import router
from src.services.balances import SelectelBalanceProvider


def test_get_balance_returns_normalized_selectel_balance(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        SelectelBalanceProvider,
        "get_balance",
        AsyncMock(return_value=Balance(balance=Decimal("102.20"), currency="RUB")),
    )

    response = client.get("/api/billing/balance/")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"balance": "102.20", "currency": "RUB"}


def test_get_balance_omits_missing_currency(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        SelectelBalanceProvider,
        "get_balance",
        AsyncMock(return_value=Balance(balance=Decimal("102.12"))),
    )

    response = client.get("/api/billing/balance/")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"balance": "102.12"}


def test_balance_openapi_response_example() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api")

    response = app.openapi()["paths"]["/api/billing/balance/"]["get"]["responses"]["200"]

    assert response["content"]["application/json"]["example"] == {
        "balance": "102.12",
        "currency": "RUB",
    }


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
