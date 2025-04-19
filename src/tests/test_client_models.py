import pytest
from pydantic import ValidationError

from src.models import ChatRequest, Message


def test_valid_minimal_chat_request():
    """Test minimal valid chat request with only required fields."""
    request = ChatRequest(
        messages=[{"role": "user", "content": "Hello"}],
        model="gpt-4",
        stream=False,
    )

    assert len(request.messages) == 1
    assert request.model == "gpt-4"
    assert request.stream is False
    assert request.get_provider_params() == {}


def test_valid_openai_chat_request():
    """Test valid OpenAI-style chat request with provider-specific fields."""
    request = ChatRequest(
        messages=[
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Hello!"},
        ],
        model="gpt-4",
        stream=True,
        temperature=0.7,
        max_tokens=1000,
        presence_penalty=0.5,
        frequency_penalty=0.5,
        top_p=0.9,
    )

    provider_params = request.get_provider_params()
    assert provider_params["temperature"] == 0.7
    assert provider_params["max_tokens"] == 1000
    assert provider_params["presence_penalty"] == 0.5
    assert provider_params["frequency_penalty"] == 0.5
    assert provider_params["top_p"] == 0.9


def test_valid_anthropic_chat_request():
    """Test valid Anthropic-style chat request with provider-specific fields."""
    request = ChatRequest(
        messages=[{"role": "user", "content": "Hello!"}],
        model="claude-3",
        stream=True,
        max_tokens_to_sample=1000,
        temperature=0.7,
        top_p=0.9,
        system="You are Claude, an AI assistant",
    )

    provider_params = request.get_provider_params()
    assert provider_params["max_tokens_to_sample"] == 1000
    assert provider_params["temperature"] == 0.7
    assert provider_params["top_p"] == 0.9
    assert provider_params["system"] == "You are Claude, an AI assistant"


@pytest.mark.parametrize(
    "invalid_data,expected_error",
    [
        # Отсутствуют обязательные поля
        (
            {"stream": True},
            "Field required",
        ),
        # Пустой список сообщений
        (
            {
                "messages": [],
                "model": "gpt-4",
                "stream": True,
            },
            "List should have at least 1 item",
        ),
        # Невалидная роль в сообщении
        (
            {
                "messages": [{"role": "", "content": "Hello"}],
                "model": "gpt-4",
                "stream": True,
            },
            "String should have at least 1 character",
        ),
        # Пустой контент в сообщении
        (
            {
                "messages": [{"role": "user", "content": ""}],
                "model": "gpt-4",
                "stream": True,
            },
            "String should have at least 1 character",
        ),
        # Отсутствует поле role в сообщении
        (
            {
                "messages": [{"content": "Hello"}],
                "model": "gpt-4",
                "stream": True,
            },
            "Field required",
        ),
        # Отсутствует поле content в сообщении
        (
            {
                "messages": [{"role": "user"}],
                "model": "gpt-4",
                "stream": True,
            },
            "Field required",
        ),
        # Пустая модель
        (
            {
                "messages": [{"role": "user", "content": "Hello"}],
                "model": "",
                "stream": True,
            },
            "String should have at least 1 character",
        ),
    ],
)
def test_invalid_chat_requests(invalid_data, expected_error):
    """Test various invalid chat request scenarios."""
    with pytest.raises(ValidationError) as exc_info:
        ChatRequest(**invalid_data)

    assert expected_error in str(exc_info.value)


def test_message_role_validation():
    """Test message role field validation."""
    message = Message(role="user", content="Hello")
    assert message.role == "user"

    message = Message(role="assistant", content="Hi!")
    assert message.role == "assistant"

    message = Message(role="system", content="You are an AI")
    assert message.role == "system"

    with pytest.raises(ValidationError) as exc_info:
        Message(role="", content="Invalid role")
    assert "String should have at least 1 character" in str(exc_info.value)


def test_provider_params_extraction():
    """Test extraction of provider-specific parameters."""
    request = ChatRequest(
        messages=[{"role": "user", "content": "Hello"}],
        model="gpt-4",
        stream=True,
        # Provider-specific params
        temperature=0.7,
        custom_param="test",
        another_param=123,
    )

    params = request.get_provider_params()
    assert params == {
        "temperature": 0.7,
        "custom_param": "test",
        "another_param": 123,
    }
    assert "messages" not in params
    assert "model" not in params
    assert "stream" not in params
