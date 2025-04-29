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
    AIModel,
)
from src.constants import DEFAULT_PROVIDER_TIMEOUT, Provider


class TestSystemInfo:
    """Tests for SystemInfo model."""

    def test_system_info_creation(self) -> None:
        """Test SystemInfo model creation."""
        info = SystemInfo(os_version="test-os")
        assert info.status == "ok"
        assert info.os_version == "test-os"
        assert info.providers == []

    def test_system_info_with_providers(self) -> None:
        """Test SystemInfo model with providers."""
        info = SystemInfo(os_version="test-os", providers=["test-provider"])
        assert info.providers == ["test-provider"]


class TestHealthCheck:
    """Tests for HealthCheck model."""

    def test_health_check_creation(self) -> None:
        """Test HealthCheck model creation."""
        check = HealthCheck(status="ok", timestamp=datetime.now())
        assert check.status == "ok"
        assert isinstance(check.timestamp, datetime)


class TestMessage:
    """Tests for Message model."""

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
        provider_params = request.get_provider_params()
        assert provider_params == {"temperature": 0.7, "max_tokens": 1000}


class TestLLMProvider:
    """Tests for LLMProvider model."""

    def test_llm_provider_creation(self) -> None:
        """Test LLMProvider model creation."""
        provider = LLMProvider(vendor=Provider.OPENAI, api_key=SecretStr("test-key"))
        assert provider.vendor == Provider.OPENAI
        assert provider.api_key.get_secret_value() == "test-key"
        assert provider.timeout == DEFAULT_PROVIDER_TIMEOUT

    def test_llm_provider_auth_headers(self) -> None:
        """Test LLMProvider auth headers."""
        provider = LLMProvider(vendor=Provider.OPENAI, api_key=SecretStr("test-key"))
        assert provider.auth_headers == {"Authorization": "Bearer test-key"}


class TestAIModel:
    """Tests for AIModel model."""

    @pytest.mark.parametrize(
        "model_id,model_type,expected",
        [
            ("gpt-4", "chat", True),
            ("text-davinci-003", "chat", True),
            ("claude-2", "chat", True),
            ("other-model", "chat", True),
            ("other-model", "other", False),
        ],
    )
    def test_is_chat_model(self, model_id: str, model_type: str, expected: bool) -> None:
        """Test AIModel is_chat_model property."""
        model = AIModel(id=model_id, name="Test Model", type=model_type, vendor="test")
        assert model.is_chat_model == expected
