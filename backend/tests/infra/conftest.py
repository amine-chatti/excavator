from __future__ import annotations

from collections.abc import Iterator
from sqlite3 import Connection

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from excavator.infra.db.base import Base


@pytest.fixture
def engine() -> Iterator[Engine]:
    test_engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(test_engine, "connect")
    def enable_sqlite_foreign_keys(
        dbapi_connection: Connection,
        _: object,
    ) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()
