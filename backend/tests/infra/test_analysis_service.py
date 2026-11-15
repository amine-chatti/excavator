from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from excavator.infra.analysis_service import AnalysisSummary, UnsupportedLanguageError, analyze_file
from excavator.infra.db.models import Commit, FileChange, Repository, Symbol, SymbolVersion
from excavator.infra.git_history import GitHistoryError


def _git(repo: Path, *arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *arguments],
            check=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        pytest.fail(f"git is required for these tests: {exc}")
    return completed.stdout


def _repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Analysis Tests")
    _git(repo, "config", "user.email", "analysis@example.invalid")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "core.autocrlf", "false")
    hooks = repo / "hooks"
    hooks.mkdir()
    _git(repo, "config", "core.hooksPath", str(hooks))
    _git(repo, "branch", "-M", "main")
    return repo


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD").decode().strip()


def _write(repo: Path, path: str, content: bytes) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def _db_repository(session: Session) -> int:
    repository = Repository(owner="owner", name="repo")
    session.add(repository)
    session.flush()
    return repository.id


def test_analyze_file_persists_rename_and_removed_function(
    engine: Engine,
    tmp_path: Path,
) -> None:
    repo = _repository(tmp_path)
    _write(repo, "old.py", b"def keep():\n    return 1\n\ndef remove():\n    return 2\n")
    _commit(repo, "initial")
    _write(repo, "old.py", b"def keep():\n    return 3\n\ndef remove():\n    return 2\n")
    (repo / "old.py").rename(repo / "new.py")
    _commit(repo, "rename")
    _write(repo, "new.py", b"def keep():\n    return 3\n")
    _commit(repo, "remove")

    with Session(engine) as session:
        repository_id = _db_repository(session)
        summary = analyze_file(session, repository_id, repo, "new.py")
        session.commit()
        symbols = session.execute(select(Symbol).order_by(Symbol.id)).scalars().all()
        versions = session.execute(select(SymbolVersion).order_by(SymbolVersion.id)).scalars().all()
        changes = session.execute(select(FileChange).order_by(FileChange.id)).scalars().all()

    assert isinstance(summary, AnalysisSummary)
    assert summary.commit_count == 3
    assert summary.skipped_commit_count == 0
    assert summary.lineage_count == 2
    assert len(summary.symbol_ids) == 2
    assert [change.change_type for change in changes] == ["added", "renamed", "modified"]
    assert len(versions) == 4
    assert any(symbol.status == "deleted" for symbol in symbols)
    keep_versions = [version for version in versions if version.qualified_name == "keep"]
    assert [version.path for version in keep_versions] == ["old.py", "new.py"]
    assert [version.lineage_method for version in keep_versions] == ["exact", "exact"]


def test_unsupported_language_fails_before_git(
    engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: calls.append(args))

    with Session(engine) as session:
        repository_id = _db_repository(session)
        with pytest.raises(UnsupportedLanguageError):
            analyze_file(session, repository_id, tmp_path, "file.txt")

    assert calls == []


def test_missing_repository_fails_before_git(
    engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: calls.append(args))

    with Session(engine) as session, pytest.raises(ValueError, match="does not exist"):
        analyze_file(session, 999, tmp_path, "file.py")

    assert calls == []


def test_max_commits_adds_truncation_warning(engine: Engine, tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    _write(repo, "file.py", b"def value():\n    return 1\n")
    _commit(repo, "first")
    _write(repo, "file.py", b"def value():\n    return 2\n")
    _commit(repo, "second")

    with Session(engine) as session:
        repository_id = _db_repository(session)
        summary = analyze_file(session, repository_id, repo, "file.py", max_commits=1)

    assert summary.warnings == (
        "history truncated: the oldest returned commit is the baseline and "
        "all its symbols appear as added",
    )


def test_syntax_error_adds_counted_warning(engine: Engine, tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    _write(repo, "file.py", b"def value():\n    return 1\n")
    _commit(repo, "valid")
    _write(repo, "file.py", b"def value(:\n")
    _commit(repo, "syntax error")

    with Session(engine) as session:
        repository_id = _db_repository(session)
        summary = analyze_file(session, repository_id, repo, "file.py")

    assert summary.skipped_commit_count == 1
    assert summary.warnings == ("skipped 1 commit(s) due to syntax errors",)


def test_analyze_file_is_idempotent(engine: Engine, tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    _write(repo, "file.py", b"def value():\n    return 1\n")
    _commit(repo, "initial")

    with Session(engine) as session:
        repository_id = _db_repository(session)
        first = analyze_file(session, repository_id, repo, "file.py")
        session.commit()
        second = analyze_file(session, repository_id, repo, "file.py")
        session.commit()
        assert first.symbol_ids == second.symbol_ids
        assert len(session.execute(select(Commit)).scalars().all()) == 1
        assert len(session.execute(select(SymbolVersion)).scalars().all()) == 1


def test_rollback_leaves_no_rows(engine: Engine, tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    _write(repo, "file.py", b"def value():\n    return 1\n")
    _commit(repo, "initial")

    with Session(engine) as session:
        repository_id = _db_repository(session)
        analyze_file(session, repository_id, repo, "file.py")
        session.rollback()
        assert session.execute(select(Commit)).scalars().all() == []
        assert session.execute(select(Symbol)).scalars().all() == []


def test_file_with_no_history_writes_nothing(engine: Engine, tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    with Session(engine) as session:
        repository_id = _db_repository(session)
        with pytest.raises(GitHistoryError):
            analyze_file(session, repository_id, repo, "missing.py")
        assert session.execute(select(Commit)).scalars().all() == []
