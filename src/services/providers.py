import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, TYPE_CHECKING

import httpx
from fastapi import HTTPException

from src.settings import ProxyRoute
from src.utils import Cache

if TYPE_CHECKING:
    from src.settings import AppSettings

logger = logging.getLogger(__name__)


@dataclass
class AIModel:
    """Represents an AI model with provider-specific details."""

    id: str
    provider: str

    @property
    def name(self) -> str:
        """Get human-readable model name."""
        return f"{self.provider}: {self.id}"

    @property
    def full_name(self) -> str:
        """Get the full model name with provider prefix."""
        return f"{self.provider}__{self.id}"


class ProviderClient:
    """Generic client for AI providers."""

    # Default retry settings
    _DEFAULT_RETRY_DELAY: float = 1.0  # seconds
    _DEFAULT_MAX_RETRIES: int = 1

    def __init__(self, provider: str, route: ProxyRoute):
        self.provider = provider
        self.route = route
        self._client = httpx.AsyncClient()

    async def _retry_with_timeout(
        self,
        operation: callable,
        *,
        max_retries: Optional[int] = None,
        retry_delay: Optional[float] = None,
    ):
        """Execute operation with retries on failure."""
        max_retries = max_retries if max_retries is not None else self._DEFAULT_MAX_RETRIES
        retry_delay = retry_delay if retry_delay is not None else self._DEFAULT_RETRY_DELAY

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return await operation()
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    delay = retry_delay * (attempt + 1)
                    logger.warning(
                        f"Request to {self.provider} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Request to {self.provider} failed after {max_retries + 1} attempts: {e}"
                    )

        raise last_error

    async def list_models(self) -> List[AIModel]:
        """List available models from the provider."""

        async def _fetch_models():
            url = f"{self.route.target_url.rstrip('/')}/models"
            headers = {}

            # Add auth if configured
            if self.route.auth_token:
                headers["Authorization"] = (
                    f"{self.route.auth_type} {self.route.auth_token.get_secret_value()}"
                )

            # Add any additional headers from route config
            if self.route.additional_headers:
                headers.update(self.route.additional_headers)

            async with self._client as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()

                data = response.json()
                models_data = data.get("data") or data.get("models", [])

                return [
                    AIModel(
                        id=model["id"],
                        provider=self.provider,
                    )
                    for model in models_data
                    # TODO: Make model filtering configurable per provider
                    if self._is_chat_model(model)
                ]

        try:
            return await self._retry_with_timeout(_fetch_models)
        except Exception as e:
            logger.error(f"Failed to list {self.provider} models: {e}")
            return []

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
