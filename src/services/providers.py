import asyncio
import logging
import urllib.parse
from dataclasses import dataclass
from typing import Dict, List, Optional, TYPE_CHECKING

import httpx
from fastapi import HTTPException

from src.settings import ProxyRoute, LLMProvider
from src.utils import Cache, retry_with_timeout

if TYPE_CHECKING:
    from src.settings import AppSettings

logger = logging.getLogger(__name__)


@dataclass
class AIModel:
    """Represents an AI model with provider-specific details."""

    id: str
    name: str
    vendor: str


class ProviderClient:
    """Generic client for AI providers."""

    # Default retry settings
    _DEFAULT_RETRY_DELAY: float = 1.0  # seconds
    _DEFAULT_MAX_RETRIES: int = 1

    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self._base_url = provider.base_url
        self._client = httpx.AsyncClient()

    async def list_models(self) -> list[AIModel]:
        """List available models from the provider."""

        # @retry_with_timeout(
        #     max_retries=self._DEFAULT_MAX_RETRIES,
        #     retry_delay=self._DEFAULT_RETRY_DELAY,
        # )
        @retry_with_timeout
        async def _fetch_models() -> list[AIModel]:
            url = urllib.parse.urljoin(self._base_url, "models")
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"{self.provider.auth_type} {self.provider.api_key}",
            }

            async with self._client as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()

                data = response.json()
                models_data = data.get("data") or data.get("models", [])

                return [
                    AIModel(
                        id=model["id"],
                        name=model["name"],
                        vendor=self.provider.vendor,
                    )
                    for model in models_data
                    if self._is_chat_model(model)
                ]

        # models = await _fetch_models()
        # models: list[AIModel] = []
        # TODO: think about typing here
        try:
            models = await _fetch_models()
        except Exception as e:
            logger.error(f"Failed to list {self.provider} models: {e}. Skipping.")

        return models

    def _is_chat_model(self, model: Dict) -> bool:
        """Check if model is a chat model based on provider-specific rules."""
        model_id = model["id"]
        model_type = model.get("type")

        if model_type == "chat":  # Anthropic-style
            return True

        if model_id.startswith(("gpt-", "text-")):  # OpenAI-style
            return True

        # Add more provider-specific rules as needed
        return False

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()


class ProviderService:
    """Service for managing AI providers and their configurations."""

    def __init__(self, settings: "AppSettings") -> None:
        """Initialize the service with settings.

        Args:
            settings: Application settings containing provider configurations.
        """
        self.settings = settings
        self._models_cache = Cache[List[AIModel]](ttl=settings.models_cache_ttl)
        self._clients: Dict[str, ProviderClient] = {}

    def get_client(self, provider: str) -> ProviderClient:
        """Get or create a client for the specified provider."""
        if provider not in self._clients:
            route = self._find_provider_route(provider)
            if not route:
                raise HTTPException(
                    status_code=400,
                    detail=f"Provider '{provider}' is not configured",
                )

            self._clients[provider] = ProviderClient(provider, route)

        return self._clients[provider]

    def _find_provider_route(self, provider: str) -> Optional[ProxyRoute]:
        """Find proxy route for the provider."""
        provider_path = f"/proxy/{provider}"
        for route in self.settings.proxy_routes:
            if route.source_path.startswith(provider_path):
                return route
        return None

    async def list_models(self, force_refresh: bool = False) -> List[AIModel]:
        """Get list of available models from all configured providers.

        Args:
            force_refresh: If True, ignore cache and fetch fresh data

        Results are cached per provider with TTL defined in settings.
        If a provider fails, other providers' cached data remains valid.
        """
        all_models = []
        tasks = []
        providers = []

        # Check cache and create tasks for expired/missing providers
        for route in self.settings.proxy_routes:
            if not route.source_path.startswith("/proxy/"):
                continue

            provider = route.source_path.split("/")[2]
            if not force_refresh:
                cached = self._models_cache.get(provider)
                if cached is not None:
                    all_models.extend(cached)
                    continue

            providers.append(provider)
            client = self.get_client(provider)
            tasks.append(client.list_models())

        if tasks:
            # Run tasks in parallel for providers that need refresh
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results and update cache for each provider
            for provider, result in zip(providers, results):
                if isinstance(result, Exception):
                    logger.error(f"Failed to list models for {provider}: {result}")
                    continue

                self._models_cache.set(provider, result)
                all_models.extend(result)

        return all_models

    def invalidate_models_cache(self, provider: Optional[str] = None) -> None:
        """Force invalidation of models cache.

        Args:
            provider: Specific provider to invalidate cache for.
                     If None - invalidate cache for all providers.
        """
        self._models_cache.invalidate(provider)

    async def close(self):
        """Close all provider clients."""
        for client in self._clients.values():
            await client.close()
