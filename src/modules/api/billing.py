"""Billing API endpoints."""

from fastapi import APIRouter, Depends

from src.models import Balance
from src.modules.api.base import ErrorHandlingBaseRoute
from src.services.balances import SelectelBalanceProvider
from src.settings import SettingsDep
from src.modules.auth.dependencies import APIAccess
from src.modules.auth.permissions import Permission

router = APIRouter(
    dependencies=[Depends(APIAccess(Permission.BILLING))],
    prefix="/billing",
    tags=["billing"],
    route_class=ErrorHandlingBaseRoute,
)


@router.get(
    "/balance/",
    response_model=Balance,
    response_model_exclude_none=True,
    responses={
        200: {
            "description": "Normalized Selectel balance.",
            "content": {
                "application/json": {
                    "example": {"balance": "102.12", "currency": "RUB"},
                }
            },
        }
    },
)
async def get_balance(settings: SettingsDep) -> Balance:
    """Return the current normalized Selectel account balance."""
    return await SelectelBalanceProvider(settings).get_balance()
