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
