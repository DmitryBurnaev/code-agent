"""HTTP client for AI providers."""

import httpx

from src.settings import AppSettings
from src.models import LLMProvider


class AIProviderHTTPClient(httpx.AsyncClient):
    _DEFAULT_MAX_RETRIES: int = 2
    _DEFAULT_TIMEOUT: float = 30.0  # Default timeout in seconds

    def __init__(
        self,
        settings: AppSettings,
        provider: LLMProvider | None = None,
        retries: int = _DEFAULT_MAX_RETRIES,
        timeout: float | None = None,
    ) -> None:
        transport = httpx.AsyncHTTPTransport(retries=retries, proxy=settings.http_proxy_url)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if provider is not None:
            headers |= provider.auth_headers

        super().__init__(
            transport=transport,
            headers=headers,
            timeout=timeout or self._DEFAULT_TIMEOUT,
        )

    @property
    def transport(self) -> httpx.AsyncHTTPTransport:
        """Return the transport instance."""
        return self._transport  # type: ignore

    @property
    def proxies(self) -> dict[str, str] | None:
        """Return the proxies configuration."""
        return self._proxies  # type: ignore
