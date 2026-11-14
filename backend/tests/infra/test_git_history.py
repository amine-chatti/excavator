from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Final, cast

import pytest

from excavator.core.lineage import build_file_history
from excavator.core.matching import ChangeKind
from excavator.infra import git_history
from excavator.infra.git_history import GitHistoryError, read_file_versions
from excavator.languages.registry import get_analyzer

GIT_TIMEOUT: Final = git_history.GIT_TIMEOUT_SECONDS


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
    _git(repo, "config", "user.name", "Excavator Tests")
    _git(repo, "config", "user.email", "excavator-tests@example.invalid")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "core.autocrlf", "false")
    hooks = repo / "hooks"
    hooks.mkdir()
    _git(repo, "config", "core.hooksPath", str(hooks))
    _git(repo, "branch", "-M", "main")
    return repo


def _commit(repo: Path, message: str = "change") -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD").decode().strip()


def _write(repo: Path, path: str, content: bytes) -> None:
    target = repo / Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def test_reads_commits_oldest_first_with_exact_bytes(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    contents = [b"first\r\n", b"second\r", b"third\n"]
    commits = []
    for index, content in enumerate(contents):
        _write(repo, "file.bin", content)
        commits.append(_commit(repo, f"version {index}"))

    versions = read_file_versions(repo, "file.bin")

    assert [version.commit_sha for version in versions] == commits
    assert [version.source for version in versions] == contents
    assert all(version.path == "file.bin" for version in versions)


def test_preserves_binary_bom_and_empty_file_contents(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    contents = [b"\xef\xbb\xbftext", b"\xff\xfe\x00\x80", b""]
    for index, content in enumerate(contents):
        _write(repo, "file.bin", content)
        _commit(repo, str(index))

    versions = read_file_versions(repo, "file.bin")

    assert [version.source for version in versions] == contents


def test_tracks_renames_and_paths_with_spaces_and_unicode(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    _write(repo, "old name.py", b"def f():\n    return 1\n")
    first = _commit(repo, "add")
    new_path = "new \u00e9 name.py"
    (repo / "old name.py").rename(repo / new_path)
    _write(repo, new_path, b"def f():\n    return 2\n")
    second = _commit(repo, "rename")

    versions = read_file_versions(repo, new_path)

    assert [version.commit_sha for version in versions] == [first, second]
    assert [version.path for version in versions] == ["old name.py", new_path]
    assert [version.source for version in versions] == [
        b"def f():\n    return 1\n",
        b"def f():\n    return 2\n",
    ]


def test_deletion_and_reappearance_are_distinct_versions(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    _write(repo, "file.py", b"before")
    first = _commit(repo, "add")
    (repo / "file.py").unlink()
    deleted = _commit(repo, "delete")
    _write(repo, "file.py", b"after")
    reappeared = _commit(repo, "reappear")

    versions = read_file_versions(repo, "file.py")

    assert [version.commit_sha for version in versions] == [first, deleted, reappeared]
    assert [version.source for version in versions] == [b"before", None, b"after"]


def test_max_commits_keeps_newest_commits_in_oldest_first_order(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    commits = []
    for index in range(3):
        _write(repo, "file.py", str(index).encode())
        commits.append(_commit(repo, str(index)))

    versions = read_file_versions(repo, "file.py", max_commits=2)

    assert [version.commit_sha for version in versions] == commits[-2:]


@pytest.mark.parametrize("max_commits", [0, -1])
def test_invalid_max_commits_is_rejected_before_git_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    max_commits: int,
) -> None:
    repo = _repository(tmp_path)

    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("git should not be called")

    monkeypatch.setattr(subprocess, "run", fail_if_called)

    with pytest.raises(ValueError, match="max_commits"):
        read_file_versions(repo, "file.py", max_commits=max_commits)


@pytest.mark.parametrize(
    "file_path",
    ["", "--output=x", "-n1", "../x", "a/../b", "/abs", "C:/x", r"a\b", "\0x"],
)
def test_rejects_invalid_file_paths(tmp_path: Path, file_path: str) -> None:
    repo = _repository(tmp_path)

    with pytest.raises(ValueError, match="file_path"):
        read_file_versions(repo, file_path)


@pytest.mark.parametrize("file_path", [":(top)a.py", ":!a.py", "*.py", "a?.py", "[ab].py"])
def test_treats_pathspec_magic_as_literal(tmp_path: Path, file_path: str) -> None:
    repo = _repository(tmp_path)
    _write(repo, "a.py", b"a")
    _write(repo, "b.py", b"b")
    _commit(repo)

    with pytest.raises(GitHistoryError, match="no Git history"):
        read_file_versions(repo, file_path)


@pytest.mark.parametrize("ref", ["", "--exec=x", "HEAD x", "HEAD\n", "-x", "a..b", "\0"])
def test_rejects_invalid_refs(tmp_path: Path, ref: str) -> None:
    repo = _repository(tmp_path)

    with pytest.raises(ValueError, match="ref"):
        read_file_versions(repo, "file.py", ref=ref)


def test_rejects_invalid_repository_paths(tmp_path: Path) -> None:
    file_path = tmp_path / "file"
    file_path.write_bytes(b"")

    with pytest.raises(ValueError, match="repo_path"):
        read_file_versions(tmp_path / "missing", "file.py")
    with pytest.raises(ValueError, match="repo_path"):
        read_file_versions(file_path, "file.py")
    with pytest.raises(ValueError, match="repo_path"):
        read_file_versions(cast(Path | str, None), "file.py")


def test_maps_git_failures_to_git_history_error(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    _write(repo, "file.py", b"content")
    _commit(repo)

    with pytest.raises(GitHistoryError, match="not a git repository"):
        read_file_versions(tmp_path, "file.py")
    with pytest.raises(GitHistoryError, match="bad revision"):
        read_file_versions(repo, "file.py", ref="missing-ref")
    with pytest.raises(GitHistoryError, match="no Git history"):
        read_file_versions(repo, "missing.py")


@pytest.mark.parametrize(
    ("exception", "message"),
    [
        (FileNotFoundError(), "git executable"),
        (subprocess.TimeoutExpired(["git"], GIT_TIMEOUT), "timed out"),
    ],
)
def test_maps_process_exceptions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
    message: str,
) -> None:
    repo = _repository(tmp_path)

    def raise_exception(*args: object, **kwargs: object) -> None:
        raise exception

    monkeypatch.setattr(subprocess, "run", raise_exception)

    with pytest.raises(GitHistoryError, match=message):
        read_file_versions(repo, "file.py")


def test_includes_git_stderr_in_nonzero_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repository(tmp_path)

    def fail(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(["git"], 1, b"", b"fatal: test failure")

    monkeypatch.setattr(subprocess, "run", fail)

    with pytest.raises(GitHistoryError, match="fatal: test failure"):
        read_file_versions(repo, "file.py")


def test_rejects_unparseable_log_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repository(tmp_path)
    output = subprocess.CompletedProcess(["git"], 0, b"\x1einvalid\0", b"")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: output)

    with pytest.raises(GitHistoryError, match="parse"):
        read_file_versions(repo, "file.py")


def test_parses_newline_in_a_git_path() -> None:
    parsed = git_history._parse_log(b"\x1e" + b"a" * 40 + b"\0\nR100\0old\0new\nname.py\0")

    assert parsed == [("a" * 40, "R", "new\nname.py")]


@pytest.mark.parametrize(
    ("output", "message"),
    [
        (b"\x1e" + b"a" * 40 + b"\0\n", "parse"),
        (b"\x1e" + b"\xff" + b"\0\nM\0file.py\0", "parse"),
        (b"\x1e" + b"a" * 40 + b"\0\n\0file.py\0", "parse"),
        (b"\x1e" + b"a" * 40 + b"\0\nR100\0old", "rename"),
        (b"\x1e" + b"a" * 40 + b"\0\nR100\0old\0", "path"),
        (b"\x1e" + b"a" * 40 + b"\0\nQ\0file.py\0", "status"),
    ],
)
def test_rejects_malformed_log_records(output: bytes, message: str) -> None:
    with pytest.raises(GitHistoryError, match=message):
        git_history._parse_log(output)


def test_git_invocation_is_read_only_and_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repository(tmp_path)
    _write(repo, "file.py", b"content")
    _commit(repo)
    original_run = subprocess.run
    calls: list[tuple[list[str], bool, int, bool, dict[str, str]]] = []

    def spy(
        arguments: list[str],
        *,
        shell: bool,
        timeout: int,
        capture_output: bool,
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append((arguments, shell, timeout, capture_output, env))
        return original_run(
            arguments,
            shell=shell,
            timeout=timeout,
            capture_output=capture_output,
            env=env,
        )

    monkeypatch.setattr(subprocess, "run", spy)
    read_file_versions(repo, "file.py")

    assert calls
    for arguments, shell, timeout, capture_output, _ in calls:
        assert isinstance(arguments, list)
        assert shell is False
        assert timeout == GIT_TIMEOUT
        assert capture_output is True
    log_arguments = calls[0][0]
    assert log_arguments.index("--") + 1 == len(log_arguments) - 1
    assert "--diff-merges=first-parent" in log_arguments


def test_first_parent_history_excludes_side_branch_commits(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    base = b"".join(f"line {index}\n".encode() for index in range(10))
    _write(repo, "file.py", base)
    initial = _commit(repo, "initial")
    _git(repo, "switch", "-c", "side")
    side_content = b"side\n" + base.splitlines(keepends=True)[1]
    side_content += b"".join(base.splitlines(keepends=True)[2:])
    _write(repo, "file.py", side_content)
    side = _commit(repo, "side")
    _git(repo, "switch", "main")
    main_content = base.splitlines(keepends=True)[:-1] + [b"main\n"]
    _write(repo, "file.py", b"".join(main_content))
    main = _commit(repo, "main")
    _git(repo, "merge", "--no-ff", "-q", "side", "-m", "merge")
    merge = _git(repo, "rev-parse", "HEAD").decode().strip()

    versions = read_file_versions(repo, "file.py")

    assert [version.commit_sha for version in versions] == [initial, main, merge]
    assert side not in {version.commit_sha for version in versions}
    expected_merge = (
        b"side\n" + b"".join(f"line {index}\n".encode() for index in range(1, 9)) + b"main\n"
    )
    assert versions[-1].source == expected_merge


def test_reader_feeds_python_lineage_across_rename(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    _write(repo, "old.py", b"def f():\n    return 1\n")
    _commit(repo, "initial")
    _git(repo, "mv", "old.py", "new.py")
    _write(repo, "new.py", b"def f():\n    return 2\n")
    _commit(repo, "rename")
    _write(repo, "new.py", b"def f():\n    return 3\n")
    _commit(repo, "edit")

    versions = read_file_versions(repo, "new.py")
    analyzer = get_analyzer(versions[-1].path)
    assert analyzer is not None
    history = build_file_history(versions, analyzer)

    assert len(history.lineages) == 1
    assert [event.change for event in history.lineages[0].events] == [
        ChangeKind.ADDED,
        ChangeKind.MODIFIED,
        ChangeKind.MODIFIED,
    ]
