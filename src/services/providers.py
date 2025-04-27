import asyncio
import logging
import urllib.parse
from typing import TYPE_CHECKING

import httpx
from pydantic import BaseModel

from src.services.http import AIProviderHTTPClient
from src.models import LLMProvider, AIModel
from src.utils import Cache

if TYPE_CHECKING:
    from src.settings import AppSettings

logger = logging.getLogger(__name__)


class ProviderAIModelsResponse(BaseModel):
    """Represents an AI model with provider-specific details."""

    models: list[AIModel]


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
                    logger.warning("%s | Failed to fetch models from provider.", self._provider)
                    return []

                if not (response_data := response.json().get("data")):
                    logger.warning("%s | No models data in provider response.", self._provider)
                    return []

                models_data = ProviderAIModelsResponse.model_validate(
                    response_data, context={"vendor": self._provider.vendor}
                )
                return [ai_model for ai_model in models_data.models if ai_model.is_chat_model]

        models: list[AIModel] = []
        try:
            models = await _fetch_models()
        except Exception as exc:
            logger.error(f"Failed to list {self._provider} models: {exc}. Skipping.")

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
        self._provider_clients: dict[LLMProvider, ProviderClient] = {}
        self._http_client = http_client or AIProviderHTTPClient(settings)

    def get_client(self, provider: LLMProvider) -> ProviderClient:
        """Get or create a client for the specified provider."""
        if provider not in self._provider_clients:
            self._provider_clients[provider] = ProviderClient(provider, self._http_client)

        return self._provider_clients[provider]

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
        for llm_provider in self._settings.providers:
            # route = self._find_provider_route(llm_provider)
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
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results and update cache for each provider
            for provider, result in zip(providers, results):
                if isinstance(result, BaseException):
                    logger.error(f"Failed to list models for {provider}: {result!r}")
                    continue

                self._models_cache.set(provider.vendor, result)
                all_models.extend(result)

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
