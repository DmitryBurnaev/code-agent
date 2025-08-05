import asyncio
import logging
import urllib.parse
from typing import TYPE_CHECKING, Iterable

import httpx
from pydantic import BaseModel

from src.db.repositories import VendorRepository
from src.db.services import SASessionUOW
from src.services.cache import CacheProtocol, InMemoryCache
from src.constants import VendorSlug
from src.services.http import VendorHTTPClient
from src.models import LLMVendor, AIModel

if TYPE_CHECKING:
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
                    "%s | Failed to fetch models from vendor: code: %s | resp: %s",
                    self._vendor,
                    response.status_code,
                    response.text,
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
            logger.exception(f"Failed to list {self._vendor} models: {exc}. Skipping.")

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

    async def get_list_models(self, force_refresh: bool = False) -> list[AIModel]:
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

        if self._settings.offline_test_mode:
            return self._mocked_models(vendors=[vendor.slug for vendor in active_vendors])

        all_models = []
        tasks = []
        vendors = []
        logger.info("Fetching models from all vendors...")
        for vendor in active_vendors:
            logger.debug(
                "Vendor %s: fetching models (force_refresh: %s)",
                vendor,
                force_refresh,
            )
            llm_vendor = LLMVendor.from_vendor(vendor)
            if not force_refresh:
                print(vendor.slug, self._cache._data)
                cached = self._cache_get_data(vendor.slug)
                if cached is not None:
                    all_models.extend(cached)
                    continue

            vendors.append(llm_vendor)
            vendor_client = self.get_client(llm_vendor)
            tasks.append(vendor_client.get_list_models())

        if tasks:
            # Run tasks in parallel for vendors that need refresh
            results: Iterable[list[AIModel] | BaseException] = await asyncio.gather(
                *tasks, return_exceptions=True
            )

            # Process results and update cache for each vendor
            for llm_vendor, result in zip(vendors, results):
                if isinstance(result, BaseException):
                    logger.error(f"Failed to list models for {llm_vendor}: {result!r}")
                    continue

                if result:
                    self._cache_set_data(llm_vendor.slug, result)
                    all_models.extend(result)
                else:
                    logger.debug(f"No models for {llm_vendor}: {result!r}")

        return all_models

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
