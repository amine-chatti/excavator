"""Read SHA-1 commit metadata from a local Git repository."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from excavator.infra.git_history import GitHistoryError, _run_git

_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_RECORD_SEPARATOR = b"\x1e"


@dataclass(frozen=True, slots=True)
class CommitMetadata:
    sha: str
    message: str
    author_name: str
    author_email: str
    authored_at: datetime
    parent_shas: tuple[str, ...]


def read_commit_metadata(
    repo_path: Path | str,
    shas: Iterable[str],
) -> dict[str, CommitMetadata]:
    """Read commit metadata in one safe, read-only Git invocation."""
    sha_values = tuple(shas)
    for sha in sha_values:
        if not isinstance(sha, str) or _SHA_PATTERN.fullmatch(sha) is None:
            raise ValueError(
                "only 40-character SHA-1 values are supported; "
                "SHA-256 repositories are not supported yet"
            )
    if not sha_values:
        return {}

    repository = Path(repo_path)
    if not repository.exists() or not repository.is_dir():
        raise ValueError("repo_path must exist and be a directory")
    prefix = _run_git(repository, ["rev-parse", "--show-prefix"])
    if prefix not in {b"", b"\n"}:
        raise ValueError("repo_path must be the repository root")

    output = _run_git(
        repository,
        [
            "log",
            "--no-walk=unsorted",
            "--format=%x1e%H%x00%P%x00%an%x00%ae%x00%aI%x00%B%x00",
            *sha_values,
        ],
    )
    metadata: dict[str, CommitMetadata] = {}
    for raw_record in output.split(_RECORD_SEPARATOR):
        if not raw_record:
            continue
        fields = raw_record.split(b"\0")
        if len(fields) < 6:
            raise GitHistoryError("unable to parse Git commit metadata")
        try:
            sha = fields[0].decode("ascii")
            parents = tuple(fields[1].decode("ascii").split()) if fields[1] else ()
            author_name = fields[2].decode("utf-8", errors="replace")
            author_email = fields[3].decode("utf-8", errors="replace")
            authored_at = datetime.fromisoformat(fields[4].decode("ascii"))
            message = fields[5].decode("utf-8", errors="replace")
        except (UnicodeDecodeError, ValueError) as exc:
            raise GitHistoryError("unable to parse Git commit metadata") from exc
        if authored_at.tzinfo is None or authored_at.utcoffset() is None:
            raise GitHistoryError("unable to parse Git commit metadata")
        if not sha or sha not in sha_values:
            raise GitHistoryError("unable to parse Git commit metadata")
        metadata[sha] = CommitMetadata(
            sha,
            message,
            author_name,
            author_email,
            authored_at,
            parents,
        )
    if set(metadata) != set(sha_values):
        missing = sorted(set(sha_values) - set(metadata))
        raise GitHistoryError(f"commit metadata not found for {', '.join(missing)}")
    return metadata
