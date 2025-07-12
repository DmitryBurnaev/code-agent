"""Tests for models."""

import pytest
from datetime import datetime
from pydantic import SecretStr

from src.models import (
    SystemInfo,
    HealthCheck,
    Message,
    ChatRequest,
    LLMVendor,
)
from src.constants import VENDOR_DEFAULT_TIMEOUT, VendorSlug


class TestSystemInfo:
    """Tests for SystemInfo model."""

    def test_system_info_creation(self) -> None:
        """Test SystemInfo model creation."""
        info = SystemInfo()
        assert info.status == "ok"
        assert info.vendors == []

    def test_system_info_with_vendors(self) -> None:
        """Test SystemInfo model with vendors."""
        info = SystemInfo(vendors=["test-vendor"])
        assert info.vendors == ["test-vendor"]


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

    def test_chat_request_with_vendor_params(self) -> None:
        """Test ChatRequest model with vendor-specific parameters."""
        messages = [Message(role="user", content="Hello!")]
        request = ChatRequest(
            messages=messages,
            model="test-model",
            **{"temperature": 0.7, "max_tokens": 1000},  # type: ignore
        )
        vendor_params = request.get_extra_params()
        assert vendor_params == {"temperature": 0.7, "max_tokens": 1000}


class TestLLMVendor:
    """Tests for LLMVendor model."""

    def test_llm_vendor_creation(self) -> None:
        """Test LLMVendor model creation."""
        vendor = LLMVendor(slug=VendorSlug.OPENAI, api_key=SecretStr("test-key"))
        assert vendor.slug == VendorSlug.OPENAI
        assert vendor.api_key.get_secret_value() == "test-key"
        assert vendor.timeout == VENDOR_DEFAULT_TIMEOUT

    def test_llm_vendor_auth_headers(self) -> None:
        """Test LLMVendor auth headers."""
        vendor = LLMVendor(slug=VendorSlug.OPENAI, api_key=SecretStr("test-key"))
        assert vendor.auth_headers == {"Authorization": "Bearer test-key"}
