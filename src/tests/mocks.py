import json
import dataclasses
from typing import Any, Self
from unittest.mock import AsyncMock


@dataclasses.dataclass
class MockUser:
    id: int
    is_active: bool = False
    username: str = "test-user"


@dataclasses.dataclass
class MockAPIToken:
    is_active: bool
    user: MockUser


@dataclasses.dataclass
class MockVendor:
    id: int
    name: str
    slug: str
    is_active: bool = True
    timeout: int = 10

    @property
    def api_url(self) -> str:
        return f"https://api.{self.slug}.com/v1/"

    @property
    def decrypted_api_key(self) -> str:
        return f"decrypted-{self.slug}-api-key"


@dataclasses.dataclass
class MockTestResponse:
    headers: dict[str, str]
    data: dict[str, Any] | list[dict[str, Any]]
    status_code: int = 200

    def json(self) -> dict[str, Any] | list[dict[str, Any]]:
        return self.data

    @property
    def text(self) -> str:
        return json.dumps(self.data)


class MockHTTPxClient:
    """Imitate real http client but with mocked response"""

    def __init__(
        self,
        response: MockTestResponse | None = None,
        get_method: AsyncMock | None = None,
    ):
        if not any([response, get_method]):
            raise AssertionError("At least one of `response` or `get_method` must be specified")

        self.response = response
        self.get = get_method or AsyncMock(return_value=response)
        self.aclose = AsyncMock()
        super().__init__()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore
        pass
