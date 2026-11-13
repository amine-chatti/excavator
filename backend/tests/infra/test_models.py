from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from sqlite3 import Connection
from typing import cast

import pytest
from sqlalchemy import Table, create_engine, delete, event, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from excavator.infra.db.base import Base
from excavator.infra.db.models import Commit, Repository


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

    assert table_names == {"repositories", "commits"}


def test_naive_repository_datetime_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        session.add(
            Repository(owner="octocat", name="hello-world", created_at=datetime(2026, 1, 1))
        )

        with pytest.raises(StatementError, match="UTCDateTime requires an aware datetime"):
            session.commit()


def test_naive_commit_datetime_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        commit = _commit(repository.id)
        commit.authored_at = datetime(2026, 1, 1)
        session.add(commit)

        with pytest.raises(StatementError, match="UTCDateTime requires an aware datetime"):
            session.commit()


def test_aware_non_utc_datetimes_round_trip_as_utc(engine: Engine) -> None:
    authored_at = datetime(2026, 1, 1, 12, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    created_at = datetime(2026, 1, 1, 13, tzinfo=timezone(timedelta(hours=5, minutes=30)))

    with Session(engine) as session:
        repository = _repository()
        repository.created_at = created_at
        session.add(repository)
        session.flush()
        commit = _commit(repository.id)
        commit.authored_at = authored_at
        session.add(commit)
        session.commit()
        session.refresh(repository)
        session.refresh(commit)

        assert repository.created_at == created_at.astimezone(UTC)
        assert repository.created_at.tzinfo is UTC
        assert commit.authored_at == authored_at.astimezone(UTC)
        assert commit.authored_at.tzinfo is UTC


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


def test_invalid_sha_length_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        commit = _commit(repository.id)
        commit.sha = "a" * 39
        session.add(commit)

        with pytest.raises(IntegrityError):
            session.commit()


def test_unknown_repository_id_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        session.add(_commit(repository_id=999))

        with pytest.raises(IntegrityError):
            session.commit()


def test_deleting_repository_cascades_to_commits(engine: Engine) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        session.add(_commit(repository.id))
        session.commit()

        session.execute(delete(Repository).where(Repository.id == repository.id))
        session.commit()

        assert session.execute(select(Commit)).scalars().all() == []


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
        "pk_repositories",
        "uq_repositories_owner_name",
        "ck_repositories_indexing_status_values",
    }
    assert commit_constraints == {
        "pk_commits",
        "uq_commits_repository_id_sha",
        "ck_commits_sha_length",
        "fk_commits_repository_id_repositories",
    }
    assert commit_indexes == set()
