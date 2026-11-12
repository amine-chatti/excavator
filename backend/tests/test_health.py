from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import SecretStr

from excavator.api.main import create_app
from excavator.config import Settings
from excavator.logging import _redact_sensitive_values


def test_health_route() -> None:
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_does_not_expose_token() -> None:
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://excavator:excavator@localhost:5432/excavator",
        GITHUB_TOKEN=SecretStr("super-secret-token"),
        LOG_LEVEL="INFO",
    )

    rendered = repr(settings)
    text = str(settings)

    assert "super-secret-token" not in rendered
    assert "super-secret-token" not in text
    assert "**********" in rendered
    assert "**********" in text


def test_logging_redacts_secret() -> None:
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://excavator:excavator@localhost:5432/excavator",
        GITHUB_TOKEN=SecretStr("super-secret-token"),
        LOG_LEVEL="INFO",
    )

    redacted = _redact_sensitive_values("logger", "info", {"github_token": settings.GITHUB_TOKEN})

    assert redacted["github_token"] == "**********"
    assert "super-secret-token" not in str(redacted)
    assert "SecretStr" not in str(redacted)
