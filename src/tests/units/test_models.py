"""Tests for models."""

import pytest
from datetime import datetime
from pydantic import SecretStr

from src.models import (
    SystemInfo,
    HealthCheck,
    Message,
    ChatRequest,
    LLMProvider,
)
from src.constants import VENDOR_DEFAULT_TIMEOUT, Vendor


class TestSystemInfo:
    """Tests for SystemInfo model."""

    def test_system_info_creation(self) -> None:
        """Test SystemInfo model creation."""
        info = SystemInfo()
        assert info.status == "ok"
        assert info.providers == []

    def test_system_info_with_providers(self) -> None:
        """Test SystemInfo model with providers."""
        info = SystemInfo(providers=["test-provider"])
        assert info.providers == ["test-provider"]


class TestHealthCheck:
    """Tests for HealthCheck model."""

    def test_health_check_creation(self) -> None:
        """Test HealthCheck model creation."""
        check = HealthCheck(status="ok", timestamp=datetime.now())
        assert check.status == "ok"
        assert isinstance(check.timestamp, datetime)


class TestMessage:
    """Tests for Message models."""

    @pytest.mark.parametrize(
        "role,content",
        [
            ("user", "Hello!"),
            ("assistant", "Hi there!"),
            ("system", "You are a helpful assistant."),
        ],
    )
    def test_message_creation(self, role: str, content: str) -> None:
        """Test Message model creation with different roles."""
        message = Message(role=role, content=content)
        assert message.role == role
        assert message.content == content


class TestChatRequest:
    """Tests for ChatRequest model."""

    def test_chat_request_creation(self) -> None:
        """Test ChatRequest model creation."""
        messages = [Message(role="user", content="Hello!")]
        request = ChatRequest(messages=messages, model="test-model")
        assert request.messages == messages
        assert request.model == "test-model"
        assert request.stream is False

    def test_chat_request_with_provider_params(self) -> None:
        """Test ChatRequest model with provider-specific parameters."""
        messages = [Message(role="user", content="Hello!")]
        request = ChatRequest(
            messages=messages,
            model="test-model",
            **{"temperature": 0.7, "max_tokens": 1000},  # type: ignore
        )
        provider_params = request.get_extra_params()
        assert provider_params == {"temperature": 0.7, "max_tokens": 1000}


class TestLLMProvider:
    """Tests for LLMProvider model."""

    def test_llm_provider_creation(self) -> None:
        """Test LLMProvider model creation."""
        provider = LLMProvider(vendor=Vendor.OPENAI, api_key=SecretStr("test-key"))
        assert provider.vendor == Vendor.OPENAI
        assert provider.api_key.get_secret_value() == "test-key"
        assert provider.timeout == VENDOR_DEFAULT_TIMEOUT

    def test_llm_provider_auth_headers(self) -> None:
        """Test LLMProvider auth headers."""
        provider = LLMProvider(vendor=Vendor.OPENAI, api_key=SecretStr("test-key"))
        assert provider.auth_headers == {"Authorization": "Bearer test-key"}
