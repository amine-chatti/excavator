from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from excavator.core.lineage import FileVersion

GIT_TIMEOUT_SECONDS = 30
_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")
_RECORD_SEPARATOR = b"\x1e"


class GitHistoryError(Exception):
    """Raised when a local Git history cannot be read."""


def read_file_versions(
    repo_path: Path | str,
    file_path: str,
    ref: str = "HEAD",
    max_commits: int | None = None,
) -> tuple[FileVersion, ...]:
    """Read the versions of a file touched by Git history, oldest first."""
    _validate_inputs(repo_path, file_path, ref, max_commits)
    repository = Path(repo_path)

    log_args = [
        "log",
        "--follow",
        "--first-parent",
        "--diff-merges=first-parent",
        "--find-renames=20%",
        "--name-status",
        "-z",
        "--format=%x1e%H",
    ]
    if max_commits is not None:
        log_args.append(f"--max-count={max_commits}")
    log_args.extend([ref, "--", file_path])

    log_output = _run_git(repository, log_args)
    records = _parse_log(log_output)
    if not records:
        raise GitHistoryError(f"no Git history found for path {file_path!r}")

    versions: list[FileVersion] = []
    for commit_sha, status, commit_path in records:
        source = None
        if status != "D":
            source = _run_git(
                repository,
                ["cat-file", "blob", f"{commit_sha}:{commit_path}"],
            )
        versions.append(FileVersion(commit_sha, commit_path, source))

    versions.reverse()
    return tuple(versions)


def _validate_inputs(
    repo_path: Path | str,
    file_path: str,
    ref: str,
    max_commits: int | None,
) -> None:
    try:
        repository = Path(repo_path)
    except (TypeError, ValueError) as exc:
        raise ValueError("repo_path must be a directory") from exc
    if not repository.exists() or not repository.is_dir():
        raise ValueError("repo_path must exist and be a directory")

    if not isinstance(file_path, str) or not file_path:
        raise ValueError("file_path must be a non-empty relative path")
    if file_path.startswith("-") or file_path.startswith("/") or "\\" in file_path:
        raise ValueError("file_path must use relative forward-slash path syntax")
    if _DRIVE_PREFIX.match(file_path):
        raise ValueError("file_path must not have a Windows drive prefix")
    if _has_control_character(file_path):
        raise ValueError("file_path must not contain control characters")
    if any(segment in {"", ".", ".."} for segment in file_path.split("/")):
        raise ValueError("file_path must not contain empty, '.' or '..' segments")

    if not isinstance(ref, str) or not ref:
        raise ValueError("ref must be a non-empty ref")
    if ref.startswith("-") or ".." in ref or any(char.isspace() for char in ref):
        raise ValueError("ref must not start with '-' or contain whitespace or '..'")
    if _has_control_character(ref):
        raise ValueError("ref must not contain control characters")

    if max_commits is not None and max_commits < 1:
        raise ValueError("max_commits must be at least 1")


def _has_control_character(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _run_git(repository: Path, arguments: list[str]) -> bytes:
    command = [
        "git",
        "-C",
        str(repository),
        "--no-pager",
        "-c",
        "core.quotepath=false",
        "-c",
        "core.autocrlf=false",
        *arguments,
    ]
    environment = os.environ.copy()
    environment.update({"GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"})
    try:
        completed = subprocess.run(
            command,
            shell=False,
            timeout=GIT_TIMEOUT_SECONDS,
            capture_output=True,
            env=environment,
        )
    except FileNotFoundError as exc:
        raise GitHistoryError("git executable was not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitHistoryError("git command timed out") from exc
    if completed.returncode != 0:
        details = completed.stderr.decode(errors="replace").strip()
        message = "git command failed"
        if details:
            message += f": {details}"
        raise GitHistoryError(message)
    return completed.stdout


def _parse_log(output: bytes) -> list[tuple[str, str, str]]:
    records: list[tuple[str, str, str]] = []
    for raw_record in output.split(_RECORD_SEPARATOR):
        if not raw_record:
            continue
        fields = raw_record.split(b"\0")
        if len(fields) < 3:
            raise GitHistoryError("unable to parse Git log output")
        try:
            commit_sha = fields[0].decode("ascii")
            status = fields[1].lstrip(b"\r\n").decode("ascii")
        except UnicodeDecodeError as exc:
            raise GitHistoryError("unable to parse Git log output") from exc
        if not commit_sha or not status:
            raise GitHistoryError("unable to parse Git log output")

        status_kind = status[0]
        if status_kind in {"R", "C"}:
            if len(fields) < 4:
                raise GitHistoryError("unable to parse Git rename output")
            commit_path = os.fsdecode(fields[3])
        elif status_kind in {"A", "D", "M", "T", "U", "X", "B"}:
            commit_path = os.fsdecode(fields[2])
        else:
            raise GitHistoryError("unable to parse Git status output")
        if not commit_path:
            raise GitHistoryError("unable to parse Git path output")
        records.append((commit_sha, status_kind, commit_path))
    return records
