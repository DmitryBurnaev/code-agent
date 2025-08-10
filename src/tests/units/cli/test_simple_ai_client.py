from typing import Any, Iterator, Optional
from src.cli import simple_ai_client

# Mock response for non-streaming mode
default_json_type = dict[str, Any]


class MockResponse:
    def __init__(self, json_data: default_json_type, is_success: bool = True) -> None:
        self._json = json_data
        self.text: str = str(json_data)
        self.is_success = is_success

    def json(self) -> default_json_type:
        return self._json


# Mock response for streaming mode
class MockStreamResponse:
    def __init__(self, lines: list[bytes], is_success: bool = True) -> None:
        self._lines = lines
        self.is_success = is_success

    def __enter__(self) -> "MockStreamResponse":
        return self

    def __exit__(
        self, exc_type: Optional[type[BaseException]], exc_val: Optional[BaseException], exc_tb: Any
    ) -> None:
        pass

    def iter_lines(self) -> Iterator[bytes]:
        for line in self._lines:
            yield line


def test_extract_text_from_response_stream() -> None:
    data = {"choices": [{"delta": {"content": "Привет, "}}]}
    assert simple_ai_client.extract_text_from_response(data) == "Привет, "


def test_extract_text_from_response_full() -> None:
    data = {"choices": [{"message": {"content": "Полный ответ."}}]}
    assert simple_ai_client.extract_text_from_response(data) == "Полный ответ."


def test_process_full_response_prints_content(capsys: Any) -> None:
    resp = MockResponse({"choices": [{"message": {"content": "Answer!"}}]})
    out = simple_ai_client.process_full_response(resp)  # type: ignore
    captured = capsys.readouterr()
    assert "Answer!" in captured.out
    assert out == "Answer!"


def test_process_stream_response_prints_content(capsys: Any) -> None:
    # Mock SSE chunks
    lines = [
        b'data: {"choices": [{"delta": {"content": "chunk1 "}}]}',
        b'data: {"choices": [{"delta": {"content": "chunk2!"}}]}',
        b"data: [DONE]",
    ]
    resp = MockStreamResponse(lines)
    out = simple_ai_client.process_stream_response(resp)  # type: ignore
    captured = capsys.readouterr()
    assert "chunk1 chunk2!" in captured.out
    assert out == "chunk1 chunk2!"
