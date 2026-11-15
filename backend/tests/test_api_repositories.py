from __future__ import annotations

import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from sqlite3 import Connection
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from excavator.api.dependencies import get_github_client, get_session
from excavator.api.main import create_app
from excavator.api.routes.repositories import repository_path
from excavator.infra.db.base import Base
from excavator.infra.db.models import (
    Commit,
    PullRequest,
    Repository,
    Symbol,
    SymbolVersion,
)
from excavator.infra.git_clone import GitCloneError
from excavator.infra.git_history import GitHistoryError
from excavator.infra.github_client import (
    GitHubClientError,
    GitHubRateLimitError,
    IssueData,
    PullRequestData,
    ReviewCommentData,
)


def _git(repo: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
    )
    return completed.stdout


def _git_repository(root: Path, owner: str = "owner", name: str = "repo") -> Path:
    repo = root / owner / name
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "API Tests")
    _git(repo, "config", "user.email", "api@example.invalid")
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


@pytest.fixture
def engine() -> Iterator[Engine]:
    test_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def enable_sqlite_foreign_keys(
        dbapi_connection: Connection,
        _: object,
    ) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def client(
    engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, Session, Path]]:
    root = tmp_path / "repositories"
    root.mkdir()
    monkeypatch.setenv("REPOS_ROOT", str(root))
    app = create_app()
    session = Session(engine)

    def override_session() -> Iterator[Session]:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client, session, root
    session.close()


def test_create_repository_success_and_client_path_is_ignored(
    client: tuple[TestClient, Session, Path],
) -> None:
    test_client, session, root = client
    _git_repository(root)

    response = test_client.post(
        "/repositories",
        json={"owner": "owner", "name": "repo", "path": str(root / "other")},
    )

    assert response.status_code == 201
    assert response.json()["owner"] == "owner"
    assert response.json()["name"] == "repo"
    assert session.scalar(select(Repository).where(Repository.owner == "owner")) is not None


def test_duplicate_repository_returns_conflict(
    client: tuple[TestClient, Session, Path],
) -> None:
    test_client, _, root = client
    _git_repository(root)

    assert (
        test_client.post("/repositories", json={"owner": "owner", "name": "repo"}).status_code
        == 201
    )
    duplicate = test_client.post(
        "/repositories",
        json={"owner": "owner", "name": "repo"},
    )

    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "repository already exists"}


@pytest.mark.parametrize("value", ["", ".", "..", "a/b", r"a\b", "C:\\repo"])
def test_invalid_repository_identifier_returns_422(
    client: tuple[TestClient, Session, Path],
    value: str,
) -> None:
    response = client[0].post("/repositories", json={"owner": value, "name": "repo"})

    assert response.status_code == 422
    assert response.json() == {"detail": "invalid request"}


def test_invalid_repository_name_suffix_returns_422(
    client: tuple[TestClient, Session, Path],
) -> None:
    response = client[0].post(
        "/repositories",
        json={"owner": "owner", "name": "repo.git"},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "invalid request"}


def test_missing_repository_directory_returns_404(
    client: tuple[TestClient, Session, Path],
) -> None:
    response = client[0].post(
        "/repositories",
        json={"owner": "owner", "name": "missing"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "repository directory not found"}


def _create_bare_remote(root: Path) -> Path:
    source = _git_repository(root / "source")
    _write(source, "file.py", b"def value():\n    return 1\n")
    _commit(source, "initial")
    remote_root = root / "remotes"
    bare = remote_root / "owner" / "repo.git"
    bare.parent.mkdir(parents=True)
    _git(bare.parent, "init", "--bare", "-q", bare.name)
    _git(source, "remote", "add", "origin", str(bare))
    _git(source, "push", "-q", "origin", "HEAD:main")
    subprocess.run(
        ["git", "--git-dir", str(bare), "symbolic-ref", "HEAD", "refs/heads/main"],
        check=True,
        capture_output=True,
    )
    return remote_root


def test_clone_repository_then_analyze(
    client: tuple[TestClient, Session, Path],
) -> None:
    test_client, session, root = client
    remote_root = _create_bare_remote(root)
    app = cast(FastAPI, test_client.app)
    app.state.settings.GIT_REMOTE_BASE = str(remote_root)
    app.state.settings.ALLOW_LOCAL_REMOTES = True

    response = test_client.post(
        "/repositories",
        json={"owner": "owner", "name": "repo", "clone": True},
    )

    assert response.status_code == 201
    assert (root / "owner" / "repo" / "file.py").is_file()
    repository_id = response.json()["id"]
    analysis = test_client.post(
        f"/repositories/{repository_id}/analyze",
        json={"file_path": "file.py"},
    )
    assert analysis.status_code == 200
    assert session.get(Repository, repository_id) is not None


def test_clone_true_with_existing_directory_keeps_existing_behavior(
    client: tuple[TestClient, Session, Path],
) -> None:
    test_client, _, root = client
    _git_repository(root)

    response = test_client.post(
        "/repositories",
        json={"owner": "owner", "name": "repo", "clone": True},
    )

    assert response.status_code == 201


def test_clone_failure_returns_generic_502(
    client: tuple[TestClient, Session, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, _, root = client
    absolute = str(root / "private")

    from excavator.api.routes import repositories as repository_routes

    def fail_clone(*args: object, **kwargs: object) -> None:
        raise GitCloneError("git clone failed: " + absolute)

    monkeypatch.setattr(repository_routes, "clone_repository", fail_clone)
    response = test_client.post(
        "/repositories",
        json={"owner": "owner", "name": "repo", "clone": True},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "repository clone failed"}
    assert absolute not in response.text


@pytest.mark.parametrize(
    ("exception", "status_code"),
    [(FileExistsError("exists"), 409), (ValueError("invalid remote"), 422)],
)
def test_clone_preflight_errors_are_mapped(
    client: tuple[TestClient, Session, Path],
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
    status_code: int,
) -> None:
    test_client, _, _ = client

    from excavator.api.routes import repositories as repository_routes

    def fail_clone(*args: object, **kwargs: object) -> None:
        raise exception

    monkeypatch.setattr(repository_routes, "clone_repository", fail_clone)
    response = test_client.post(
        "/repositories",
        json={"owner": "owner", "name": "repo", "clone": True},
    )

    assert response.status_code == status_code


def test_list_repositories_is_ordered_by_id(
    client: tuple[TestClient, Session, Path],
) -> None:
    test_client, _, root = client
    _git_repository(root, "owner", "first")
    _git_repository(root, "owner", "second")
    test_client.post("/repositories", json={"owner": "owner", "name": "first"})
    test_client.post("/repositories", json={"owner": "owner", "name": "second"})

    response = test_client.get("/repositories")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["first", "second"]


def _api_pull_request(number: int) -> PullRequestData:
    return PullRequestData(
        number=number,
        title=f"PR {number}",
        body="body",
        state="open",
        author_login="author",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        merged_at=None,
        url=f"https://github.com/owner/repo/pull/{number}",
        base_ref="main",
        merged=False,
        merge_method="unknown",
    )


def test_ingest_pull_requests_and_list_pagination(
    client: tuple[TestClient, Session, Path],
) -> None:
    test_client, _, root = client
    _, repository_id = _create_analyzable_repo(test_client, root)
    assert (
        test_client.post(
            f"/repositories/{repository_id}/analyze",
            json={"file_path": "new.py"},
        ).status_code
        == 200
    )

    class FakeClient:
        calls = 0

        def list_pull_requests_for_commit(
            self,
            owner: str,
            name: str,
            sha: str,
        ) -> tuple[PullRequestData, ...]:
            self.calls += 1
            return (_api_pull_request(self.calls),)

    app = cast(FastAPI, test_client.app)
    app.dependency_overrides[get_github_client] = lambda: FakeClient()
    response = test_client.post(
        f"/repositories/{repository_id}/ingest-pull-requests",
        json={"file_path": "new.py"},
    )

    assert response.status_code == 200
    assert response.json()["pull_request_count"] == 2
    assert response.json()["pull_request_commit_count"] == 2
    listed = test_client.get(
        f"/repositories/{repository_id}/pull-requests",
        params={"limit": 1, "offset": 1},
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 2
    assert len(listed.json()["items"]) == 1


def test_ingest_pull_requests_requires_analyzed_file(
    client: tuple[TestClient, Session, Path],
) -> None:
    test_client, _, root = client
    _git_repository(root)
    repository_id = test_client.post(
        "/repositories",
        json={"owner": "owner", "name": "repo"},
    ).json()["id"]

    response = test_client.post(
        f"/repositories/{repository_id}/ingest-pull-requests",
        json={"file_path": "file.py"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "file has not been analyzed"}


def test_ingest_pull_requests_unknown_repository_returns_404(
    client: tuple[TestClient, Session, Path],
) -> None:
    response = client[0].post(
        "/repositories/999/ingest-pull-requests",
        json={"file_path": "file.py"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "repository not found"}


def test_ingest_pull_requests_honors_max_commits(
    client: tuple[TestClient, Session, Path],
) -> None:
    test_client, _, root = client
    _, repository_id = _create_analyzable_repo(test_client, root)
    assert (
        test_client.post(
            f"/repositories/{repository_id}/analyze",
            json={"file_path": "new.py"},
        ).status_code
        == 200
    )

    class FakeClient:
        def list_pull_requests_for_commit(
            self,
            owner: str,
            name: str,
            sha: str,
        ) -> tuple[PullRequestData, ...]:
            return (_api_pull_request(20),)

    app = cast(FastAPI, test_client.app)
    app.dependency_overrides[get_github_client] = lambda: FakeClient()
    response = test_client.post(
        f"/repositories/{repository_id}/ingest-pull-requests",
        json={"file_path": "new.py", "max_commits": 1},
    )

    assert response.status_code == 200
    assert response.json()["pull_request_commit_count"] == 1


def test_list_pull_requests_unknown_repository_returns_404(
    client: tuple[TestClient, Session, Path],
) -> None:
    response = client[0].get("/repositories/999/pull-requests")

    assert response.status_code == 404
    assert response.json() == {"detail": "repository not found"}


@pytest.mark.parametrize(
    ("error", "status_code"),
    [(GitHubRateLimitError("limited"), 429), (GitHubClientError("failed"), 502)],
)
def test_ingest_pull_requests_maps_client_errors(
    client: tuple[TestClient, Session, Path],
    error: Exception,
    status_code: int,
) -> None:
    test_client, _, root = client
    _, repository_id = _create_analyzable_repo(test_client, root)
    assert (
        test_client.post(
            f"/repositories/{repository_id}/analyze",
            json={"file_path": "new.py"},
        ).status_code
        == 200
    )

    class FailingClient:
        def list_pull_requests_for_commit(
            self,
            owner: str,
            name: str,
            sha: str,
        ) -> tuple[PullRequestData, ...]:
            raise error

    app = cast(FastAPI, test_client.app)
    app.dependency_overrides[get_github_client] = lambda: FailingClient()
    response = test_client.post(
        f"/repositories/{repository_id}/ingest-pull-requests",
        json={"file_path": "new.py"},
    )

    assert response.status_code == status_code


def test_ingest_pull_requests_maps_unexpected_client_error(
    client: tuple[TestClient, Session, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, _, root = client
    _, repository_id = _create_analyzable_repo(test_client, root)
    assert (
        test_client.post(
            f"/repositories/{repository_id}/analyze",
            json={"file_path": "new.py"},
        ).status_code
        == 200
    )

    from excavator.api.routes import pull_requests as pull_request_routes

    def fail_ingest(*args: object, **kwargs: object) -> object:
        raise GitHubClientError("failed")

    monkeypatch.setattr(pull_request_routes, "ingest_pull_requests", fail_ingest)
    response = test_client.post(
        f"/repositories/{repository_id}/ingest-pull-requests",
        json={"file_path": "new.py"},
    )

    assert response.status_code == 502


def _create_analyzable_repo(test_client: TestClient, root: Path) -> tuple[Path, int]:
    repo = _git_repository(root)
    _write(repo, "old.py", b"def keep():\n    return 1\n\ndef remove():\n    return 2\n")
    _commit(repo, "initial")
    _write(repo, "old.py", b"def keep():\n    return 3\n\ndef remove():\n    return 2\n")
    (repo / "old.py").rename(repo / "new.py")
    _commit(repo, "rename")
    _write(repo, "new.py", b"def keep():\n    return 3\n")
    _commit(repo, "remove")
    repository_id = test_client.post(
        "/repositories",
        json={"owner": "owner", "name": "repo"},
    ).json()["id"]
    return repo, repository_id


def test_analyze_then_symbols_and_lineage(
    client: tuple[TestClient, Session, Path],
) -> None:
    test_client, _, root = client
    _, repository_id = _create_analyzable_repo(test_client, root)

    analyzed = test_client.post(
        f"/repositories/{repository_id}/analyze",
        json={"file_path": "new.py", "ref": "main"},
    )
    symbols = test_client.get(f"/repositories/{repository_id}/symbols")

    assert analyzed.status_code == 200
    assert analyzed.json()["commit_count"] == 3
    assert analyzed.json()["lineage_count"] == 2
    assert symbols.status_code == 200
    assert symbols.json()["total"] == 2
    symbol_id = symbols.json()["items"][0]["id"]
    lineage = test_client.get(f"/symbols/{symbol_id}/lineage")
    assert lineage.status_code == 200
    assert lineage.json()["symbol"]["id"] == symbol_id
    assert lineage.json()["versions"][0]["commit_message"] == "initial"


def test_analyze_twice_is_idempotent(
    client: tuple[TestClient, Session, Path],
) -> None:
    test_client, session, root = client
    _, repository_id = _create_analyzable_repo(test_client, root)

    first = test_client.post(
        f"/repositories/{repository_id}/analyze",
        json={"file_path": "new.py"},
    ).json()
    second = test_client.post(
        f"/repositories/{repository_id}/analyze",
        json={"file_path": "new.py"},
    ).json()

    assert first["symbol_ids"] == second["symbol_ids"]
    assert len(session.execute(select(Symbol)).scalars().all()) == 2
    assert len(session.execute(select(SymbolVersion)).scalars().all()) == 4
    assert len(session.execute(select(Commit)).scalars().all()) == 3


def test_discussion_api_ingestion_and_paginated_lists(
    client: tuple[TestClient, Session, Path],
) -> None:
    test_client, session, root = client
    _git_repository(root)
    repository_id = test_client.post(
        "/repositories", json={"owner": "owner", "name": "repo"}
    ).json()["id"]
    pr = PullRequest(
        repository_id=repository_id,
        number=15,
        title="Discussion",
        body="Fixes #31",
        state="open",
        merged=False,
        merged_at=None,
        merge_method="unknown",
        base_ref="main",
        author_login=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        url="https://github.com/owner/repo/pull/15",
    )
    session.add(pr)
    session.commit()

    class FakeClient:
        def list_review_comments(
            self, owner: str, name: str, number: int
        ) -> tuple[ReviewCommentData, ...]:
            return ()

        def get_issue(self, owner: str, name: str, number: int) -> IssueData | None:
            return IssueData(
                number=31,
                title="Issue 31",
                body=None,
                state="open",
                author_login=None,
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                closed_at=None,
                url="https://github.com/owner/repo/issues/31",
            )

    app = cast(FastAPI, test_client.app)
    app.dependency_overrides[get_github_client] = lambda: FakeClient()
    ingested = test_client.post(f"/repositories/{repository_id}/ingest-discussion")
    assert ingested.status_code == 200
    assert ingested.json() == {
        "review_comment_count": 0,
        "issue_count": 1,
        "issue_reference_count": 1,
        "skipped_pull_request_count": 0,
        "failed_items": [],
    }
    issues = test_client.get(f"/repositories/{repository_id}/issues", params={"limit": 1})
    comments = test_client.get(
        f"/repositories/{repository_id}/pull-requests/15/review-comments",
        params={"limit": 1, "offset": 0},
    )
    assert issues.status_code == 200
    assert issues.json()["total"] == 1
    assert issues.json()["items"][0]["number"] == 31
    assert comments.status_code == 200
    assert comments.json() == {"items": [], "total": 0}


def test_discussion_api_404s(
    client: tuple[TestClient, Session, Path],
) -> None:
    test_client, _, root = client
    assert test_client.post("/repositories/999/ingest-discussion").status_code == 404
    assert test_client.get("/repositories/999/issues").status_code == 404
    assert test_client.get("/repositories/999/pull-requests/1/review-comments").status_code == 404
    _git_repository(root)
    repository_id = test_client.post(
        "/repositories", json={"owner": "owner", "name": "repo"}
    ).json()["id"]
    response = test_client.post(f"/repositories/{repository_id}/ingest-discussion")
    assert response.status_code == 404
    assert response.json() == {"detail": "repository has no stored pull requests"}
    assert (
        test_client.get(
            f"/repositories/{repository_id}/pull-requests/999/review-comments"
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (GitHubRateLimitError("secret token"), 429, "GitHub rate limit exceeded"),
        (GitHubClientError("private path"), 502, "GitHub API request failed"),
    ],
)
def test_discussion_api_maps_errors_generically(
    client: tuple[TestClient, Session, Path],
    error: Exception,
    status: int,
    detail: str,
) -> None:
    test_client, session, root = client
    _git_repository(root)
    repository_id = test_client.post(
        "/repositories", json={"owner": "owner", "name": "repo"}
    ).json()["id"]
    session.add(
        PullRequest(
            repository_id=repository_id,
            number=1,
            title="PR",
            body=None,
            state="open",
            merged=False,
            merged_at=None,
            merge_method="unknown",
            base_ref="main",
            author_login=None,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            url="https://github.com/owner/repo/pull/1",
        )
    )
    session.commit()

    class FailingClient:
        def list_review_comments(
            self, owner: str, name: str, number: int
        ) -> tuple[ReviewCommentData, ...]:
            raise error

        def get_issue(self, owner: str, name: str, number: int) -> IssueData | None:
            return None

    app = cast(FastAPI, test_client.app)
    app.dependency_overrides[get_github_client] = lambda: FailingClient()
    response = test_client.post(f"/repositories/{repository_id}/ingest-discussion")
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert "secret token" not in response.text
    assert "private path" not in response.text


def test_discussion_api_maps_unexpected_service_client_error(
    client: tuple[TestClient, Session, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, session, root = client
    _git_repository(root)
    repository_id = test_client.post(
        "/repositories", json={"owner": "owner", "name": "repo"}
    ).json()["id"]
    session.add(
        PullRequest(
            repository_id=repository_id,
            number=1,
            title="PR",
            body=None,
            state="open",
            merged=False,
            merged_at=None,
            merge_method="unknown",
            base_ref="main",
            author_login=None,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            url="https://github.com/owner/repo/pull/1",
        )
    )
    session.commit()

    from excavator.api.routes import pull_requests as routes

    def fail(*args: object, **kwargs: object) -> object:
        raise GitHubClientError("do not expose")

    monkeypatch.setattr(routes, "ingest_discussion", fail)
    response = test_client.post(f"/repositories/{repository_id}/ingest-discussion")
    assert response.status_code == 502
    assert response.json() == {"detail": "GitHub API request failed"}
    assert "do not expose" not in response.text


def test_analyze_error_mappings_and_path_sanitization(
    client: tuple[TestClient, Session, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, _, root = client
    _, repository_id = _create_analyzable_repo(test_client, root)
    absolute = str(root / "secret.py")

    invalid = test_client.post(
        f"/repositories/{repository_id}/analyze",
        json={"file_path": absolute},
    )
    unsupported = test_client.post(
        f"/repositories/{repository_id}/analyze",
        json={"file_path": "file.txt"},
    )
    unknown = test_client.post(
        "/repositories/999/analyze",
        json={"file_path": "file.py"},
    )
    no_history = test_client.post(
        f"/repositories/{repository_id}/analyze",
        json={"file_path": "missing.py"},
    )

    from excavator.api.routes import analysis as analysis_routes

    def raise_git_failure(*args: object, **kwargs: object) -> object:
        raise GitHistoryError("git command failed: " + absolute)

    monkeypatch.setattr(analysis_routes, "analyze_file", raise_git_failure)
    failed = test_client.post(
        f"/repositories/{repository_id}/analyze",
        json={"file_path": "new.py"},
    )

    assert invalid.status_code == 422
    assert absolute not in invalid.text
    assert unsupported.status_code == 422
    assert unknown.status_code == 404
    assert no_history.status_code == 404
    assert failed.status_code == 502
    assert failed.json() == {"detail": "local Git operation failed"}
    assert absolute not in failed.text


@pytest.mark.parametrize(
    "payload",
    [
        {"file_path": "new.py", "ref": ""},
        {"file_path": "new.py", "ref": "-main"},
        {"file_path": "new.py", "ref": "main..old"},
        {"file_path": "new.py", "ref": "main branch"},
        {"file_path": "new.py", "ref": "main\nbranch"},
        {"file_path": "new.py", "max_commits": 0},
    ],
)
def test_analyze_invalid_git_inputs_are_sanitized(
    client: tuple[TestClient, Session, Path],
    payload: dict[str, object],
) -> None:
    test_client, _, root = client
    _, repository_id = _create_analyzable_repo(test_client, root)

    response = test_client.post(
        f"/repositories/{repository_id}/analyze",
        json=payload,
    )

    assert response.status_code == 422
    assert str(root) not in response.text


def test_repository_path_rejects_outside_root() -> None:
    repository = Repository(owner="..", name="outside")

    with pytest.raises(ValueError, match="outside REPOS_ROOT"):
        repository_path(Path("root"), repository)


def test_create_repository_rejects_resolved_path_outside_root(
    client: tuple[TestClient, Session, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, _, root = client
    _git_repository(root)
    original_resolve = Path.resolve

    def resolve_outside(path: Path, strict: bool = False) -> Path:
        if path.name == "repo":
            return root.parent / "outside"
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve_outside)
    response = test_client.post(
        "/repositories",
        json={"owner": "owner", "name": "repo"},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "invalid repository path"}


def test_analysis_value_error_maps_to_422(
    client: tuple[TestClient, Session, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, _, root = client
    _, repository_id = _create_analyzable_repo(test_client, root)

    from excavator.api.routes import analysis as analysis_routes

    def raise_value_error(*args: object, **kwargs: object) -> object:
        raise ValueError("invalid analysis input")

    monkeypatch.setattr(analysis_routes, "analyze_file", raise_value_error)
    response = test_client.post(
        f"/repositories/{repository_id}/analyze",
        json={"file_path": "new.py"},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "invalid analysis input"}


def test_symbols_pagination_filters_and_total(
    client: tuple[TestClient, Session, Path],
) -> None:
    test_client, _, root = client
    _, repository_id = _create_analyzable_repo(test_client, root)
    test_client.post(
        f"/repositories/{repository_id}/analyze",
        json={"file_path": "new.py"},
    )

    response = test_client.get(
        f"/repositories/{repository_id}/symbols",
        params={"path": "new.py", "kind": "function", "status": "exists", "limit": 1},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert len(response.json()["items"]) == 1


def test_lineage_and_openapi_errors(
    client: tuple[TestClient, Session, Path],
) -> None:
    test_client = client[0]

    assert test_client.get("/symbols/999/lineage").status_code == 404
    openapi = test_client.get("/openapi.json")

    assert openapi.status_code == 200
    assert "/repositories" in openapi.json()["paths"]


def test_session_dependency_closes_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    @contextmanager
    def fake_scope() -> Iterator[Session]:
        events.append("open")
        try:
            yield Session()
        finally:
            events.append("close")

    import excavator.api.dependencies as dependencies

    monkeypatch.setattr(dependencies, "session_scope", fake_scope)
    iterator = dependencies.get_session()
    next(iterator)
    with pytest.raises(StopIteration):
        next(iterator)

    assert events == ["open", "close"]
