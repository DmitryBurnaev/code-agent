"""HTTP client for AI vendors."""

import logging
from typing import Any

import httpx
from httpx import URL, Response

from src.settings import AppSettings
from src.models import LLMVendor

logger = logging.getLogger(__name__)


class VendorHTTPClient(httpx.AsyncClient):
    """Wrapper around httpx.AsyncClient for AI vendors."""

    def __init__(
        self,
        settings: AppSettings,
        vendor: LLMVendor | None = None,
        timeout: int | None = None,
        retries: int | None = None,
    ) -> None:
        transport = httpx.AsyncHTTPTransport(
            retries=(retries or settings.vendor_default_retries),
            proxy=settings.http_proxy_url,
        )
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if vendor is not None:
            headers |= vendor.auth_headers

        super().__init__(
            transport=transport,
            headers=headers,
            timeout=timeout or settings.vendor_default_timeout,
        )

    async def get(self, url: URL | str, **kwargs: Any) -> Response:
        logger.info(f"Request [GET]: {url}")
        response = await super().get(url=url, **kwargs)
        return response

    @property
    def transport(self) -> httpx.AsyncHTTPTransport:
        """Return the transport instance."""
        return self._transport  # type: ignore

    @property
    def proxies(self) -> dict[str, str] | None:
        """Return the proxies' configuration."""
        return self._proxies  # type: ignore
