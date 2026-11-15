from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from excavator.infra import git_clone
from excavator.infra.git_clone import GitCloneError, clone_repository


def _git(repo: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
    )
    return completed.stdout


def _source_repository(root: Path) -> Path:
    repo = root / "source"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Clone Tests")
    _git(repo, "config", "user.email", "clone@example.invalid")
    (repo / "file.py").write_bytes(b"def value():\n    return 1\n")
    _git(repo, "add", "file.py")
    _git(repo, "commit", "-q", "-m", "initial")
    _git(repo, "branch", "-M", "main")
    return repo


def _bare_remote(root: Path) -> Path:
    source = _source_repository(root)
    remote = root / "remotes" / "owner" / "repo.git"
    remote.parent.mkdir(parents=True)
    _git(remote.parent, "init", "--bare", "-q", remote.name)
    _git(source, "remote", "add", "origin", str(remote))
    _git(source, "push", "-q", "origin", "HEAD:main")
    subprocess.run(
        ["git", "--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main"],
        check=True,
        capture_output=True,
    )
    return remote.parent.parent


def test_clone_repository_from_allowed_local_remote(tmp_path: Path) -> None:
    remote_base = _bare_remote(tmp_path)
    target_root = tmp_path / "repositories"

    clone_repository("owner", "repo", target_root, str(remote_base), allow_local=True)

    assert (target_root / "owner" / "repo" / "file.py").read_bytes() == (
        b"def value():\n    return 1\n"
    )


@pytest.mark.parametrize(
    ("owner", "name"),
    [
        ("", "repo"),
        (".", "repo"),
        ("..", "repo"),
        ("owner/name", "repo"),
        ("owner", ""),
        ("owner", "."),
        ("owner", ".."),
        ("owner", "repo.git"),
    ],
)
def test_clone_repository_rejects_invalid_identifiers(
    tmp_path: Path,
    owner: str,
    name: str,
) -> None:
    with pytest.raises(ValueError):
        clone_repository(owner, name, tmp_path)


def test_clone_repository_rejects_local_remote_without_opt_in(tmp_path: Path) -> None:
    remote_base = tmp_path / "remote"
    remote_base.mkdir()

    with pytest.raises(ValueError, match="HTTPS"):
        clone_repository("owner", "repo", tmp_path / "repositories", str(remote_base))


def test_clone_repository_rejects_existing_target(tmp_path: Path) -> None:
    target = tmp_path / "repositories" / "owner" / "repo"
    target.mkdir(parents=True)

    with pytest.raises(FileExistsError):
        clone_repository("owner", "repo", tmp_path / "repositories")


def test_clone_repository_rejects_target_outside_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_resolve = Path.resolve

    def resolve_outside(path: Path, strict: bool = False) -> Path:
        if path.name == "repo":
            return tmp_path / "outside"
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve_outside)

    with pytest.raises(ValueError, match="outside repos_root"):
        clone_repository("owner", "repo", tmp_path / "repositories")


def test_clone_repository_subprocess_is_restricted_and_scrubs_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("GIT_DIR", "secret")
    monkeypatch.setenv("GIT_WORK_TREE", "secret")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        captured["command"] = command
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    clone_repository("owner", "repo", tmp_path / "repositories")

    command = captured["command"]
    assert isinstance(command, list)
    assert command[0:2] == ["git", "clone"]
    assert command[command.index("--") + 1] == "https://github.com/owner/repo.git"
    assert captured["shell"] is False
    assert captured["timeout"] == git_clone.GIT_CLONE_TIMEOUT_SECONDS
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert "GIT_DIR" not in environment
    assert "GIT_WORK_TREE" not in environment
    assert environment["GIT_TERMINAL_PROMPT"] == "0"
    assert environment["GIT_OPTIONAL_LOCKS"] == "0"


def test_clone_repository_failure_cleans_partial_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "repositories" / "owner" / "repo"

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        target.mkdir(parents=True)
        (target / "partial").write_text("partial")
        return subprocess.CompletedProcess(command, 1, stdout=b"", stderr=b"secret path")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(GitCloneError, match="git clone failed") as error:
        clone_repository("owner", "repo", tmp_path / "repositories")

    assert not target.exists()
    assert str(tmp_path) not in str(error.value)


def test_clone_repository_timeout_with_no_partial_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(command, 300)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(GitCloneError, match="git clone failed"):
        clone_repository("owner", "repo", tmp_path / "repositories")


def test_clone_repository_surfaces_cleanup_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "repositories" / "owner" / "repo"

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        target.mkdir(parents=True)
        return subprocess.CompletedProcess(command, 1, stdout=b"", stderr=b"")

    def fail_remove(path: Path) -> None:
        raise OSError("cleanup failed")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(shutil, "rmtree", fail_remove)

    with pytest.raises(GitCloneError, match="git clone failed"):
        clone_repository("owner", "repo", tmp_path / "repositories")
