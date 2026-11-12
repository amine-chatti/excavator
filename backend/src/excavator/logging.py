from __future__ import annotations

import logging
from collections.abc import MutableMapping
from typing import Any, cast

import structlog
from pydantic import SecretStr

from excavator.config import Settings


def _redact_sensitive_values(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    redacted = dict(event_dict)
    for key, value in event_dict.items():
        lowercase_key = key.lower()
        if lowercase_key.endswith("token") or lowercase_key in {
            "authorization",
            "password",
            "secret",
        }:
            if value is None:
                redacted[key] = None
            elif isinstance(value, (SecretStr, str)):
                redacted[key] = "**********"
    return redacted


def configure_logging(settings: Settings) -> None:
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(level=log_level, force=True)
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
            _redact_sensitive_values,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    logger = structlog.get_logger(name)
    return cast(structlog.BoundLogger, logger)
