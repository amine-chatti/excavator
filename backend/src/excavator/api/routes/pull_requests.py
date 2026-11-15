from __future__ import annotations

from datetime import datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from excavator.api.dependencies import get_github_client, get_session
from excavator.api.routes.analysis import AnalysisRequest
from excavator.infra.db.models import (
    Commit,
    FileChange,
    Issue,
    PullRequest,
    Repository,
    ReviewComment,
)
from excavator.infra.github_client import (
    DiscussionGitHubClient,
    GitHubClient,
    GitHubClientError,
    GitHubRateLimitError,
)
from excavator.infra.persistence.discussion import ingest_discussion
from excavator.infra.persistence.pull_requests import ingest_pull_requests

router = APIRouter(prefix="/repositories", tags=["pull-requests"])


class PullRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: int
    title: str
    body: str | None
    state: str
    merged: bool
    merged_at: datetime | None
    merge_method: str
    base_ref: str
    author_login: str | None
    created_at: datetime
    url: str


class PullRequestIngestResponse(BaseModel):
    pull_request_count: int
    pull_request_commit_count: int
    missing_commit_count: int
    failed_shas: tuple[str, ...]


class PullRequestListResponse(BaseModel):
    items: list[PullRequestResponse]
    total: int


class ReviewCommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    github_id: int
    pull_request_id: int
    review_github_id: int | None
    in_reply_to_github_id: int | None
    path: str
    diff_hunk: str
    commit_sha: str
    original_commit_sha: str
    line: int | None
    start_line: int | None
    original_line: int | None
    original_start_line: int | None
    side: str | None
    start_side: str | None
    subject_type: str | None
    body: str
    author_login: str | None
    created_at: datetime
    updated_at: datetime
    url: str


class IssueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    number: int
    title: str
    body: str | None
    state: str
    author_login: str | None
    created_at: datetime
    closed_at: datetime | None
    url: str


class DiscussionIngestResponse(BaseModel):
    review_comment_count: int
    issue_count: int
    issue_reference_count: int
    skipped_pull_request_count: int
    failed_items: tuple[str, ...]


class ReviewCommentListResponse(BaseModel):
    items: list[ReviewCommentResponse]
    total: int


class IssueListResponse(BaseModel):
    items: list[IssueResponse]
    total: int


@router.post(
    "/{repository_id}/ingest-pull-requests",
    response_model=PullRequestIngestResponse,
)
def ingest_repository_pull_requests(
    repository_id: int,
    payload: AnalysisRequest,
    session: Annotated[Session, Depends(get_session)],
    client: Annotated[GitHubClient, Depends(get_github_client)],
) -> PullRequestIngestResponse:
    repository = session.get(Repository, repository_id)
    if repository is None:
        raise HTTPException(status_code=404, detail="repository not found")
    shas = tuple(
        session.scalars(
            select(Commit.sha)
            .join(FileChange, FileChange.commit_id == Commit.id)
            .where(
                Commit.repository_id == repository_id,
                FileChange.path == payload.file_path,
            )
            .order_by(Commit.id)
        )
    )
    if not shas:
        raise HTTPException(status_code=404, detail="file has not been analyzed")
    if payload.max_commits is not None:
        shas = shas[: payload.max_commits]
    try:
        result = ingest_pull_requests(
            session,
            repository_id,
            repository.owner,
            repository.name,
            shas,
            client,
        )
    except GitHubRateLimitError:
        session.commit()
        raise HTTPException(status_code=429, detail="GitHub rate limit exceeded") from None
    except GitHubClientError:
        raise HTTPException(status_code=502, detail="GitHub API request failed") from None
    if result.failed_shas and result.pull_request_count == 0:
        raise HTTPException(status_code=502, detail="GitHub API request failed")
    return PullRequestIngestResponse(
        pull_request_count=result.pull_request_count,
        pull_request_commit_count=result.pull_request_commit_count,
        missing_commit_count=result.missing_commit_count,
        failed_shas=result.failed_shas,
    )


@router.get(
    "/{repository_id}/pull-requests",
    response_model=PullRequestListResponse,
)
def list_repository_pull_requests(
    repository_id: int,
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PullRequestListResponse:
    if session.get(Repository, repository_id) is None:
        raise HTTPException(status_code=404, detail="repository not found")
    query = select(PullRequest).where(PullRequest.repository_id == repository_id)
    total = session.scalar(
        select(func.count(PullRequest.id)).where(PullRequest.repository_id == repository_id)
    )
    rows = list(session.scalars(query.order_by(PullRequest.number).offset(offset).limit(limit)))
    items = [PullRequestResponse.model_validate(row) for row in rows]
    return PullRequestListResponse(items=items, total=total or 0)


@router.post(
    "/{repository_id}/ingest-discussion",
    response_model=DiscussionIngestResponse,
)
def ingest_repository_discussion(
    repository_id: int,
    session: Annotated[Session, Depends(get_session)],
    client: Annotated[GitHubClient, Depends(get_github_client)],
) -> DiscussionIngestResponse:
    repository = session.get(Repository, repository_id)
    if repository is None:
        raise HTTPException(status_code=404, detail="repository not found")
    if (
        session.scalar(
            select(func.count(PullRequest.id)).where(PullRequest.repository_id == repository_id)
        )
        == 0
    ):
        raise HTTPException(status_code=404, detail="repository has no stored pull requests")
    try:
        result = ingest_discussion(
            session,
            repository_id,
            repository.owner,
            repository.name,
            cast(DiscussionGitHubClient, client),
        )
    except GitHubRateLimitError:
        session.commit()
        raise HTTPException(status_code=429, detail="GitHub rate limit exceeded") from None
    except GitHubClientError:
        raise HTTPException(status_code=502, detail="GitHub API request failed") from None
    if (
        result.failed_items
        and result.review_comment_count == 0
        and result.issue_count == 0
        and result.issue_reference_count == 0
    ):
        raise HTTPException(status_code=502, detail="GitHub API request failed")
    return DiscussionIngestResponse(
        review_comment_count=result.review_comment_count,
        issue_count=result.issue_count,
        issue_reference_count=result.issue_reference_count,
        skipped_pull_request_count=result.skipped_pull_request_count,
        failed_items=result.failed_items,
    )


@router.get("/{repository_id}/issues", response_model=IssueListResponse)
def list_repository_issues(
    repository_id: int,
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> IssueListResponse:
    if session.get(Repository, repository_id) is None:
        raise HTTPException(status_code=404, detail="repository not found")
    query = select(Issue).where(Issue.repository_id == repository_id)
    total = session.scalar(select(func.count(Issue.id)).where(Issue.repository_id == repository_id))
    rows = list(session.scalars(query.order_by(Issue.number).offset(offset).limit(limit)))
    return IssueListResponse(
        items=[IssueResponse.model_validate(row) for row in rows], total=total or 0
    )


@router.get(
    "/{repository_id}/pull-requests/{number}/review-comments",
    response_model=ReviewCommentListResponse,
)
def list_pull_request_review_comments(
    repository_id: int,
    number: int,
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ReviewCommentListResponse:
    if session.get(Repository, repository_id) is None:
        raise HTTPException(status_code=404, detail="repository not found")
    pr = session.scalar(
        select(PullRequest).where(
            PullRequest.repository_id == repository_id, PullRequest.number == number
        )
    )
    if pr is None:
        raise HTTPException(status_code=404, detail="pull request not found")
    query = select(ReviewComment).where(ReviewComment.pull_request_id == pr.id)
    total = session.scalar(
        select(func.count(ReviewComment.id)).where(ReviewComment.pull_request_id == pr.id)
    )
    rows = list(
        session.scalars(query.order_by(ReviewComment.github_id).offset(offset).limit(limit))
    )
    return ReviewCommentListResponse(
        items=[ReviewCommentResponse.model_validate(row) for row in rows], total=total or 0
    )
