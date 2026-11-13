from __future__ import annotations

import pytest
import structlog
from pydantic import SecretStr

from excavator.config import Settings
from excavator.logging import _redact_sensitive_values, configure_logging


def test_structlog_output_redacts_secret(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(Settings(LOG_LEVEL="INFO"))
    logger = structlog.get_logger("test")
    logger.info("token_event", github_token=SecretStr("super-secret-token"))

    captured = capsys.readouterr()
    assert "super-secret-token" not in captured.err
    assert "**********" in captured.err


def test_redaction_handles_none_and_non_sensitive_values() -> None:
    event_dict = {
        "authorization": None,
        "password": "secret",
        "safe_value": 42,
    }

    redacted = _redact_sensitive_values(None, "info", event_dict)

    assert redacted == {
        "authorization": None,
        "password": "**********",
        "safe_value": 42,
    }


def test_redaction_handles_non_string_sensitive_values() -> None:
    event_dict = {"password": 42}

    redacted = _redact_sensitive_values(None, "info", event_dict)

    assert redacted == event_dict
