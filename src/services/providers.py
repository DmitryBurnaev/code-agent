import asyncio
import logging
import urllib.parse
from typing import TYPE_CHECKING, Iterable

import httpx
from pydantic import BaseModel

from src.constants import Provider
from src.services.http import AIProviderHTTPClient
from src.models import LLMProvider, AIModel
from src.utils import Cache, singleton

if TYPE_CHECKING:
    from src.settings import AppSettings

logger = logging.getLogger(__name__)


class ProviderAIModel(BaseModel):
    """
    Parse provider sent data
    Example: {'id': 'o1-mini', 'object': 'model', 'created': 1725649008, 'owned_by': 'system'}
    """

    id: str


class ProviderAIModelsResponse(BaseModel):
    """Represents an AI model with provider-specific details."""

    data: list[ProviderAIModel]


class ProviderClient:
    """Generic client for AI providers."""

    def __init__(self, provider: LLMProvider, http_client: httpx.AsyncClient):
        self._provider = provider
        self._base_url = provider.base_url
        self._http_client = http_client

    async def get_list_models(self) -> list[AIModel]:
        """List available models from the provider."""
        url = urllib.parse.urljoin(self._base_url, "models")

        async def _fetch_models() -> list[AIModel]:
            async with self._http_client as http_client:
                response = await http_client.get(url, headers=self._provider.auth_headers)
                if response.status_code != httpx.codes.OK:
                    logger.warning(
                        "%s | Failed to fetch models from provider: code: %s | resp: %s",
                        self._provider,
                        response.status_code,
                        response.text,
                    )
                    return []

                if not (response_data := response.json()):
                    logger.warning("%s | No models data in provider response.", self._provider)
                    return []

                models_data = ProviderAIModelsResponse.model_validate(response_data)
                vendor = self._provider.vendor
                return [
                    AIModel(id=f"{vendor}__{model.id}", vendor=vendor, vendor_id=model.id)
                    for model in models_data.data
                ]

        models: list[AIModel] = []
        try:
            models = await _fetch_models()
        except Exception as exc:
            logger.exception(f"Failed to list {self._provider} models: {exc}. Skipping.")

        return models

    @staticmethod
    def _is_chat_model(model: dict[str, str]) -> bool:
        """Check if the model is a chat model based on provider-specific rules."""
        model_id = model["id"]
        model_type = model.get("type")

        if model_type == "chat":  # Anthropic-style
            return True

        if model_id.startswith(("gpt-", "text-")):  # OpenAI-style
            return True

        # Add more provider-specific rules as needed
        return False

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._http_client.aclose()


@singleton
class ProviderService:
    """Service for managing AI providers and their configurations."""

    def __init__(
        self, settings: "AppSettings", http_client: httpx.AsyncClient | None = None
    ) -> None:
        """Initialize the service with settings.

        Args:
            settings: Application settings containing provider configurations.
        """
        self._settings = settings
        self._models_cache = Cache[list[AIModel]](ttl=settings.models_cache_ttl)
        self._provider_clients: dict[Provider, ProviderClient] = {}
        self._http_client = http_client or AIProviderHTTPClient(settings)

    def get_client(self, provider: LLMProvider) -> ProviderClient:
        """Get or create a client for the specified provider."""
        if provider.vendor not in self._provider_clients:
            self._provider_clients[provider.vendor] = ProviderClient(provider, self._http_client)

        return self._provider_clients[provider.vendor]

    async def get_list_models(self, force_refresh: bool = False) -> list[AIModel]:
        """Get a list of available models from all configured providers.

        Args:
            force_refresh: If True, ignore cache and fetch fresh data

        Results are cached per provider with TTL defined in settings.
        If a provider fails, other providers' cached data remains valid.
        """
        all_models = []
        tasks = []
        providers = []
        logger.info("Fetching models from all providers...")
        for llm_provider in self._settings.providers:
            logger.debug(
                "Provider %s: fetching models (force_refresh: %s)",
                llm_provider.vendor,
                force_refresh,
            )
            if not force_refresh:
                cached = self._models_cache.get(str(llm_provider.vendor))
                if cached is not None:
                    all_models.extend(cached)
                    continue

            providers.append(llm_provider)
            client = self.get_client(llm_provider)
            tasks.append(client.get_list_models())

        if tasks:
            # Run tasks in parallel for providers that need refresh
            results: Iterable[list[AIModel] | BaseException] = await asyncio.gather(
                *tasks, return_exceptions=True
            )

            # Process results and update cache for each provider
            for provider, result in zip(providers, results):
                if isinstance(result, BaseException):
                    logger.error(f"Failed to list models for {provider}: {result!r}")
                    continue

                if result:
                    self._models_cache.set(provider.vendor, result)
                    all_models.extend(result)
                else:
                    logger.debug(f"No models for {provider}: {result!r}")

        return all_models

    def invalidate_models_cache(self, provider: str | None = None) -> None:
        """Force invalidation of models' cache.

        Args:
            provider: Specific provider to invalidate cache for.
                     If None - invalidate cache for all providers.
        """
        self._models_cache.invalidate(provider)

    async def close(self) -> None:
        """Close all provider clients."""
        for client in self._provider_clients.values():
            await client.close()
