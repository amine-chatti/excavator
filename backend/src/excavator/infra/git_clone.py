from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

GIT_CLONE_TIMEOUT_SECONDS = 300
_IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]+$")
_SCRUBBED_ENVIRONMENT = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
)


class GitCloneError(Exception):
    """Raised when a local Git clone cannot be completed."""


def clone_repository(
    owner: str,
    name: str,
    repos_root: Path | str,
    remote_base: str = "https://github.com",
    *,
    allow_local: bool = False,
) -> None:
    """Clone a repository into its validated owner/name target directory."""
    _validate_identifier(owner, "owner")
    _validate_identifier(name, "name")
    if name.endswith(".git"):
        raise ValueError("name must not end with '.git'")

    root = Path(repos_root).expanduser().resolve()
    target = (root / owner / name).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("repository target is outside repos_root") from exc
    if target.exists():
        raise FileExistsError("repository target already exists")

    remote = str(remote_base).rstrip("/\\")
    if remote.startswith("https://"):
        file_protocol = False
    elif allow_local and Path(remote).is_dir():
        file_protocol = True
    else:
        raise ValueError("remote_base must be an HTTPS URL or an allowed local directory")

    url = f"{remote}/{owner}/{name}.git"
    command = [
        "git",
        "clone",
        "--quiet",
        "-c",
        "core.autocrlf=false",
        "-c",
        "protocol.allow=never",
        "-c",
        "protocol.https.allow=always",
    ]
    if file_protocol:
        command.extend(["-c", "protocol.file.allow=always"])
    command.extend(["--", url, str(target)])

    environment = os.environ.copy()
    for variable in _SCRUBBED_ENVIRONMENT:
        environment.pop(variable, None)
    environment.update({"GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"})
    try:
        completed = subprocess.run(
            command,
            shell=False,
            timeout=GIT_CLONE_TIMEOUT_SECONDS,
            capture_output=True,
            env=environment,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        _remove_partial_target(target)
        raise GitCloneError("git clone failed") from exc
    if completed.returncode != 0:
        _remove_partial_target(target)
        raise GitCloneError("git clone failed")


def _validate_identifier(value: str, label: str) -> None:
    if value in {".", ".."} or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} must contain only ASCII letters, numbers, '.', '_' or '-'")


def _remove_partial_target(target: Path) -> None:
    if target.exists():
        try:
            shutil.rmtree(target)
        except OSError as exc:
            raise GitCloneError("git clone failed") from exc
