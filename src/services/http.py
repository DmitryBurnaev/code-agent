import httpx

from src.settings import AppSettings
from src.models import LLMProvider


class AIProviderHTTPClient(httpx.AsyncClient):
    _DEFAULT_MAX_RETRIES: int = 2

    def __init__(
        self,
        settings: AppSettings,
        provider: LLMProvider | None = None,
        retries: int = _DEFAULT_MAX_RETRIES,
    ) -> None:
        transport = httpx.AsyncHTTPTransport(retries=retries)
        proxy = httpx.Proxy(url=settings.http_proxy_url) if settings.http_proxy_url else None
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if provider is not None:
            headers |= provider.auth_headers

        super().__init__(
            transport=transport,
            proxy=proxy,
            headers=headers,
        )
