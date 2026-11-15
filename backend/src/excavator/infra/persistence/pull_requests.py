from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from excavator.infra.db.models import Commit, PullRequest, PullRequestCommit
from excavator.infra.github_client import (
    GitHubClient,
    GitHubClientError,
    GitHubRateLimitError,
    PullRequestData,
)


@dataclass(frozen=True, slots=True)
class PullRequestPersistResult:
    pull_request_count: int
    pull_request_commit_count: int
    missing_commit_count: int


@dataclass(frozen=True, slots=True)
class PullRequestIngestResult:
    pull_request_count: int
    pull_request_commit_count: int
    missing_commit_count: int
    failed_shas: tuple[str, ...]


def persist_pull_requests(
    session: Session,
    repository_id: int,
    commit_prs: dict[str, tuple[PullRequestData, ...]],
) -> PullRequestPersistResult:
    """Upsert pull requests and links inside the caller-owned transaction."""
    shas = tuple(commit_prs)
    commits = {
        commit.sha: commit
        for commit in session.scalars(
            select(Commit).where(Commit.repository_id == repository_id, Commit.sha.in_(shas))
        )
    }
    missing_commit_count = sum(sha not in commits for sha in shas)
    pull_requests: dict[int, PullRequest] = {}
    link_count = 0
    for sha, data_items in commit_prs.items():
        commit = commits.get(sha)
        for data in data_items:
            pull_request = pull_requests.get(data.number)
            if pull_request is None:
                pull_request = session.scalar(
                    select(PullRequest).where(
                        PullRequest.repository_id == repository_id,
                        PullRequest.number == data.number,
                    )
                )
                if pull_request is None:
                    pull_request = PullRequest(
                        repository_id=repository_id,
                        number=data.number,
                        title=data.title,
                        body=data.body,
                        state=data.state,
                        merged=data.merged,
                        merged_at=data.merged_at,
                        merge_method=data.merge_method,
                        base_ref=data.base_ref,
                        author_login=data.author_login,
                        created_at=data.created_at,
                        url=data.url,
                    )
                    session.add(pull_request)
                    session.flush()
                else:
                    _update_pull_request(pull_request, data)
                pull_requests[data.number] = pull_request
            if commit is not None:
                link = session.get(PullRequestCommit, (pull_request.id, commit.id))
                if link is None:
                    session.add(
                        PullRequestCommit(
                            pull_request_id=pull_request.id,
                            commit_id=commit.id,
                        )
                    )
                link_count += 1
    session.flush()
    return PullRequestPersistResult(len(pull_requests), link_count, missing_commit_count)


def ingest_pull_requests(
    session: Session,
    repository_id: int,
    owner: str,
    name: str,
    shas: Iterable[str],
    client: GitHubClient,
) -> PullRequestIngestResult:
    commit_prs: dict[str, tuple[PullRequestData, ...]] = {}
    failed_shas: list[str] = []
    for sha in dict.fromkeys(shas):
        try:
            commit_prs[sha] = client.list_pull_requests_for_commit(owner, name, sha)
        except GitHubRateLimitError:
            persist_pull_requests(session, repository_id, commit_prs)
            raise
        except GitHubClientError:
            failed_shas.append(sha)
    result = persist_pull_requests(session, repository_id, commit_prs)
    return PullRequestIngestResult(
        result.pull_request_count,
        result.pull_request_commit_count,
        result.missing_commit_count,
        tuple(failed_shas),
    )


def _update_pull_request(pull_request: PullRequest, data: PullRequestData) -> None:
    pull_request.title = data.title
    pull_request.body = data.body
    pull_request.state = data.state
    pull_request.merged = data.merged
    pull_request.merged_at = data.merged_at
    pull_request.merge_method = data.merge_method
    pull_request.base_ref = data.base_ref
    pull_request.author_login = data.author_login
    pull_request.created_at = data.created_at
    pull_request.url = data.url
