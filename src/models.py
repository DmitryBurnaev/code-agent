from typing import Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, SecretStr

from src.constants import Provider, DEFAULT_PROVIDER_TIMEOUT, PROVIDER_URLS

__all__ = (
    "SystemInfo",
    "HealthCheck",
    "Message",
    "ChatRequest",
    "LLMProvider",
    "AIModel",
)


class SystemInfo(BaseModel):
    """Response model for system information endpoint."""

    status: str = "ok"
    providers: list[str] = Field(default_factory=list)


class HealthCheck(BaseModel):
    """Response model for health check endpoint."""

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
    """Base model for chat completion requests with required fields."""

    model_config = ConfigDict(
        extra="allow",  # Allow extra fields for provider-specific parameters
        json_schema_extra={
            "example": {
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Hello!"},
                ],
                "model": "gpt-4",
                "stream": True,
                "temperature": 0.7,  # Optional provider-specific field
                "max_tokens": 1000,  # Optional provider-specific field
            }
        },
    )

    messages: list[Message] = Field(
        description="The list of messages in the conversation",
        min_length=1,  # At least one message required
    )
    model: str = Field(
        description="The model to use for chat completion",
    )
    stream: bool = Field(
        default=False,
        description="Whether to stream the response",
    )

    def get_extra_params(self) -> dict[str, Any]:
        """
        Get provider-specific parameters that were passed in the request.
        Excludes the required fields.
        """
        required_fields = {"messages", "model", "stream"}

        return {k: v for k, v in self.model_dump().items() if k not in required_fields}


class LLMProvider(BaseModel):
    """Provider configuration with API keys."""

    vendor: Provider
    api_key: SecretStr
    auth_type: str = "Bearer"
    timeout: int = DEFAULT_PROVIDER_TIMEOUT

    @property
    def base_url(self) -> str:
        """Get base URL for provider."""
        return PROVIDER_URLS[self.vendor]

    @property
    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"{self.auth_type} {self.api_key.get_secret_value()}"}

    def __repr__(self) -> str:
        return f"LLMProvider(vendor={self.vendor}, api_key={self.api_key})"

    def __str__(self) -> str:
        return f"Provider {self.vendor}"


class AIModel(BaseModel):
    """Represents an AI model with provider-specific details."""

    id: str
    vendor: str
    vendor_id: str
