from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from sqlite3 import Connection
from typing import cast

import pytest
from sqlalchemy import Table, create_engine, event, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import ConnectionRecord

from excavator.infra.db.base import Base
from excavator.infra.db.models import Commit, Repository


@pytest.fixture
def engine() -> Iterator[Engine]:
    test_engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(test_engine, "connect")
    def enable_sqlite_foreign_keys(
        dbapi_connection: Connection,
        _: ConnectionRecord,
    ) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


def _repository(owner: str = "octocat", name: str = "hello-world") -> Repository:
    return Repository(owner=owner, name=name)


def _commit(repository_id: int, message: str = "Initial commit") -> Commit:
    return Commit(
        repository_id=repository_id,
        sha="a" * 40,
        message=message,
        author_login="octocat",
        authored_at=datetime(2026, 1, 1, tzinfo=UTC),
        parent_shas=[],
        url="https://github.com/octocat/hello-world/commit/" + "a" * 40,
    )


def test_tables_create_successfully_on_sqlite(engine: Engine) -> None:
    table_names = set(inspect(engine).get_table_names())

    assert table_names == {"repository", "commit"}


def test_duplicate_repository_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        session.add_all([_repository(), _repository()])

        with pytest.raises(IntegrityError):
            session.commit()


def test_duplicate_commit_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        session.add_all([_commit(repository.id), _commit(repository.id)])

        with pytest.raises(IntegrityError):
            session.commit()


def test_invalid_indexing_status_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        session.add(Repository(owner="octocat", name="hello-world", indexing_status="invalid"))

        with pytest.raises(IntegrityError):
            session.commit()


def test_commit_message_round_trips_verbatim(engine: Engine) -> None:
    message = "Fix unicode: café\n\nTrailing whitespace   \n\t"

    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        session.add(_commit(repository.id, message=message))
        session.commit()
        stored_message = session.execute(select(Commit.message)).scalar_one()

    assert stored_message == message


def test_constraint_names_follow_metadata_convention() -> None:
    repository_table = cast(Table, Repository.__table__)
    commit_table = cast(Table, Commit.__table__)
    repository_constraints = {constraint.name for constraint in repository_table.constraints}
    commit_constraints = {constraint.name for constraint in commit_table.constraints}
    commit_indexes = {index.name for index in commit_table.indexes}

    assert repository_constraints == {
        "pk_repository",
        "uq_repository_owner",
        "ck_repository_indexing_status_values",
    }
    assert commit_constraints == {
        "pk_commit",
        "uq_commit_repository_id",
        "fk_commit_repository_id_repository",
    }
    assert commit_indexes == {"ix_commit_repository_id"}
