from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from typing import Final

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from excavator.infra.db.base import Base
from excavator.infra.db.session import (
    create_db_engine,
    create_session_factory,
    session_scope,
)

BACKEND_ROOT: Final[Path] = Path(__file__).parents[2]


def _offline_sql() -> str:
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=BACKEND_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def test_offline_migration_contains_every_model_table() -> None:
    sql = _offline_sql()

    for table in Base.metadata.tables.values():
        assert table.name is not None
        assert f"CREATE TABLE {table.name}" in sql


def test_offline_migration_contains_every_unique_and_foreign_key() -> None:
    sql = _offline_sql()

    for table in Base.metadata.tables.values():
        for constraint in table.constraints:
            name = constraint.name
            if isinstance(name, str) and (
                constraint.__class__.__name__ in {"UniqueConstraint", "ForeignKeyConstraint"}
            ):
                assert name in sql


def test_offline_migration_contains_every_model_index() -> None:
    sql = _offline_sql()

    for table in Base.metadata.tables.values():
        for index in table.indexes:
            assert index.name is not None
            assert index.name in sql


def test_baseline_migration_has_a_working_offline_downgrade() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "head:base", "--sql"],
        cwd=BACKEND_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    for table in Base.metadata.tables.values():
        assert table.name is not None
        assert f"DROP TABLE {table.name}" in completed.stdout


def test_baseline_migration_is_the_single_head() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["0001_baseline"]


def test_create_db_engine_uses_supplied_url() -> None:
    engine = create_db_engine("sqlite+pysqlite:///:memory:")

    try:
        assert engine.url.drivername == "sqlite+pysqlite"
        database = engine.url.database
        assert database is not None
        assert database == ":memory:"
    finally:
        engine.dispose()


def test_create_db_engine_uses_settings_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")

    engine = create_db_engine()

    try:
        assert engine.url.drivername == "sqlite+pysqlite"
    finally:
        engine.dispose()


def test_create_session_factory_uses_supplied_engine() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    try:
        factory = create_session_factory(engine)
        with factory() as session:
            assert session.bind is engine
    finally:
        engine.dispose()


def test_session_scope_commits_and_closes() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    events: list[str] = []

    class TrackingSession(Session):
        def commit(self) -> None:
            events.append("commit")
            super().commit()

        def close(self) -> None:
            events.append("close")
            super().close()

    factory = sessionmaker(bind=engine, class_=TrackingSession)
    with session_scope(factory):
        pass

    assert events == ["commit", "close"]
    engine.dispose()


def test_session_scope_rolls_back_and_closes() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    events: list[str] = []

    class TrackingSession(Session):
        def rollback(self) -> None:
            events.append("rollback")
            super().rollback()

        def close(self) -> None:
            events.append("close")
            super().close()

    factory = sessionmaker(bind=engine, class_=TrackingSession)
    with pytest.raises(RuntimeError, match="failure"), session_scope(factory):
        raise RuntimeError("failure")

    assert events == ["rollback", "close"]
    engine.dispose()


def test_importing_session_module_does_not_create_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import excavator.infra.db.session as session_module

    calls: list[object] = []
    monkeypatch.setattr(session_module, "create_engine", lambda *args, **kwargs: calls.append(args))

    importlib.reload(session_module)

    assert calls == []


def test_sqlite_models_are_compatible_with_session_scope() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session)

    with session_scope(factory) as session:
        assert session.bind is not None
        assert session.bind is engine

    engine.dispose()
