from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from excavator.infra.db.models import Commit, PullRequest, PullRequestCommit, Repository
from excavator.infra.github_client import (
    GitHubClientError,
    GitHubRateLimitError,
    PullRequestData,
)
from excavator.infra.persistence.pull_requests import (
    ingest_pull_requests,
    persist_pull_requests,
)


def _data(number: int, base_ref: str = "main") -> PullRequestData:
    return PullRequestData(
        number=number,
        title=f"PR {number}",
        body="body",
        state="open",
        author_login="author",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        merged_at=None,
        url=f"https://github.com/owner/repo/pull/{number}",
        base_ref=base_ref,
        merged=False,
        merge_method="unknown",
    )


def _repository(session: Session) -> int:
    repository = Repository(owner="owner", name="repo")
    session.add(repository)
    session.flush()
    return repository.id


def _commit(session: Session, repository_id: int, sha: str) -> None:
    session.add(
        Commit(
            repository_id=repository_id,
            sha=sha,
            message="message",
            authored_at=datetime(2026, 1, 1, tzinfo=UTC),
            parent_shas=[],
        )
    )
    session.flush()


def test_persist_pull_requests_is_idempotent_and_skips_missing_commits(
    engine: Engine,
) -> None:
    existing_sha = "1" * 40
    missing_sha = "2" * 40
    with Session(engine) as session:
        repository_id = _repository(session)
        _commit(session, repository_id, existing_sha)
        commit_prs: dict[str, tuple[PullRequestData, ...]] = {
            existing_sha: (_data(7, "main"),),
            missing_sha: (_data(8),),
        }

        first = persist_pull_requests(session, repository_id, commit_prs)
        session.commit()
        second = persist_pull_requests(session, repository_id, commit_prs)
        session.commit()

        pull_requests = session.scalars(select(PullRequest)).all()
        links = session.scalars(select(PullRequestCommit)).all()

    assert first == second
    assert first.pull_request_count == 2
    assert first.pull_request_commit_count == 1
    assert first.missing_commit_count == 1
    assert [pull_request.id for pull_request in pull_requests] == [1, 2]
    assert pull_requests[0].base_ref == "main"
    assert len(links) == 1


def test_ingest_records_failures_and_deduplicates_shas(engine: Engine) -> None:
    sha = "3" * 40

    class FakeClient:
        def list_pull_requests_for_commit(
            self,
            owner: str,
            name: str,
            requested_sha: str,
        ) -> tuple[PullRequestData, ...]:
            assert (owner, name, requested_sha) == ("owner", "repo", sha)
            return (_data(9),)

    with Session(engine) as session:
        repository_id = _repository(session)
        _commit(session, repository_id, sha)
        result = ingest_pull_requests(
            session,
            repository_id,
            "owner",
            "repo",
            [sha, sha],
            FakeClient(),
        )

    assert result.failed_shas == ()
    assert result.pull_request_count == 1
    assert result.pull_request_commit_count == 1


def test_ingest_continues_after_individual_client_error(engine: Engine) -> None:
    good_sha = "4" * 40
    failed_sha = "5" * 40

    class FakeClient:
        def list_pull_requests_for_commit(
            self,
            owner: str,
            name: str,
            requested_sha: str,
        ) -> tuple[PullRequestData, ...]:
            if requested_sha == failed_sha:
                raise GitHubClientError("failure")
            return (_data(10),)

    with Session(engine) as session:
        repository_id = _repository(session)
        _commit(session, repository_id, good_sha)
        result = ingest_pull_requests(
            session,
            repository_id,
            "owner",
            "repo",
            [good_sha, failed_sha],
            FakeClient(),
        )

    assert result.failed_shas == (failed_sha,)
    assert result.pull_request_count == 1


def test_ingest_persists_partial_results_before_rate_limit(engine: Engine) -> None:
    good_sha = "6" * 40
    limited_sha = "7" * 40

    class FakeClient:
        def list_pull_requests_for_commit(
            self,
            owner: str,
            name: str,
            requested_sha: str,
        ) -> tuple[PullRequestData, ...]:
            if requested_sha == limited_sha:
                raise GitHubRateLimitError("limited")
            return (_data(11),)

    with Session(engine) as session:
        repository_id = _repository(session)
        _commit(session, repository_id, good_sha)
        with pytest.raises(GitHubRateLimitError):
            ingest_pull_requests(
                session,
                repository_id,
                "owner",
                "repo",
                [good_sha, limited_sha],
                FakeClient(),
            )
        assert session.scalars(select(PullRequest)).one().number == 11
