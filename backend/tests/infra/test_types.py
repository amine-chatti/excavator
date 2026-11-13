from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import cast

from sqlalchemy.engine import Dialect

from excavator.infra.db.types import UTCDateTime


def test_utc_datetime_bind_none() -> None:
    assert UTCDateTime().process_bind_param(None, cast(Dialect, None)) is None


def test_utc_datetime_result_none() -> None:
    assert UTCDateTime().process_result_value(None, cast(Dialect, None)) is None


def test_utc_datetime_result_preserves_aware_datetime() -> None:
    value = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=2)))

    assert UTCDateTime().process_result_value(value, cast(Dialect, None)) is value


def test_utc_datetime_result_preserves_utc_datetime() -> None:
    value = datetime(2026, 1, 1, tzinfo=UTC)

    assert UTCDateTime().process_result_value(value, cast(Dialect, None)) is value
