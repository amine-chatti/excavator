from __future__ import annotations

import pytest
import structlog
from pydantic import SecretStr

from excavator.config import Settings
from excavator.logging import configure_logging


def test_structlog_output_redacts_secret(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(Settings(LOG_LEVEL="INFO"))
    logger = structlog.get_logger("test")
    logger.info("token_event", github_token=SecretStr("super-secret-token"))

    captured = capsys.readouterr()
    assert "super-secret-token" not in captured.err
    assert "**********" in captured.err
