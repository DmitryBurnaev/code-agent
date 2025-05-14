#!/usr/bin/env python3
"""
CLI for interacting with AI models (DeepSeek/OpenAI compatible API)

Requires the DEEPSEEK_API_TOKEN environment variable or --token argument for authorization.
"""
import argparse
import httpx
import json
import os
import sys
from typing import Any, Dict, Optional, ContextManager

from src.constants import PROVIDER_URLS, Provider


def call_ai_model(
    vendor: str = "deepseek",
    model_name: str = "deepseek-chat",
    stream: bool = False,
    prompt: str = "Hello!",
    token: str = "",
) -> Optional[httpx.Response | ContextManager[httpx.Response]]:
    """
    Sends a request to the AI model. In stream mode, returns a context manager for httpx.Response.
    """
    if not token:
        print("[ERROR] Authorization token is not set (use --token or environment variable)")
        sys.exit(1)

    try:
        provider_enum = Provider[vendor.upper()]
    except KeyError:
        print(f"[ERROR] Unknown vendor: {vendor}. Supported: {[p.value for p in Provider]}")
        sys.exit(1)

    url = PROVIDER_URLS[provider_enum] + "/chat/completions"
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


def extract_text_from_response(data: Dict[str, Any]) -> str:
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
        for line in r.iter_lines():
            if not line:
                continue
            if isinstance(line, bytes):
                line = line.decode("utf-8")
            if line.startswith("data:"):
                line = line[len("data:") :].strip()
            if not line or line == "[DONE]":
                continue
            try:
                data = json.loads(line)
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


def main() -> None:
    """
    Main function for CLI.
    """
    parser = argparse.ArgumentParser(
        description="CLI for interacting with AI models (DeepSeek/OpenAI compatible API)"
    )
    parser.add_argument("--vendor", default="deepseek", help="AI provider (deepseek, ...)")
    parser.add_argument("--model", default="deepseek-chat", help="Model name (e.g. deepseek-chat)")
    parser.add_argument(
        "--token", default=None, help="Authorization token (or environment variable)"
    )
    parser.add_argument("--stream", action="store_true", help="Stream mode")
    parser.add_argument("--prompt", default="Hello!", help="Prompt text")
    args = parser.parse_args()

    token = args.token or os.environ.get("AI_API_TOKEN", "")
    response = call_ai_model(
        vendor=args.vendor,
        model_name=args.model,
        stream=args.stream,
        prompt=args.prompt,
        token=token,
    )
    if response and not args.stream:
        process_full_response(response)  # type: ignore
    elif response and args.stream:
        process_stream_response(response)  # type: ignore
    else:
        print("Error: Invalid request mode")


if __name__ == "__main__":
    main()
