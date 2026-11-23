import asyncio
import logging
import urllib.parse
from typing import TYPE_CHECKING, Iterable

import httpx
from pydantic import BaseModel

from src.db.repositories import VendorRepository
from src.db.services import SASessionUOW
from src.services.cache import CacheProtocol, InMemoryCache
from src.constants import VendorMode, VendorSlug
from src.modules.auth.permissions import Permission, has_permission
from src.services.cursor import CursorClient, CursorError
from src.db.diagnostics import failure_details
from src.services.http import VendorHTTPClient
from src.models import LLMVendor, AIModel

if TYPE_CHECKING:
    from src.db.models import User, Vendor
    from src.settings import AppSettings

logger = logging.getLogger(__name__)


class VendorModelResponse(BaseModel):
    """
    Parse vendor sent data
    Example: {'id': 'o1-mini', 'object': 'model', 'created': 1725649008, 'owned_by': 'system'}
    """

    id: str


class VendorDataResponse(BaseModel):
    """Represents an AI model with vendor-specific details."""

    data: list[VendorModelResponse]


class VendorClient:
    """Generic client for AI vendors."""

    def __init__(self, vendor: LLMVendor, http_client: httpx.AsyncClient):
        self._vendor = vendor
        self._base_url = vendor.base_url
        self._http_client = http_client

    async def get_list_models(self) -> list[AIModel]:
        """List available models from the vendor."""
        url = urllib.parse.urljoin(self._base_url, "models")

        async def _fetch_models() -> list[AIModel]:
            response = await self._http_client.get(url, headers=self._vendor.auth_headers)
            if response.status_code != httpx.codes.OK:
                logger.warning(
                    "%s | Failed to fetch models from vendor: code: %s",
                    self._vendor,
                    response.status_code,
                )
                return []

            if not (response_data := response.json()):
                logger.warning("%s | No models data in vendor response.", self._vendor)
                return []

            models_data = VendorDataResponse.model_validate(response_data)
            vendor = self._vendor.slug
            return [AIModel.from_vendor(vendor, model_id=model.id) for model in models_data.data]

        models: list[AIModel] = []
        try:
            models = await _fetch_models()
        except Exception as exc:
            logger.warning("Failed to list %s models: %s", self._vendor.slug, failure_details(exc))

        return models

    @staticmethod
    def _is_chat_model(model: dict[str, str]) -> bool:
        """Check if the model is a chat model based on vendor-specific rules."""
        model_id = model["id"]
        model_type = model.get("type")

        if model_type == "chat":  # Anthropic-style
            return True

        if model_id.startswith(("gpt-", "text-")):  # OpenAI-style
            return True

        # Add more vendor-specific rules as needed
        return False


class VendorService:
    """Service for managing AI vendors and their configurations."""

    def __init__(
        self,
        settings: "AppSettings",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the service with settings.

        Args:
            settings: Application settings containing vendor configurations.
        """
        self._settings = settings
        self._cache: CacheProtocol = InMemoryCache()
        self._vendor_clients: dict[str, VendorClient] = {}
        self._http_client = http_client or VendorHTTPClient(settings)

    def get_client(self, llm_vendor: LLMVendor) -> VendorClient:
        """Get or create a client for the specified vendor."""
        if llm_vendor.slug not in self._vendor_clients:
            self._vendor_clients[llm_vendor.slug] = VendorClient(llm_vendor, self._http_client)

        return self._vendor_clients[llm_vendor.slug]

    async def get_list_models(
        self, force_refresh: bool = False, *, user: "User | None" = None
    ) -> list[AIModel]:
        """Get a list of available models from all configured vendors.

        Args:
            force_refresh: If True, ignore cache and fetch fresh data

        Results are cached per vendor with TTL defined in settings.
        If a vendor fails, other vendors' cached data remains valid.
        """
        async with SASessionUOW() as uow:
            active_vendors = await VendorRepository(session=uow.session).filter(is_active=True)

        if not active_vendors:
            logger.warning("No active vendors detected.")
            return []

        if self._settings.flags.offline_mode:
            return self._mocked_models(
                vendors=[
                    vendor.slug
                    for vendor in active_vendors
                    if vendor.auth_mode != VendorMode.SUBSCRIPTION
                ]
            )

        all_models = []
        tasks = []
        vendors = []
        logger.info("Fetching models from all vendors...")
        for vendor in active_vendors:
            if vendor.auth_mode == VendorMode.SUBSCRIPTION:
                if has_permission(user, Permission.LLM) and has_permission(
                    user, Permission.AI_SUBSCRIPTIONS
                ):
                    tasks.append(self._subscription_models(vendor, force_refresh))
                    vendors.append(vendor)
                continue
            logger.debug(
                "Vendor %s: fetching models (force_refresh: %s)",
                vendor,
                force_refresh,
            )
            try:
                llm_vendor = LLMVendor.from_vendor(vendor)
            except Exception as exc:
                logger.warning(
                    "Failed to configure vendor %s: %s", vendor.slug, failure_details(exc)
                )
                continue

            if not force_refresh:
                cached = self._cache_get_data(vendor.slug)
                if cached is not None:
                    all_models.extend(cached)
                    continue

            vendors.append(vendor)
            vendor_client = self.get_client(llm_vendor)
            tasks.append(vendor_client.get_list_models())

        if tasks:
            # Run tasks in parallel for vendors that need refresh
            results: Iterable[list[AIModel] | BaseException] = await asyncio.gather(
                *tasks, return_exceptions=True
            )

            # Process results and update cache for each vendor
            for vendor, result in zip(vendors, results):
                if isinstance(result, BaseException):
                    logger.error(
                        "Failed to list models for %s: %s", vendor.slug, failure_details(result)
                    )
                    continue

                if result:
                    if vendor.auth_mode != VendorMode.SUBSCRIPTION:
                        self._cache_set_data(vendor.slug, result)
                    all_models.extend(result)
                else:
                    logger.debug("No models for %s", vendor.slug)

        return all_models

    async def _subscription_models(self, vendor: "Vendor", force_refresh: bool) -> list[AIModel]:
        if vendor.slug != VendorSlug.CURSOR or not vendor.subscription_models:
            return []
        try:
            available = set(await CursorClient(self._settings).models(refresh=force_refresh))
        except CursorError as exc:
            logger.warning("Cursor catalog unavailable: %s", exc.code)
            return []
        return [
            AIModel.from_vendor(vendor.slug, model)
            for model in vendor.subscription_models
            if model in available
        ]

    def _cache_set_data(self, vendor: str, models: list[AIModel]) -> None:
        self._cache.set(vendor, [model.model_dump() for model in models])

    def _cache_get_data(self, vendor: str) -> list[AIModel] | None:
        cached = self._cache.get(vendor)
        if not cached or not isinstance(cached, list):
            logger.debug(f"No cached models for {vendor}: {cached!r}")
            return None

        return [AIModel.model_validate(model_data) for model_data in cached]

    @staticmethod
    def _mocked_models(vendors: list[str]) -> list[AIModel]:
        mocked_models: dict[str, list[str]] = {
            VendorSlug.OPENAI.name: ["openai-chat", "o12-macro"],
            VendorSlug.DEEPSEEK.name: ["deepseek-chat", "deepseek-think"],
            VendorSlug.ANTHROPIC.name: ["anthropic-123"],
        }
        result = []
        for vendor in vendors:
            for model in mocked_models.get(vendor, []):
                result.append(AIModel.from_vendor(vendor, model))

        return result
