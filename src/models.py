from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class SystemInfo(BaseModel):
    """Response model for system information endpoint."""

    status: str = "ok"
    os_version: str
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

    messages: List[Message] = Field(
        ...,
        description="The list of messages in the conversation",
        min_items=1,  # At least one message required
    )
    model: str = Field(
        ...,
        description="The model to use for chat completion",
    )
    stream: bool = Field(
        default=False,
        description="Whether to stream the response",
    )

    def get_provider_params(self) -> Dict[str, Any]:
        """
        Get provider-specific parameters that were passed in the request.
        Excludes the required fields.
        """
        required_fields = {"messages", "model", "stream"}

        return {k: v for k, v in self.model_dump().items() if k not in required_fields}
