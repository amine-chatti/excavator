"""Persist core file history and symbol lineages."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TypedDict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from excavator.core.lineage import FileHistory, FileVersion, SymbolLineage
from excavator.core.matching import ChangeKind
from excavator.infra.db.models import (
    Analysis,
    Commit,
    FileChange,
    Repository,
    Symbol,
    SymbolVersion,
)
from excavator.infra.git_metadata import CommitMetadata


@dataclass(frozen=True, slots=True)
class PersistResult:
    commit_ids: tuple[int, ...]
    file_change_ids: tuple[int, ...]
    symbol_ids: tuple[int, ...]
    symbol_version_ids: tuple[int, ...]


class _SymbolVersionValues(TypedDict):
    kind: str
    commit_id: int
    path: str
    qualified_name: str
    start_line: int
    end_line: int
    body_hash: str
    parse_status: str
    lineage_method: str
    status: str


def persist_file_history(
    session: Session,
    repository_id: int,
    versions: Iterable[FileVersion],
    history: FileHistory,
    commit_metadata: dict[str, CommitMetadata],
    language: str,
) -> PersistResult:
    """Reconcile one file's lineage inside the caller-owned transaction."""
    version_values = tuple(versions)
    _validate_input(version_values, history, commit_metadata)
    repository = session.get(Repository, repository_id)
    if repository is None:
        raise ValueError(f"repository {repository_id} does not exist")

    version_shas = tuple(version.commit_sha for version in version_values)
    sha_set = set(version_shas)
    metadata_values = {sha: commit_metadata[sha] for sha in sha_set}
    commits = _upsert_commits(session, repository_id, version_shas, metadata_values)
    _replace_file_changes(session, version_values, commits)

    paths = {version.path for version in version_values}
    stored = _load_stored_symbols(session, repository_id, paths)
    stored_by_key: dict[tuple[str, str, str], list[Symbol]] = {}
    for symbol, key in stored:
        stored_by_key.setdefault(key, []).append(symbol)

    symbol_ids: list[int] = []
    symbol_version_ids: list[int] = []
    used_ids: set[int] = set()
    for lineage in history.lineages:
        key = _lineage_key(lineage)
        candidates = stored_by_key.get(key, [])
        candidate = next((item for item in candidates if item.id not in used_ids), None)
        version_rows = _build_symbol_versions(lineage, version_values, commits)
        latest = version_rows[-1]
        if candidate is None:
            symbol = Symbol(
                repository_id=repository_id,
                language=language,
                kind=latest["kind"],
                qualified_name=latest["qualified_name"],
                current_path=latest["path"],
                status=latest["status"],
            )
            session.add(symbol)
            session.flush()
        else:
            symbol = candidate
            used_ids.add(symbol.id)
            session.execute(delete(SymbolVersion).where(SymbolVersion.symbol_id == symbol.id))
        symbol.language = language
        symbol.kind = latest["kind"]
        symbol.qualified_name = latest["qualified_name"]
        symbol.current_path = latest["path"]
        symbol.status = latest["status"]
        session.add_all(
            [
                SymbolVersion(
                    symbol_id=symbol.id,
                    commit_id=row["commit_id"],
                    path=row["path"],
                    qualified_name=row["qualified_name"],
                    start_line=row["start_line"],
                    end_line=row["end_line"],
                    body_hash=row["body_hash"],
                    parse_status=row["parse_status"],
                    lineage_method=row["lineage_method"],
                )
                for row in version_rows
            ]
        )
        session.flush()
        symbol_ids.append(symbol.id)
        symbol_version_ids.extend(
            row.id
            for row in session.execute(
                select(SymbolVersion)
                .where(SymbolVersion.symbol_id == symbol.id)
                .order_by(SymbolVersion.id)
            ).scalars()
        )

    _reconcile_unmatched(session, stored, used_ids)
    session.flush()
    return PersistResult(
        tuple(commits[sha].id for sha in version_shas),
        tuple(change.id for change in _load_file_changes(session, version_values, commits)),
        tuple(symbol_ids),
        tuple(symbol_version_ids),
    )


def _validate_input(
    versions: tuple[FileVersion, ...],
    history: FileHistory,
    commit_metadata: dict[str, CommitMetadata],
) -> None:
    if not versions:
        raise ValueError("versions must be non-empty")
    version_shas = {version.commit_sha for version in versions}
    for sha in version_shas:
        if len(sha) != 40 or any(character not in "0123456789abcdef" for character in sha):
            raise ValueError("only 40-character lowercase SHA-1 values are supported")
    for lineage in history.lineages:
        for event in lineage.events:
            if event.commit_sha not in version_shas:
                raise ValueError(f"lineage event SHA {event.commit_sha} is not in versions")
    for sha in history.skipped_commits:
        if sha not in version_shas:
            raise ValueError(f"skipped commit SHA {sha} is not in versions")
    missing = version_shas - commit_metadata.keys()
    if missing:
        raise ValueError(f"commit_metadata is missing SHA {sorted(missing)[0]}")


def _upsert_commits(
    session: Session,
    repository_id: int,
    shas: tuple[str, ...],
    metadata: dict[str, CommitMetadata],
) -> dict[str, Commit]:
    existing = {
        commit.sha: commit
        for commit in session.execute(
            select(Commit).where(Commit.repository_id == repository_id, Commit.sha.in_(set(shas)))
        ).scalars()
    }
    for sha in dict.fromkeys(shas):
        commit = existing.get(sha)
        if commit is None:
            commit = Commit(
                repository_id=repository_id,
                sha=sha,
                message="",
                authored_at=metadata[sha].authored_at,
                parent_shas=[],
                url=None,
            )
            session.add(commit)
            existing[sha] = commit
        commit.message = metadata[sha].message
        commit.author_login = None
        commit.authored_at = metadata[sha].authored_at
        commit.parent_shas = list(metadata[sha].parent_shas)
        commit.url = None
    session.flush()
    return existing


def _replace_file_changes(
    session: Session,
    versions: tuple[FileVersion, ...],
    commits: dict[str, Commit],
) -> None:
    commit_ids = [commits[version.commit_sha].id for version in versions]
    paths = {version.path for version in versions}
    session.execute(
        delete(FileChange).where(
            FileChange.commit_id.in_(commit_ids),
            FileChange.path.in_(paths),
        )
    )
    previous: FileVersion | None = None
    for version in versions:
        if version.source is None:
            change_type = "deleted"
            old_path = None
        elif previous is None or previous.source is None:
            change_type = "added"
            old_path = None
        elif version.path != previous.path:
            change_type = "renamed"
            old_path = previous.path
        else:
            change_type = "modified"
            old_path = None
        session.add(
            FileChange(
                commit_id=commits[version.commit_sha].id,
                path=version.path,
                old_path=old_path,
                change_type=change_type,
            )
        )
        previous = version
    session.flush()


def _load_file_changes(
    session: Session,
    versions: tuple[FileVersion, ...],
    commits: dict[str, Commit],
) -> list[FileChange]:
    return list(
        session.execute(
            select(FileChange)
            .where(
                FileChange.commit_id.in_([commits[version.commit_sha].id for version in versions]),
                FileChange.path.in_({version.path for version in versions}),
            )
            .order_by(FileChange.id)
        ).scalars()
    )


def _load_stored_symbols(
    session: Session,
    repository_id: int,
    paths: set[str],
) -> list[tuple[Symbol, tuple[str, str, str]]]:
    symbols = list(
        session.execute(
            select(Symbol)
            .join(SymbolVersion)
            .where(Symbol.repository_id == repository_id, SymbolVersion.path.in_(paths))
            .distinct()
            .order_by(Symbol.id)
        ).scalars()
    )
    if not symbols:
        return []
    first_versions = session.execute(
        select(SymbolVersion, Commit)
        .join(Commit, Commit.id == SymbolVersion.commit_id)
        .where(SymbolVersion.symbol_id.in_([symbol.id for symbol in symbols]))
        .order_by(SymbolVersion.symbol_id, SymbolVersion.id)
    ).all()
    first_by_symbol: dict[int, tuple[SymbolVersion, Commit]] = {}
    for version, commit in first_versions:
        first_by_symbol.setdefault(version.symbol_id, (version, commit))
    return [
        (
            symbol,
            (
                symbol.kind,
                first_by_symbol[symbol.id][0].qualified_name,
                first_by_symbol[symbol.id][1].sha,
            ),
        )
        for symbol in symbols
    ]


def _lineage_key(lineage: SymbolLineage) -> tuple[str, str, str]:
    first = lineage.events[0]
    if first.symbol is None:
        raise ValueError("a symbol lineage must start with an event containing a symbol")
    return first.symbol.kind.value, first.symbol.qualified_name, first.commit_sha


def _build_symbol_versions(
    lineage: SymbolLineage,
    versions: tuple[FileVersion, ...],
    commits: dict[str, Commit],
) -> list[_SymbolVersionValues]:
    paths = {version.commit_sha: version.path for version in versions}
    previous = None
    rows: list[_SymbolVersionValues] = []
    for event in lineage.events:
        current = event.symbol or previous
        if current is None:
            raise ValueError("a lineage removal event has no previous symbol")
        change = event.change
        method = "rename_detected" if change in {ChangeKind.RENAMED, ChangeKind.MOVED} else "exact"
        rows.append(
            {
                "kind": current.kind.value,
                "commit_id": commits[event.commit_sha].id,
                "path": paths[event.commit_sha],
                "qualified_name": current.qualified_name,
                "start_line": current.start_line,
                "end_line": current.end_line,
                "body_hash": current.body_hash,
                "parse_status": "ok",
                "lineage_method": method,
                "status": "deleted" if change is ChangeKind.REMOVED else "exists",
            }
        )
        previous = current
    return rows


def _reconcile_unmatched(
    session: Session,
    stored: list[tuple[Symbol, tuple[str, str, str]]],
    used_ids: set[int],
) -> None:
    analyzed = {
        symbol_id
        for symbol_id in session.execute(
            select(Analysis.symbol_id).where(
                Analysis.symbol_id.in_([symbol.id for symbol, _ in stored])
            )
        ).scalars()
    }
    for symbol, _key in stored:
        if symbol.id in used_ids:
            continue
        if symbol.id in analyzed:
            symbol.status = "deleted"
        else:
            session.delete(symbol)
