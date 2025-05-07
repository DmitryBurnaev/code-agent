"""HTTP client for AI providers."""

import httpx

from src.settings import AppSettings
from src.models import LLMProvider


class AIProviderHTTPClient(httpx.AsyncClient):
    """Wrapper around httpx.AsyncClient for AI providers."""

    def __init__(
        self,
        settings: AppSettings,
        provider: LLMProvider | None = None,
        timeout: int | None = None,
        retries: int | None = None,
    ) -> None:
        transport = httpx.AsyncHTTPTransport(
            retries=(retries or settings.provider_default_retries),
            proxy=settings.http_proxy_url,
        )
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if provider is not None:
            headers |= provider.auth_headers

        super().__init__(
            transport=transport,
            headers=headers,
            timeout=timeout or settings.provider_default_timeout,
        )

    @property
    def transport(self) -> httpx.AsyncHTTPTransport:
        """Return the transport instance."""
        return self._transport  # type: ignore

    @property
    def proxies(self) -> dict[str, str] | None:
        """Return the proxies configuration."""
        return self._proxies  # type: ignore
