from typing import Any, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field, SecretStr

from src.constants import Vendor, VENDOR_DEFAULT_TIMEOUT, PROVIDER_URLS

__all__ = (
    "SystemInfo",
    "HealthCheck",
    "Message",
    "ChatRequest",
    "LLMProvider",
    "AIModel",
    "ErrorResponse",
    "ModelListResponse",
    "ChatMessage",
    "ChatCompletionResponse",
    "ChatCompletionStreamResponse",
    "CancelCompletionResponse",
)


class SystemInfo(BaseModel):
    """System information response model."""

    status: str = "ok"
    providers: list[str] = Field(default_factory=list)


class HealthCheck(BaseModel):
    """Health check response model."""

    status: str
    timestamp: datetime


class Message(BaseModel):
    """Single message in the chat history."""

    role: str = Field(
        ...,
        description="The role of the message sender (e.g. 'user', 'assistant', 'system')",
    )
    content: str = Field(
        ...,
        description="The content of the message",
    )


class ChatRequest(BaseModel):
    """Chat completion request model."""

    model: str
    messages: list[Message]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    stop: list[str] | None = None

    def get_extra_params(self) -> dict[str, Any]:
        """Get extra parameters for the request."""
        return {
            k: v
            for k, v in self.model_dump().items()
            if k not in {"model", "messages", "stream"} and v is not None
        }


class LLMProvider(BaseModel):
    """Provider configuration with API keys."""

    vendor: Vendor
    api_key: SecretStr
    url: str | None = None
    auth_type: str = "Bearer"
    timeout: int = VENDOR_DEFAULT_TIMEOUT

    @property
    def base_url(self) -> str:
        """Get base URL for provider."""
        url = self.url or PROVIDER_URLS[self.vendor]
        if not url.endswith("/"):
            url += "/"

        return url

    @property
    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"{self.auth_type} {self.api_key.get_secret_value()}"}

    def __repr__(self) -> str:
        return f"LLMProvider(vendor={self.vendor}, api_key={self.api_key})"

    def __str__(self) -> str:
        return f"Provider {self.vendor}"


class AIModel(BaseModel):
    """AI model information."""

    id: str
    vendor: str
    vendor_id: str


class ErrorResponse(BaseModel):
    """Base error response model"""

    error: str
    detail: Optional[str] = None


class ModelListResponse(BaseModel):
    """Response model for list of available models."""

    data: list[AIModel]


class ChatMessage(BaseModel):
    """Chat message model."""

    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionChoice(BaseModel):
    """Chat completion choice model."""

    index: int
    message: ChatMessage
    finish_reason: str | None = None


class ChatCompletionChunkChoice(BaseModel):
    """Chat completion chunk choice model for streaming responses."""

    index: int
    delta: ChatMessage
    finish_reason: str | None = None


class ChatCompletionResponse(BaseModel):
    """Chat completion response model."""

    id: str
    model: str
    created: int
    choices: list[ChatCompletionChoice]
    usage: dict[str, int] | None = None


class ChatCompletionStreamResponse(BaseModel):
    """Chat completion chunk model for streaming responses."""

    id: str
    model: str
    created: int
    choices: list[ChatCompletionChunkChoice]


class CancelCompletionResponse(BaseModel):
    """Response model for chat completion cancellation."""

    id: str
    model: str
    cancelled: bool = True
    created: int = Field(default_factory=lambda: int(datetime.now().timestamp()))
