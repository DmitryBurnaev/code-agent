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

    def test_system_info_creation(self) -> None:
        info = SystemInfo()
        assert info.status == "ok"
        assert info.vendors == []

    def test_system_info_with_vendors(self) -> None:
        info = SystemInfo(vendors=["test-vendor"])
        assert info.vendors == ["test-vendor"]


class TestHealthCheck:

    def test_health_check_creation(self) -> None:
        check = HealthCheck(status="ok", timestamp=datetime.now())
        assert check.status == "ok"
        assert isinstance(check.timestamp, datetime)


class TestMessage:

    @pytest.mark.parametrize(
        "role,content",
        [
            ("user", "Hello!"),
            ("assistant", "Hi there!"),
            ("system", "You are a helpful assistant."),
        ],
    )
    def test_message_creation(self, role: str, content: str) -> None:
        message = Message(role=role, content=content)
        assert message.role == role
        assert message.content == content


class TestChatRequest:

    def test_chat_request_creation(self) -> None:
        messages = [Message(role="user", content="Hello!")]
        request = ChatRequest(messages=messages, model="test-model")
        assert request.messages == messages
        assert request.model == "test-model"
        assert request.stream is False

    def test_chat_request_with_vendor_params(self) -> None:
        messages = [Message(role="user", content="Hello!")]
        request = ChatRequest(
            messages=messages,
            model="test-model",
            **{"temperature": 0.7, "max_tokens": 1000},  # type: ignore
        )
        vendor_params = request.get_extra_params()
        assert vendor_params == {"temperature": 0.7, "max_tokens": 1000}


class TestLLMVendor:

    def test_llm_vendor_creation(self) -> None:
        vendor = LLMVendor(slug=VendorSlug.OPENAI, api_key=SecretStr("test-key"))
        assert vendor.slug == VendorSlug.OPENAI
        assert vendor.api_key.get_secret_value() == "test-key"
        assert vendor.timeout == VENDOR_DEFAULT_TIMEOUT

    def test_llm_vendor_auth_headers(self) -> None:
        vendor = LLMVendor(slug=VendorSlug.OPENAI, api_key=SecretStr("test-key"))
        assert vendor.auth_headers == {"Authorization": "Bearer test-key"}
