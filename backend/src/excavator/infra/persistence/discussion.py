from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from excavator.infra.db.models import (
    Commit,
    Issue,
    IssueReference,
    PullRequest,
    PullRequestCommit,
    ReviewComment,
)
from excavator.infra.github_client import (
    DiscussionGitHubClient,
    GitHubClientError,
    GitHubRateLimitError,
    IssueData,
    ReviewCommentData,
)


@dataclass(frozen=True, slots=True)
class DiscussionCounts:
    review_comment_count: int = 0
    issue_count: int = 0
    issue_reference_count: int = 0
    skipped_pull_request_count: int = 0


@dataclass(frozen=True, slots=True)
class DiscussionIngestResult:
    review_comment_count: int
    issue_count: int
    issue_reference_count: int
    skipped_pull_request_count: int
    failed_items: tuple[str, ...]


_ISSUE_RE = re.compile(r"(?<![\w/])#([1-9][0-9]*)\b")
_CLOSING_REF_RE = re.compile(
    r"\b(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s*:?\s*#([1-9][0-9]*)\b",
    re.IGNORECASE,
)


def _without_code_and_urls(text: str) -> str:
    text = re.sub(r"```.*?```|~~~.*?~~~|`[^`]*`", " ", text, flags=re.DOTALL)
    return re.sub(r"https?://\S+", " ", text, flags=re.IGNORECASE)


def _references(text: str) -> tuple[tuple[int, str], ...]:
    clean = _without_code_and_urls(text)
    closing_numbers = {int(match.group(1)) for match in _CLOSING_REF_RE.finditer(clean)}
    result: dict[int, str] = {}
    for match in _ISSUE_RE.finditer(clean):
        method = "closing_keyword" if int(match.group(1)) in closing_numbers else "plain_reference"
        number = int(match.group(1))
        if number not in result or method == "closing_keyword":
            result[number] = method
    return tuple(sorted(result.items()))


def extract_issue_numbers(text: str) -> tuple[int, ...]:
    """Return sorted unique #number references outside inline/fenced code and URLs.

    This intentionally does not parse cross-repository references, GitHub URLs,
    HTML comments, or references without a leading #.
    """
    return tuple(number for number, _method in _references(text))


def persist_review_comments(
    session: Session,
    repository_id: int,
    pr_comments: dict[int, tuple[ReviewCommentData, ...]],
) -> DiscussionCounts:
    numbers = tuple(pr_comments)
    prs = {
        pr.number: pr
        for pr in session.scalars(
            select(PullRequest).where(
                PullRequest.repository_id == repository_id,
                PullRequest.number.in_(numbers),
            )
        )
    }
    missing = sum(number not in prs for number in numbers)
    count = 0
    for number, comments in pr_comments.items():
        pr = prs.get(number)
        if pr is None:
            continue
        for data in comments:
            comment = session.scalar(
                select(ReviewComment).where(ReviewComment.github_id == data.github_id)
            )
            if comment is None:
                comment = ReviewComment(github_id=data.github_id, pull_request_id=pr.id)
                session.add(comment)
            _update_comment(comment, pr.id, data)
            count += 1
    session.flush()
    return DiscussionCounts(review_comment_count=count, skipped_pull_request_count=missing)


def _update_comment(comment: ReviewComment, pull_request_id: int, data: ReviewCommentData) -> None:
    comment.pull_request_id = pull_request_id
    comment.review_github_id = data.review_github_id
    comment.in_reply_to_github_id = data.in_reply_to_github_id
    comment.path = data.path
    comment.diff_hunk = data.diff_hunk
    comment.commit_sha = data.commit_sha
    comment.original_commit_sha = data.original_commit_sha
    comment.line = data.line
    comment.start_line = data.start_line
    comment.original_line = data.original_line
    comment.original_start_line = data.original_start_line
    comment.side = data.side
    comment.start_side = data.start_side
    comment.subject_type = data.subject_type
    comment.body = data.body
    comment.author_login = data.author_login
    comment.created_at = data.created_at
    comment.updated_at = data.updated_at
    comment.url = data.url


def persist_issues(
    session: Session,
    repository_id: int,
    issues: tuple[IssueData, ...],
) -> dict[int, Issue]:
    persisted: dict[int, Issue] = {}
    for data in issues:
        issue = session.scalar(
            select(Issue).where(Issue.repository_id == repository_id, Issue.number == data.number)
        )
        if issue is None:
            issue = Issue(repository_id=repository_id, number=data.number)
            session.add(issue)
        issue.title = data.title
        issue.body = data.body
        issue.state = data.state
        issue.author_login = data.author_login
        issue.created_at = data.created_at
        issue.closed_at = data.closed_at
        issue.url = data.url
        persisted[data.number] = issue
    session.flush()
    return persisted


def persist_issue_references(
    session: Session,
    issue_ids: dict[int, int],
    pr_references: dict[int, tuple[tuple[int, str], ...]],
    commit_references: dict[int, tuple[tuple[int, str], ...]],
) -> int:
    count = 0
    for pr_id, references in pr_references.items():
        for number, method in references:
            issue_id = issue_ids.get(number)
            if issue_id is None:
                continue
            if (
                session.scalar(
                    select(IssueReference).where(
                        IssueReference.pull_request_id == pr_id,
                        IssueReference.issue_id == issue_id,
                        IssueReference.method == method,
                    )
                )
                is None
            ):
                session.add(IssueReference(pull_request_id=pr_id, issue_id=issue_id, method=method))
            count += 1
    for commit_id, references in commit_references.items():
        for number, method in references:
            issue_id = issue_ids.get(number)
            if issue_id is None:
                continue
            if (
                session.scalar(
                    select(IssueReference).where(
                        IssueReference.commit_id == commit_id,
                        IssueReference.issue_id == issue_id,
                        IssueReference.method == method,
                    )
                )
                is None
            ):
                session.add(IssueReference(commit_id=commit_id, issue_id=issue_id, method=method))
            count += 1
    session.flush()
    return count


def ingest_discussion(
    session: Session,
    repository_id: int,
    owner: str,
    name: str,
    client: DiscussionGitHubClient,
) -> DiscussionIngestResult:
    prs = tuple(
        session.scalars(
            select(PullRequest)
            .where(PullRequest.repository_id == repository_id)
            .order_by(PullRequest.number)
        )
    )
    commits_by_pr: dict[int, tuple[Commit, ...]] = {}
    for pr in prs:
        commits_by_pr[pr.id] = tuple(
            session.scalars(
                select(Commit)
                .join(PullRequestCommit, PullRequestCommit.commit_id == Commit.id)
                .where(PullRequestCommit.pull_request_id == pr.id)
            )
        )

    failed: list[str] = []
    pr_comments: dict[int, tuple[ReviewCommentData, ...]] = {}
    pr_refs: dict[int, tuple[tuple[int, str], ...]] = {}
    commit_refs: dict[int, tuple[tuple[int, str], ...]] = {}
    issue_numbers: set[int] = set()
    for pr in prs:
        try:
            pr_comments[pr.number] = client.list_review_comments(owner, name, pr.number)
        except GitHubRateLimitError:
            persist_review_comments(session, repository_id, pr_comments)
            raise
        except GitHubClientError:
            failed.append(f"pull_request:{pr.number}:review_comments")
        refs = _references(pr.body or "")
        if refs:
            pr_refs[pr.id] = refs
            issue_numbers.update(number for number, _ in refs)
        for commit in commits_by_pr[pr.id]:
            refs = _references(commit.message)
            if refs:
                commit_refs[commit.id] = refs
                issue_numbers.update(number for number, _ in refs)

    issue_data: list[IssueData] = []
    for number in sorted(issue_numbers):
        try:
            issue = client.get_issue(owner, name, number)
            if issue is not None:
                issue_data.append(issue)
        except GitHubRateLimitError:
            persist_review_comments(session, repository_id, pr_comments)
            persisted = persist_issues(session, repository_id, tuple(issue_data))
            persist_issue_references(
                session,
                {n: item.id for n, item in persisted.items()},
                pr_refs,
                commit_refs,
            )
            raise
        except GitHubClientError:
            failed.append(f"issue:{number}")

    comment_counts = persist_review_comments(session, repository_id, pr_comments)
    persisted = persist_issues(session, repository_id, tuple(issue_data))
    reference_count = persist_issue_references(
        session,
        {number: issue.id for number, issue in persisted.items()},
        pr_refs,
        commit_refs,
    )
    return DiscussionIngestResult(
        review_comment_count=comment_counts.review_comment_count,
        issue_count=len(persisted),
        issue_reference_count=reference_count,
        skipped_pull_request_count=comment_counts.skipped_pull_request_count,
        failed_items=tuple(failed),
    )
