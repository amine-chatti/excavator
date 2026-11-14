from __future__ import annotations

import json

import httpx
import pytest

from excavator.api.dependencies import get_llm_client
from excavator.config import Settings
from excavator.infra.llm_client import (
    ANTHROPIC_VERSION,
    LLM_API_TIMEOUT_SECONDS,
    OLLAMA_API_TIMEOUT_SECONDS,
    AnthropicClient,
    LLMClientError,
    LLMRateLimitError,
    OllamaClient,
)
from excavator.logging import _redact_sensitive_values


def test_anthropic_client_sends_key_in_header_and_concatenates_text() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "text", "text": "first "},
                    {"type": "tool_use", "id": "ignored"},
                    {"type": "text", "text": "second"},
                ]
            },
        )

    key = "sk-ant-secret-value"
    client = AnthropicClient(
        key,
        model="claude-test",
        base_url="https://anthropic.test",
        transport=httpx.MockTransport(handler),
    )

    assert client.complete("system prompt", "user prompt") == "first second"
    request = calls[0]
    assert request.url == "https://anthropic.test/v1/messages"
    assert request.headers["x-api-key"] == key
    assert request.headers["anthropic-version"] == ANTHROPIC_VERSION
    assert request.headers["content-type"] == "application/json"
    body = json.loads(request.content)
    assert body == {
        "model": "claude-test",
        "max_tokens": 1000,
        "system": "system prompt",
        "messages": [{"role": "user", "content": "user prompt"}],
    }
    assert LLM_API_TIMEOUT_SECONDS > 0


@pytest.mark.parametrize("status", [401, 500])
def test_http_errors_are_generic_and_do_not_expose_key(status: int) -> None:
    key = "sk-ant-secret-value"
    client = AnthropicClient(
        key,
        transport=httpx.MockTransport(lambda _request: httpx.Response(status, text=key)),
    )
    with pytest.raises(LLMClientError) as error:
        client.complete("system", "user")
    assert str(status) in str(error.value)
    assert key not in str(error.value)


def test_rate_limit_and_timeout_errors_do_not_expose_key() -> None:
    key = "sk-ant-secret-value"
    limited = AnthropicClient(
        key,
        transport=httpx.MockTransport(lambda _request: httpx.Response(429, text=key)),
    )
    with pytest.raises(LLMRateLimitError) as error:
        limited.complete("system", "user")
    assert "429" in str(error.value)
    assert key not in str(error.value)

    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(key)

    with pytest.raises(LLMClientError, match="timed out") as timeout_error:
        AnthropicClient(key, transport=httpx.MockTransport(timeout)).complete("s", "u")
    assert key not in str(timeout_error.value)


def test_transport_error_and_non_https_base_are_safe() -> None:
    key = "sk-ant-secret-value"

    def fail(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(key)

    with pytest.raises(LLMClientError, match="request failed") as error:
        AnthropicClient(key, transport=httpx.MockTransport(fail)).complete("s", "u")
    assert key not in str(error.value)
    with pytest.raises(ValueError, match="HTTPS"):
        AnthropicClient(key, base_url="http://unsafe.test")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"content": "bad"}),
        httpx.Response(200, json={"content": [None]}),
        httpx.Response(200, json={"content": [{}]}),
        httpx.Response(200, json={"content": [{"type": "text", "text": 4}]}),
        httpx.Response(200, json={"content": [{"type": "image"}]}),
    ],
)
def test_malformed_responses_raise_generic_error(response: httpx.Response) -> None:
    key = "sk-ant-secret-value"
    client = AnthropicClient(
        key,
        transport=httpx.MockTransport(lambda _request: response),
    )
    with pytest.raises(LLMClientError, match="malformed response") as error:
        client.complete("s", "u")
    assert key not in str(error.value)


def test_settings_have_optional_key_and_expected_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("EXPLAIN_MODEL", raising=False)
    settings = Settings()
    assert settings.ANTHROPIC_API_KEY is None
    assert settings.EXPLAIN_MODEL == "claude-sonnet-5-5"


def test_dependency_builds_client_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPLAIN_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "configured-secret")
    monkeypatch.setenv("EXPLAIN_MODEL", "configured-model")

    client = get_llm_client()

    assert isinstance(client, AnthropicClient)
    assert client._api_key == "configured-secret"
    assert client._model == "configured-model"


def test_dependency_builds_ollama_client_without_anthropic_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXPLAIN_PROVIDER", "ollama")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "configured-ollama-model")

    client = get_llm_client()

    assert isinstance(client, OllamaClient)
    assert client._base_url == "http://ollama.test:11434"
    assert client._model == "configured-ollama-model"


def test_ollama_client_sends_chat_request_and_parses_content() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"message": {"content": '{"summary":"ok"}'}})

    base_url = "http://ollama.internal"
    client = OllamaClient(
        model="llama-test",
        base_url=f"{base_url}/",
        transport=httpx.MockTransport(handler),
    )

    assert client.complete("system prompt", "user prompt") == '{"summary":"ok"}'
    request = calls[0]
    assert str(request.url) == f"{base_url}/api/chat"
    body = json.loads(request.content)
    assert body == {
        "model": "llama-test",
        "messages": [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "user prompt"},
        ],
        "stream": False,
        "format": "json",
    }
    assert OLLAMA_API_TIMEOUT_SECONDS == 180


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(
            200,
            content=b"private response body",
            headers={"content-type": "application/json"},
        ),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"message": None}),
        httpx.Response(200, json={"message": {}}),
        httpx.Response(200, json={"message": {"content": 42}}),
    ],
)
def test_ollama_malformed_responses_are_generic(response: httpx.Response) -> None:
    base_url = "http://ollama.internal"
    client = OllamaClient(
        base_url=base_url,
        transport=httpx.MockTransport(lambda _request: response),
    )

    with pytest.raises(LLMClientError, match="malformed response") as error:
        client.complete("system", "user")
    assert base_url not in str(error.value)
    assert "private response body" not in str(error.value)


def test_ollama_wrong_content_type_is_rejected_without_leaking_body() -> None:
    base_url = "http://ollama.internal"
    body = "private response body"
    client = OllamaClient(
        base_url=base_url,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, text=body, headers={"content-type": "text/plain"})
        ),
    )

    with pytest.raises(LLMClientError, match="malformed response") as error:
        client.complete("system", "user")
    assert base_url not in str(error.value)
    assert body not in str(error.value)


def test_ollama_non_200_status_is_generic() -> None:
    base_url = "http://ollama.internal"
    body = "private response body"
    client = OllamaClient(
        base_url=base_url,
        transport=httpx.MockTransport(lambda _request: httpx.Response(503, text=body)),
    )

    with pytest.raises(LLMClientError, match="status 503") as error:
        client.complete("system", "user")
    assert base_url not in str(error.value)
    assert body not in str(error.value)


@pytest.mark.parametrize(
    ("error_type", "message"),
    [
        (httpx.ConnectError, "request failed"),
        (httpx.ReadTimeout, "timed out"),
    ],
)
def test_ollama_request_errors_are_generic(
    error_type: type[httpx.RequestError],
    message: str,
) -> None:
    base_url = "http://ollama.internal"
    private_text = "private response body"

    def fail(request: httpx.Request) -> httpx.Response:
        raise error_type(f"{base_url} {private_text}", request=request)

    client = OllamaClient(
        base_url=base_url,
        transport=httpx.MockTransport(fail),
    )

    with pytest.raises(LLMClientError, match=message) as error:
        client.complete("system", "user")
    assert base_url not in str(error.value)
    assert private_text not in str(error.value)


def test_logging_redacts_anthropic_api_key_fields(caplog: pytest.LogCaptureFixture) -> None:
    secret = "sk-ant-log-secret"
    result = _redact_sensitive_values(
        None,
        "info",
        {"anthropic_api_key": secret, "api_key": secret, "message": "request"},
    )
    assert result["anthropic_api_key"] == "**********"
    assert result["api_key"] == "**********"
    assert secret not in str(result)
    assert secret not in caplog.text
