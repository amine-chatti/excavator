from __future__ import annotations

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from excavator.core.symbols import ParseStatus, SymbolKind
from excavator.infra.db.models import Commit, Repository, Symbol, SymbolVersion


def _repository_and_commit(session: Session) -> tuple[Repository, Commit]:
    repository = Repository(owner="enum-test", name="repo")
    session.add(repository)
    session.flush()
    commit = Commit(
        repository_id=repository.id,
        sha="b" * 40,
        message="test",
        author_login="tester",
        authored_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        parent_shas=[],
        url="https://example.test/commit/" + "b" * 40,
    )
    session.add(commit)
    session.flush()
    return repository, commit


@pytest.mark.parametrize("kind", list(SymbolKind))
def test_symbol_kind_values_insert(engine: Engine, kind: SymbolKind) -> None:
    with Session(engine) as session:
        repository, _ = _repository_and_commit(session)
        session.add(
            Symbol(
                repository_id=repository.id,
                language="python",
                kind=kind.value,
                qualified_name="f",
                status="exists",
            )
        )
        session.commit()


@pytest.mark.parametrize("status", list(ParseStatus))
def test_parse_status_values_insert(engine: Engine, status: ParseStatus) -> None:
    with Session(engine) as session:
        repository, commit = _repository_and_commit(session)
        symbol = Symbol(
            repository_id=repository.id,
            language="python",
            kind=SymbolKind.FUNCTION.value,
            qualified_name="f",
            status="exists",
        )
        session.add(symbol)
        session.flush()
        session.add(
            SymbolVersion(
                symbol_id=symbol.id,
                commit_id=commit.id,
                path="f.py",
                qualified_name="f",
                start_line=1,
                end_line=1,
                body_hash="a" * 64,
                parse_status=status.value,
                lineage_method="exact",
            )
        )
        session.commit()


def test_values_outside_enums_are_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        repository, _ = _repository_and_commit(session)
        session.add(
            Symbol(
                repository_id=repository.id,
                language="python",
                kind="not-a-kind",
                qualified_name="f",
                status="exists",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()

    with Session(engine) as session:
        repository, commit = _repository_and_commit(session)
        symbol = Symbol(
            repository_id=repository.id,
            language="python",
            kind=SymbolKind.FUNCTION.value,
            qualified_name="f",
            status="exists",
        )
        session.add(symbol)
        session.flush()
        session.add(
            SymbolVersion(
                symbol_id=symbol.id,
                commit_id=commit.id,
                path="f.py",
                qualified_name="f",
                parse_status="not-a-status",
                lineage_method="exact",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
