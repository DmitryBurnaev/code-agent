"""
CLI for interacting with AI models (DeepSeek/OpenAI compatible API)

Requires the DEEPSEEK_API_TOKEN environment variable or --token argument for authorization.
"""

import argparse
import httpx
import json
import os
import sys
from typing import Any, Optional, ContextManager


DEFAULT_VENDOR_URL = "https://api.deepseek.com/v1"
DEFAULT_VENDOR = "deepseek"
DEFAULT_MODEL = "deepseek-chat"
PROVIDER_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "custom": "https://custom-provider/v1",
}


def call_ai_model(
    vendor_url: str = DEFAULT_VENDOR_URL,
    model_name: str = DEFAULT_MODEL,
    stream: bool = False,
    prompt: str = "Hello!",
    token: str = "",
) -> Optional[httpx.Response | ContextManager[httpx.Response]]:
    """
    Sends a request to the AI model. In stream mode, returns a context manager for httpx.Response.
    """
    if not token:
        print("[error] Authorization token is not set (use --token or env 'AI_API_TOKEN')")
        sys.exit(1)

    url = vendor_url + "/chat/completions"
    print(f"Sending request to {url}")
    headers = {"Authorization": f"Bearer {token}"}
    data = {
        "max_tokens": 1000,
        "messages": [
            {"content": "You are a helpful assistant. Make response in russian", "role": "system"},
            {"content": prompt, "role": "user"},
        ],
        "model": model_name,
        "stream": stream,
        "temperature": 0.7,
    }
    try:
        if stream:
            client = httpx.Client(timeout=3600)
            # Return context manager for streaming
            return client.stream("POST", url, headers=headers, json=data)

        else:
            response = httpx.post(url, headers=headers, json=data, timeout=3600)
            response.raise_for_status()
            return response

    except Exception as exc:
        print(f"Error: {exc}")
        return None


def extract_text_from_response(data: dict[str, Any]) -> str:
    """
    Extracts text content from AI model response (DeepSeek/OpenAI compatible format).
    """
    if "choices" in data:
        choices = data["choices"]
        if choices and "delta" in choices[0]:
            return choices[0]["delta"].get("content", "") or ""

        elif choices and "message" in choices[0]:
            return choices[0]["message"].get("content", "") or ""

    return ""


def process_stream_response(response_cm: ContextManager[httpx.Response]) -> str:
    """
    Processes streaming response (context manager) and returns concatenated text.
    """
    result = []
    with response_cm as r:
        for index, line in enumerate(r.iter_lines()):
            if not line:
                continue

            if isinstance(line, bytes):
                line = line.decode("utf-8")

            if line.startswith("data:"):
                line = line.removeprefix("data:").strip()

            if not line or line == "[DONE]":
                continue

            try:
                data = json.loads(line)
                if index == 0:
                    print_header(data)

                content = extract_text_from_response(data)
                if content:
                    print(content, end="", flush=True)  # Print chunk to CLI
                    result.append(content)

            except Exception as e:
                print(f"\n[stream parse error]: {e}\n{line}")

    print()  # Newline after stream
    return "".join(result)


def process_full_response(response: httpx.Response) -> str:
    """
    Processes non-streaming response and returns concatenated text.
    """
    try:
        data = response.json()
        print_header(data)
        content = extract_text_from_response(data)
        if content:
            print(content)
            return content

        else:
            print("[no content found in response]")
            return ""

    except Exception as e:
        print(f"[parse error]: {e}\n{response.text}")
        return ""


def print_header(data: dict[str, Any]) -> None:
    print("==== AI response ====")
    print(f"[completion ID]: {data.get('id')}")
    print("====")


def main() -> None:
    """
    Main function for CLI.
    """
    parser = argparse.ArgumentParser(
        description="CLI for interacting with AI models (DeepSeek/OpenAI compatible API)"
    )
    parser.add_argument("--vendor", help="AI provider (deepseek, ...)")
    parser.add_argument("--vendor-url", help="AI provider URL (https://api.deepseek.com/v1, ...)")
    parser.add_argument("--model", default="deepseek-chat", help="Model name (e.g. deepseek-chat)")
    parser.add_argument(
        "--token", default=None, help="Authorization token (or environment variable)"
    )
    parser.add_argument("--stream", action="store_true", help="Stream mode")
    parser.add_argument("--prompt", default="Hello!", help="Prompt text")
    args = parser.parse_args()

    token = args.token or os.environ.get("CLI_AI_API_TOKEN", "")
    vendor_url = args.vendor_url or DEFAULT_VENDOR_URL
    vendor = args.vendor or DEFAULT_VENDOR
    if not vendor_url:
        if not vendor:
            print("[error] Either --vendor or --vendor-url must be provided")
            sys.exit(1)

        vendor_url = PROVIDER_URLS.get(vendor)
        if not vendor_url:
            print(f"[error] Unknown vendor: {vendor}")
            sys.exit(1)

    model_name = args.model or DEFAULT_MODEL

    response = call_ai_model(
        vendor_url=vendor_url,
        model_name=model_name,
        stream=args.stream,
        prompt=args.prompt,
        token=token,
    )
    if not response:
        print("[no response from AI model]")
        sys.exit(1)

    try:
        if isinstance(response, httpx.Response):
            process_full_response(response)
        else:
            process_stream_response(response)

    except Exception as exc:
        print(f"[processing error]: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("[interrupted]")
        sys.exit(1)
