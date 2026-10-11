"""Billing API endpoints."""

from fastapi import APIRouter

from src.models import Balance
from src.modules.api.base import ErrorHandlingBaseRoute
from src.services.balances import SelectelBalanceProvider
from src.settings import SettingsDep

router = APIRouter(prefix="/billing", tags=["billing"], route_class=ErrorHandlingBaseRoute)


@router.get("/balance/", response_model=Balance)
async def get_balance(settings: SettingsDep) -> Balance:
    """Return the current normalized Selectel account balance."""
    return await SelectelBalanceProvider(settings).get_balance()
