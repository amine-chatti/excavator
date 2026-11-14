"""Orchestrate local Git analysis and persistence for one file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from excavator.core.lineage import build_file_history
from excavator.infra.db.models import Repository
from excavator.infra.git_history import read_file_versions
from excavator.infra.git_metadata import read_commit_metadata
from excavator.infra.persistence import persist_file_history
from excavator.languages.registry import get_analyzer


class UnsupportedLanguageError(ValueError):
    """Raised when no analyzer is registered for a file path."""


@dataclass(frozen=True, slots=True)
class AnalysisSummary:
    repository_id: int
    file_path: str
    ref: str
    commit_count: int
    skipped_commit_count: int
    lineage_count: int
    symbol_ids: tuple[int, ...]
    warnings: tuple[str, ...]


def analyze_file(
    session: Session,
    repository_id: int,
    repo_path: Path | str,
    file_path: str,
    ref: str = "HEAD",
    max_commits: int | None = None,
) -> AnalysisSummary:
    """Analyze and persist one local file without committing the transaction."""
    analyzer = get_analyzer(file_path)
    if analyzer is None:
        raise UnsupportedLanguageError(f"no analyzer is registered for {file_path!r}")
    if session.get(Repository, repository_id) is None:
        raise ValueError(f"repository {repository_id} does not exist")

    versions = read_file_versions(repo_path, file_path, ref, max_commits)
    metadata = read_commit_metadata(repo_path, [version.commit_sha for version in versions])
    history = build_file_history(versions, analyzer)
    result = persist_file_history(
        session,
        repository_id,
        versions,
        history,
        metadata,
        analyzer.language,
    )
    warnings: list[str] = []
    if max_commits is not None and len(versions) == max_commits:
        warnings.append(
            "history truncated: the oldest returned commit is the baseline and "
            "all its symbols appear as added"
        )
    if history.skipped_commits:
        warnings.append(f"skipped {len(history.skipped_commits)} commit(s) due to syntax errors")
    return AnalysisSummary(
        repository_id=repository_id,
        file_path=file_path,
        ref=ref,
        commit_count=len(versions),
        skipped_commit_count=len(history.skipped_commits),
        lineage_count=len(history.lineages),
        symbol_ids=result.symbol_ids,
        warnings=tuple(warnings),
    )
