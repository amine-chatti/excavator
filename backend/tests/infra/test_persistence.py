from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from excavator.core.lineage import (
    FileHistory,
    FileVersion,
    LineageEvent,
    SymbolLineage,
    build_file_history,
)
from excavator.core.matching import ChangeKind
from excavator.core.symbols import ExtractedSymbol, SymbolKind
from excavator.infra.db.models import (
    Analysis,
    Commit,
    EvidenceLink,
    FileChange,
    Repository,
    Symbol,
    SymbolVersion,
)
from excavator.infra.git_history import read_file_versions
from excavator.infra.git_metadata import CommitMetadata, read_commit_metadata
from excavator.infra.persistence import persist_file_history
from excavator.infra.persistence.file_history import _build_symbol_versions
from excavator.languages.registry import get_analyzer


def _git(repo: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
    )
    return completed.stdout


def git_repository(tmp_path: Path) -> Path:
    repo = tmp_path / "git-repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Persistence Tests")
    _git(repo, "config", "user.email", "persistence@example.invalid")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "core.autocrlf", "false")
    hooks = repo / "hooks"
    hooks.mkdir()
    _git(repo, "config", "core.hooksPath", str(hooks))
    _git(repo, "branch", "-M", "main")
    return repo


def git_commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD").decode().strip()


def git_write(repo: Path, path: str, content: bytes) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def _metadata(shas: tuple[str, ...]) -> dict[str, CommitMetadata]:
    return {
        sha: CommitMetadata(
            sha,
            f"message {index}",
            "Local Author",
            "author@example.invalid",
            datetime(2026, 1, 1, index, tzinfo=UTC),
            (),
        )
        for index, sha in enumerate(shas)
    }


def _symbol(
    name: str,
    body_hash: str,
    start_line: int = 1,
) -> ExtractedSymbol:
    return ExtractedSymbol(
        SymbolKind.FUNCTION,
        name,
        name,
        None,
        start_line,
        start_line,
        start_line + 1,
        0,
        body_hash,
    )


def _history(shas: tuple[str, ...]) -> tuple[tuple[FileVersion, ...], FileHistory]:
    versions = tuple(
        FileVersion(sha, "old.py" if index < 2 else "new.py", None if index == 4 else b"source")
        for index, sha in enumerate(shas)
    )
    first = _symbol("first", "a")
    second = _symbol("second", "b", 3)
    lineage = SymbolLineage(
        (
            LineageEvent(shas[0], ChangeKind.ADDED, first),
            LineageEvent(shas[1], ChangeKind.MODIFIED, _symbol("first", "b")),
            LineageEvent(shas[2], ChangeKind.RENAMED, second),
            LineageEvent(shas[3], ChangeKind.MOVED, _symbol("second", "c", 4)),
            LineageEvent(shas[4], ChangeKind.REMOVED, None),
        )
    )
    return versions, FileHistory((lineage,), ())


def _repository(session: Session) -> int:
    repository = Repository(owner="owner", name="repo")
    session.add(repository)
    session.flush()
    return repository.id


def test_persists_all_event_kinds_and_file_changes(engine: Engine) -> None:
    shas = tuple(f"{index:040x}" for index in range(5))
    versions, history = _history(shas)
    with Session(engine) as session:
        repository_id = _repository(session)
        result = persist_file_history(
            session, repository_id, versions, history, _metadata(shas), "python"
        )
        session.commit()

        changes = session.execute(select(FileChange).order_by(FileChange.id)).scalars().all()
        symbol_versions = (
            session.execute(select(SymbolVersion).order_by(SymbolVersion.id)).scalars().all()
        )
        symbol = session.get(Symbol, result.symbol_ids[0])

    assert [change.change_type for change in changes] == [
        "added",
        "modified",
        "renamed",
        "modified",
        "deleted",
    ]
    assert changes[2].old_path == "old.py"
    assert [version.lineage_method for version in symbol_versions] == [
        "exact",
        "exact",
        "rename_detected",
        "rename_detected",
        "exact",
    ]
    assert symbol is not None
    assert symbol.status == "deleted"
    assert symbol.current_path == "new.py"


def test_empty_skipped_and_symbol_less_commits_get_file_changes(engine: Engine) -> None:
    shas = tuple(f"{index + 10:040x}" for index in range(3))
    versions = (
        FileVersion(shas[0], "empty.py", b""),
        FileVersion(shas[1], "empty.py", b"invalid"),
        FileVersion(shas[2], "empty.py", None),
    )
    history = FileHistory((), (shas[1],))
    with Session(engine) as session:
        repository_id = _repository(session)
        persist_file_history(session, repository_id, versions, history, _metadata(shas), "python")
        session.commit()
        assert session.execute(select(Commit)).scalars().all()
        assert session.execute(select(SymbolVersion)).scalars().all() == []
        assert len(session.execute(select(FileChange)).scalars().all()) == 3


def test_deletion_and_reappearance_are_added_deleted_added(engine: Engine) -> None:
    shas = ("a" * 40, "b" * 40, "c" * 40)
    versions = (
        FileVersion(shas[0], "file.py", b"before"),
        FileVersion(shas[1], "file.py", None),
        FileVersion(shas[2], "file.py", b"after"),
    )
    with Session(engine) as session:
        repository_id = _repository(session)
        persist_file_history(
            session,
            repository_id,
            versions,
            FileHistory((), ()),
            _metadata(shas),
            "python",
        )
        session.commit()
        changes = session.execute(select(FileChange).order_by(FileChange.id)).scalars().all()

    assert [change.change_type for change in changes] == ["added", "deleted", "added"]


@pytest.mark.parametrize(
    ("versions", "history", "metadata", "message"),
    [
        ((), FileHistory((), ()), {}, "versions must be non-empty"),
        (
            (FileVersion("a" * 40, "x.py", b""),),
            FileHistory(
                (SymbolLineage((LineageEvent("b" * 40, ChangeKind.ADDED, _symbol("x", "x")),)),),
                (),
            ),
            _metadata(("a" * 40,)),
            "lineage event SHA",
        ),
        (
            (FileVersion("a" * 40, "x.py", b""),),
            FileHistory((), ("b" * 40,)),
            _metadata(("a" * 40,)),
            "skipped commit SHA",
        ),
        (
            (FileVersion("a" * 40, "x.py", b""),),
            FileHistory((), ()),
            {},
            "commit_metadata is missing",
        ),
        (
            (FileVersion("A" * 40, "x.py", b""),),
            FileHistory((), ()),
            {},
            "only 40-character lowercase SHA-1",
        ),
    ],
)
def test_validates_before_writing(
    engine: Engine,
    versions: tuple[FileVersion, ...],
    history: FileHistory,
    metadata: dict[str, CommitMetadata],
    message: str,
) -> None:
    with Session(engine) as session:
        repository_id = _repository(session)
        with pytest.raises(ValueError, match=message):
            persist_file_history(session, repository_id, versions, history, metadata, "python")
        assert session.execute(select(Commit)).scalars().all() == []


def test_rejects_missing_repository(engine: Engine) -> None:
    sha = "a" * 40
    with Session(engine) as session, pytest.raises(ValueError, match="does not exist"):
        persist_file_history(
            session,
            999,
            (FileVersion(sha, "x.py", b""),),
            FileHistory((), ()),
            _metadata((sha,)),
            "python",
        )


def test_rejects_lineage_that_starts_without_a_symbol(engine: Engine) -> None:
    sha = "a" * 40
    with Session(engine) as session:
        repository_id = _repository(session)
        with pytest.raises(ValueError, match="must start"):
            persist_file_history(
                session,
                repository_id,
                (FileVersion(sha, "x.py", b""),),
                FileHistory(
                    (SymbolLineage((LineageEvent(sha, ChangeKind.REMOVED, None),)),),
                    (),
                ),
                _metadata((sha,)),
                "python",
            )


def test_rejects_removal_without_previous_symbol() -> None:
    sha = "a" * 40
    with pytest.raises(ValueError, match="no previous symbol"):
        _build_symbol_versions(
            SymbolLineage((LineageEvent(sha, ChangeKind.REMOVED, None),)),
            (FileVersion(sha, "x.py", b""),),
            {
                sha: Commit(
                    id=1,
                    repository_id=1,
                    sha=sha,
                    message="",
                    authored_at=datetime.now(UTC),
                    parent_shas=[],
                    url=None,
                )
            },
        )


def test_reanalysis_keeps_symbol_id_and_evidence(engine: Engine) -> None:
    sha = "1" * 40
    versions, history = _history((sha, "2" * 40, "3" * 40, "4" * 40, "5" * 40))
    with Session(engine) as session:
        repository_id = _repository(session)
        first = persist_file_history(
            session,
            repository_id,
            versions,
            history,
            _metadata(tuple(v.commit_sha for v in versions)),
            "python",
        )
        analysis = Analysis(
            symbol_id=first.symbol_ids[0],
            analyzed_commit_sha=sha,
            outcome="evidence_found",
            insufficient_reason=None,
        )
        session.add(analysis)
        session.flush()
        session.add(
            EvidenceLink(
                analysis_id=analysis.id,
                commit_id=first.commit_ids[0],
                source_field="message",
                level="direct",
                method="test",
                epistemic_label="verified",
                quote_text="m",
                quote_start=0,
                quote_end=1,
                url="",
            )
        )
        session.commit()
        second = persist_file_history(
            session,
            repository_id,
            versions,
            history,
            _metadata(tuple(v.commit_sha for v in versions)),
            "python",
        )
        session.commit()
        assert second.symbol_ids == first.symbol_ids
        assert session.get(Analysis, analysis.id) is not None
        assert session.execute(select(EvidenceLink)).scalars().all()


def test_reconciliation_deletes_stale_unanalyzed_and_retains_analyzed(engine: Engine) -> None:
    shas = ("a" * 40, "b" * 40)
    versions, history = _history(("a" * 40, "1" * 40, "2" * 40, "3" * 40, "4" * 40))
    with Session(engine) as session:
        repository_id = _repository(session)
        first = persist_file_history(
            session,
            repository_id,
            versions,
            history,
            _metadata(tuple(v.commit_sha for v in versions)),
            "python",
        )
        analysis = Analysis(
            symbol_id=first.symbol_ids[0],
            analyzed_commit_sha=versions[0].commit_sha,
            outcome="evidence_found",
        )
        session.add(analysis)
        session.commit()
        disappearance = (
            FileVersion(shas[0], "old.py", None),
            FileVersion(shas[1], "old.py", None),
        )
        persist_file_history(
            session,
            repository_id,
            disappearance,
            FileHistory((), ()),
            _metadata(shas),
            "python",
        )
        session.commit()
        retained = session.get(Symbol, first.symbol_ids[0])
        assert retained is not None
        assert retained.status == "deleted"


def test_reconciliation_deletes_stale_symbol_without_analysis(engine: Engine) -> None:
    sha = "a" * 40
    versions, history = _history((sha, "1" * 40, "2" * 40, "3" * 40, "4" * 40))
    with Session(engine) as session:
        repository_id = _repository(session)
        first = persist_file_history(
            session,
            repository_id,
            versions,
            history,
            _metadata(tuple(version.commit_sha for version in versions)),
            "python",
        )
        session.commit()
        persist_file_history(
            session,
            repository_id,
            (FileVersion(sha, "old.py", None),),
            FileHistory((), ()),
            _metadata((sha,)),
            "python",
        )
        session.commit()
        assert session.get(Symbol, first.symbol_ids[0]) is None


def test_duplicate_lineage_keys_keep_lowest_symbol_id(engine: Engine) -> None:
    shas = ("a" * 40, "b" * 40, "c" * 40, "d" * 40, "e" * 40)
    versions, history = _history(shas)
    with Session(engine) as session:
        repository_id = _repository(session)
        first = persist_file_history(
            session,
            repository_id,
            versions,
            history,
            _metadata(shas),
            "python",
        )
        session.commit()
        original = session.get(Symbol, first.symbol_ids[0])
        assert original is not None
        duplicate = Symbol(
            repository_id=repository_id,
            language="python",
            kind="function",
            qualified_name="second",
            status="exists",
            current_path="new.py",
        )
        session.add(duplicate)
        session.flush()
        session.add(
            SymbolVersion(
                symbol_id=duplicate.id,
                commit_id=first.commit_ids[0],
                path="old.py",
                qualified_name="first",
                start_line=1,
                end_line=2,
                body_hash="a",
                parse_status="ok",
                lineage_method="exact",
            )
        )
        session.commit()
        duplicate_id = duplicate.id
        persist_file_history(session, repository_id, versions, history, _metadata(shas), "python")
        session.commit()
        assert session.get(Symbol, original.id) is not None
        assert session.get(Symbol, duplicate_id) is None


def test_end_to_end_git_lineage_persistence(engine: Engine, tmp_path: Path) -> None:
    repo = git_repository(tmp_path)
    git_write(repo, "example.py", b"def keep():\n    return 1\n\ndef remove():\n    return 2\n")
    first = git_commit(repo, "initial")
    git_write(repo, "example.py", b"def keep():\n    return 3\n\ndef remove():\n    return 2\n")
    (repo / "example.py").rename(repo / "renamed.py")
    second = git_commit(repo, "rename")
    git_write(repo, "renamed.py", b"def keep():\n    return 3\n")
    third = git_commit(repo, "remove")
    versions = read_file_versions(repo, "renamed.py")
    analyzer = get_analyzer("renamed.py")
    assert analyzer is not None
    history = build_file_history(versions, analyzer)
    metadata = read_commit_metadata(repo, [first, second, third])

    with Session(engine) as session:
        repository_id = _repository(session)
        persist_file_history(session, repository_id, versions, history, metadata, "python")
        session.commit()
        symbols = session.execute(select(Symbol).order_by(Symbol.id)).scalars().all()
        changes = session.execute(select(FileChange).order_by(FileChange.id)).scalars().all()

    assert len(symbols) == 2
    assert [change.change_type for change in changes] == ["added", "renamed", "modified"]
    assert any(symbol.status == "deleted" for symbol in symbols)


def test_rollback_leaves_no_rows(engine: Engine) -> None:
    sha = "a" * 40
    versions = (FileVersion(sha, "x.py", b""),)
    with Session(engine) as session:
        repository_id = _repository(session)
        persist_file_history(
            session, repository_id, versions, FileHistory((), ()), _metadata((sha,)), "python"
        )
        session.rollback()
        assert session.execute(select(Commit)).scalars().all() == []
