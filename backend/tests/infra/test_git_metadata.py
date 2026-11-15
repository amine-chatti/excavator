from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from excavator.infra import git_metadata
from excavator.infra.git_history import GitHistoryError
from excavator.infra.git_metadata import read_commit_metadata


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
    _git(repo, "config", "user.name", "Local Tests")
    _git(repo, "config", "user.email", "local@example.invalid")
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


def test_reads_full_message_unicode_author_and_timezone(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    _git(repo, "config", "user.name", "Zoë Auteur")
    _git(repo, "config", "user.email", "zoe@example.invalid")
    (repo / "file").write_text("content", encoding="utf-8")
    sha = _commit(repo, "subject\n\nbody with unicode: café")

    metadata = read_commit_metadata(repo, [sha])[sha]

    assert metadata.sha == sha
    assert metadata.message == "subject\n\nbody with unicode: café\n"
    assert metadata.author_name == "Zoë Auteur"
    assert metadata.author_email == "zoe@example.invalid"
    assert metadata.authored_at.tzinfo is not None
    assert metadata.parent_shas == ()
    assert isinstance(metadata.authored_at, datetime)


def test_reads_merge_parents(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    (repo / "file").write_text("base", encoding="utf-8")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "side")
    (repo / "side").write_text("side", encoding="utf-8")
    side = _commit(repo, "side")
    _git(repo, "checkout", "-q", "main")
    (repo / "main").write_text("main", encoding="utf-8")
    _commit(repo, "main")
    _git(repo, "merge", "--no-ff", "-q", "side", "-m", "merge")
    merge = _git(repo, "rev-parse", "HEAD").decode().strip()

    metadata = read_commit_metadata(repo, [merge])[merge]

    assert metadata.parent_shas == (
        _git(repo, "rev-parse", "HEAD^1").decode().strip(),
        side,
    )


def test_rejects_sha256_before_running_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(git_metadata, "_run_git", lambda *args: calls.append(args))

    with pytest.raises(ValueError, match="SHA-256 repositories are not supported yet"):
        read_commit_metadata(tmp_path, ["a" * 64])

    assert calls == []


def test_empty_input_does_not_run_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(git_metadata, "_run_git", lambda *args: calls.append(args))

    assert read_commit_metadata(tmp_path, []) == {}
    assert calls == []


def test_rejects_missing_repository_before_git(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exist and be a directory"):
        read_commit_metadata(tmp_path / "missing", ["a" * 40])


def test_missing_sha_maps_to_git_history_error(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    with pytest.raises(GitHistoryError, match="git command failed"):
        read_commit_metadata(repo, ["a" * 40])


def test_rejects_non_root_repository(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    (repo / "file").write_text("content", encoding="utf-8")
    sha = _commit(repo, "message")
    (repo / "subdir").mkdir()

    with pytest.raises(ValueError, match="repository root"):
        read_commit_metadata(repo / "subdir", [sha])


def test_invalid_metadata_output_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repository(tmp_path)
    sha = "a" * 40

    def fake_run(_: Path, arguments: list[str]) -> bytes:
        if arguments[0] == "rev-parse":
            return b""
        return b"\x1e" + sha.encode() + b"\0"

    monkeypatch.setattr(git_metadata, "_run_git", fake_run)
    with pytest.raises(GitHistoryError, match="unable to parse"):
        read_commit_metadata(repo, [sha])


def test_invalid_datetime_metadata_is_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _repository(tmp_path)
    sha = "a" * 40

    def fake_run(_: Path, arguments: list[str]) -> bytes:
        if arguments[0] == "rev-parse":
            return b""
        return b"\x1e" + b"\0".join(
            [sha.encode(), b"", b"name", b"email", b"not-a-date", b"message", b""]
        )

    monkeypatch.setattr(git_metadata, "_run_git", fake_run)
    with pytest.raises(GitHistoryError, match="unable to parse"):
        read_commit_metadata(repo, [sha])


def test_naive_datetime_metadata_is_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _repository(tmp_path)
    sha = "a" * 40

    def fake_run(_: Path, arguments: list[str]) -> bytes:
        if arguments[0] == "rev-parse":
            return b""
        return b"\x1e" + b"\0".join(
            [sha.encode(), b"", b"name", b"email", b"2026-01-01T00:00:00", b"message", b""]
        )

    monkeypatch.setattr(git_metadata, "_run_git", fake_run)
    with pytest.raises(GitHistoryError, match="unable to parse"):
        read_commit_metadata(repo, [sha])


def test_missing_metadata_record_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repository(tmp_path)
    sha = "a" * 40

    def fake_run(_: Path, arguments: list[str]) -> bytes:
        return b"" if arguments[0] == "rev-parse" else b""

    monkeypatch.setattr(git_metadata, "_run_git", fake_run)
    with pytest.raises(GitHistoryError, match="metadata not found"):
        read_commit_metadata(repo, [sha])


def test_metadata_for_unrequested_sha_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _repository(tmp_path)
    requested = "a" * 40
    returned = "b" * 40

    def fake_run(_: Path, arguments: list[str]) -> bytes:
        if arguments[0] == "rev-parse":
            return b""
        return b"\x1e" + b"\0".join(
            [
                returned.encode(),
                b"",
                b"name",
                b"email",
                b"2026-01-01T00:00:00+00:00",
                b"message",
                b"",
            ]
        )

    monkeypatch.setattr(git_metadata, "_run_git", fake_run)
    with pytest.raises(GitHistoryError, match="unable to parse"):
        read_commit_metadata(repo, [requested])


def test_metadata_execution_uses_safe_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _repository(tmp_path)
    (repo / "file").write_text("content", encoding="utf-8")
    sha = _commit(repo, "message")
    with patch("excavator.infra.git_history.subprocess.run", wraps=subprocess.run) as run:
        read_commit_metadata(repo, [sha])

    log_call = run.call_args_list[-1]
    command = log_call.args[0]
    assert command[0:3] == ["git", "-C", str(repo)]
    assert "log" in command
    assert log_call.kwargs["shell"] is False
    assert log_call.kwargs["capture_output"] is True
    assert "timeout" in log_call.kwargs
    assert "text" not in log_call.kwargs
    assert "universal_newlines" not in log_call.kwargs
