from __future__ import annotations

import pytest
from pydantic import SecretStr

from excavator.config import Settings


def test_settings_does_not_expose_github_token() -> None:
    settings = Settings(GITHUB_TOKEN=SecretStr("super-secret-token"))

    assert "super-secret-token" not in repr(settings)
    assert "super-secret-token" not in str(settings)
    assert "super-secret-token" not in settings.model_dump_json()


def test_github_token_defaults_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert Settings().GITHUB_TOKEN is None


def test_log_level_has_sensible_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    assert Settings().LOG_LEVEL == "INFO"


def test_explain_provider_and_ollama_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("EXPLAIN_PROVIDER", "OLLAMA_BASE_URL", "OLLAMA_MODEL"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings()

    assert settings.EXPLAIN_PROVIDER == "anthropic"
    assert settings.OLLAMA_BASE_URL == "http://localhost:11434"
    assert settings.OLLAMA_MODEL == "llama3.2:3b"


@pytest.mark.parametrize("provider", ["openai", "", "Anthropic"])
def test_settings_reject_invalid_explain_provider(provider: str) -> None:
    with pytest.raises(ValueError):
        Settings(EXPLAIN_PROVIDER=provider)  # type: ignore[arg-type]


@pytest.mark.parametrize("base_url", ["localhost:11434", "ftp://ollama.local"])
def test_settings_reject_ollama_base_url_without_http_scheme(base_url: str) -> None:
    with pytest.raises(ValueError, match="OLLAMA_BASE_URL"):
        Settings(OLLAMA_BASE_URL=base_url)
