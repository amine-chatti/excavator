from __future__ import annotations

import os
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from excavator.infra.analysis_service import analyze_file
from excavator.infra.db.models import Repository, Symbol, SymbolVersion

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _git(repo: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
    )
    return completed.stdout


def _repository(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Postgres Integration Tests")
    _git(repo, "config", "user.email", "postgres@example.invalid")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "core.autocrlf", "false")
    hooks = repo / "hooks"
    hooks.mkdir()
    _git(repo, "config", "core.hooksPath", str(hooks))
    _git(repo, "branch", "-M", "main")
    return repo


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def _run_alembic(database_url: str, schema: str, *arguments: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    environment["PGOPTIONS"] = f"-c search_path={schema}"
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, (
        f"Alembic {' '.join(arguments)} failed:\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )


def _cleanup_schema(
    database_url: str,
    schema: str,
    admin_engine: Engine,
    application_engine: Engine | None,
) -> None:
    cleanup_error: BaseException | None = None
    try:
        _run_alembic(database_url, schema, "downgrade", "base")
        with admin_engine.connect() as connection:
            remaining_tables = (
                connection.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = :schema AND table_name <> 'alembic_version'"
                    ),
                    {"schema": schema},
                )
                .scalars()
                .all()
            )
        assert not remaining_tables, f"Tables remain after downgrade: {remaining_tables}"
    except BaseException as error:
        cleanup_error = error
    finally:
        try:
            with admin_engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        except BaseException as error:
            if cleanup_error is None:
                cleanup_error = error
        finally:
            if application_engine is not None:
                try:
                    application_engine.dispose()
                except BaseException as error:
                    if cleanup_error is None:
                        cleanup_error = error
            try:
                admin_engine.dispose()
            except BaseException as error:
                if cleanup_error is None:
                    cleanup_error = error
    if cleanup_error is not None:
        raise cleanup_error


@pytest.mark.postgres
def test_postgres_migrations_and_analysis(tmp_path: Path) -> None:
    database_url = os.environ.get("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_URL is not set")

    schema = f"excavator_test_{uuid4().hex}"
    admin_engine = create_engine(database_url)
    application_engine = None
    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))

        _run_alembic(database_url, schema, "upgrade", "head")

        application_engine = create_engine(database_url)
        repo = _repository(tmp_path)
        (repo / "old.py").write_bytes(b"def keep():\n    return 1\n\ndef remove():\n    return 2\n")
        _commit(repo, "initial")
        (repo / "old.py").write_bytes(b"def keep():\n    return 3\n\ndef remove():\n    return 2\n")
        (repo / "old.py").rename(repo / "new.py")
        _commit(repo, "rename")
        (repo / "new.py").write_bytes(b"def keep():\n    return 3\n")
        _commit(repo, "remove")

        with application_engine.connect() as connection:
            connection.execute(text(f'SET search_path TO "{schema}"'))
            connection.commit()
            with Session(bind=connection) as session:
                repository = Repository(owner="owner", name="repo")
                session.add(repository)
                session.flush()

                first = analyze_file(session, repository.id, repo, "new.py")
                session.commit()
                first_symbols = session.scalars(select(Symbol).order_by(Symbol.id)).all()
                first_versions = session.scalars(select(SymbolVersion)).all()

                second = analyze_file(session, repository.id, repo, "new.py")
                session.commit()
                second_symbols = session.scalars(select(Symbol).order_by(Symbol.id)).all()
                second_versions = session.scalars(select(SymbolVersion)).all()

        assert first.lineage_count == 2
        assert len(first_symbols) == 2
        assert len(first_versions) == 4
        assert first.symbol_ids == second.symbol_ids
        assert [symbol.id for symbol in first_symbols] == [symbol.id for symbol in second_symbols]
        assert len(second_versions) == len(first_versions)
    except BaseException:
        with suppress(BaseException):
            _cleanup_schema(database_url, schema, admin_engine, application_engine)
        raise
    else:
        _cleanup_schema(database_url, schema, admin_engine, application_engine)
