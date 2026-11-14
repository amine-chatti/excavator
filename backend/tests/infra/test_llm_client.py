from __future__ import annotations

import json

import httpx
import pytest

from excavator.api.dependencies import get_llm_client
from excavator.config import Settings
from excavator.infra.llm_client import (
    ANTHROPIC_VERSION,
    LLM_API_TIMEOUT_SECONDS,
    AnthropicClient,
    LLMClientError,
    LLMRateLimitError,
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
    monkeypatch.setenv("ANTHROPIC_API_KEY", "configured-secret")
    monkeypatch.setenv("EXPLAIN_MODEL", "configured-model")

    client = get_llm_client()

    assert isinstance(client, AnthropicClient)
    assert client._api_key == "configured-secret"
    assert client._model == "configured-model"


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
