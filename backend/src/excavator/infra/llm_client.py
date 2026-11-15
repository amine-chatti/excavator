from __future__ import annotations

from typing import Protocol

import httpx

LLM_API_TIMEOUT_SECONDS = 30
OLLAMA_API_TIMEOUT_SECONDS = 180
ANTHROPIC_VERSION = "2023-06-01"


class LLMClientError(Exception):
    """Raised when an LLM response cannot be used."""


class LLMRateLimitError(LLMClientError):
    """Raised when the LLM provider rate limits a request."""


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class AnthropicClient:
    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-5-5",
        base_url: str = "https://api.anthropic.com",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("Anthropic base URL must use HTTPS")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    def complete(self, system: str, user: str) -> str:
        try:
            with httpx.Client(
                transport=self._transport,
                timeout=LLM_API_TIMEOUT_SECONDS,
            ) as client:
                response = client.post(
                    f"{self._base_url}/v1/messages",
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": ANTHROPIC_VERSION,
                        "content-type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "max_tokens": 1000,
                        "system": system,
                        "messages": [{"role": "user", "content": user}],
                    },
                )
        except httpx.TimeoutException as exc:
            raise LLMClientError("LLM request timed out") from exc
        except httpx.RequestError as exc:
            raise LLMClientError("LLM request failed") from exc
        if response.status_code == 429:
            raise LLMRateLimitError("LLM rate limit exceeded (status 429)")
        if response.status_code >= 400:
            raise LLMClientError(f"LLM request failed (status {response.status_code})")
        try:
            payload = response.json()
        except (ValueError, TypeError) as exc:
            raise LLMClientError("LLM returned a malformed response") from exc
        if not isinstance(payload, dict):
            raise LLMClientError("LLM returned a malformed response")
        content = payload.get("content")
        if not isinstance(content, list):
            raise LLMClientError("LLM returned a malformed response")
        text_blocks: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                raise LLMClientError("LLM returned a malformed response")
            block_type = block.get("type")
            if not isinstance(block_type, str):
                raise LLMClientError("LLM returned a malformed response")
            if block_type == "text":
                text = block.get("text")
                if not isinstance(text, str):
                    raise LLMClientError("LLM returned a malformed response")
                text_blocks.append(text)
        if not text_blocks:
            raise LLMClientError("LLM returned a malformed response")
        return "".join(text_blocks)


class OllamaClient:
    def __init__(
        self,
        model: str = "llama3.2:3b",
        base_url: str = "http://localhost:11434",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    def complete(self, system: str, user: str) -> str:
        try:
            with httpx.Client(
                transport=self._transport,
                timeout=OLLAMA_API_TIMEOUT_SECONDS,
            ) as client:
                response = client.post(
                    f"{self._base_url}/api/chat",
                    json={
                        "model": self._model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "stream": False,
                        "format": "json",
                    },
                )
        except httpx.TimeoutException as exc:
            raise LLMClientError("LLM request timed out") from exc
        except httpx.RequestError as exc:
            raise LLMClientError("LLM request failed") from exc
        if response.status_code != 200:
            raise LLMClientError(f"LLM request failed (status {response.status_code})")
        if response.headers.get("content-type", "").split(";")[0].strip().lower() != (
            "application/json"
        ):
            raise LLMClientError("LLM returned a malformed response")
        try:
            payload = response.json()
        except (ValueError, TypeError) as exc:
            raise LLMClientError("LLM returned a malformed response") from exc
        if not isinstance(payload, dict):
            raise LLMClientError("LLM returned a malformed response")
        message = payload.get("message")
        if not isinstance(message, dict):
            raise LLMClientError("LLM returned a malformed response")
        content = message.get("content")
        if not isinstance(content, str):
            raise LLMClientError("LLM returned a malformed response")
        return content
