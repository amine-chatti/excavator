from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from excavator.infra.db.models import (
    Commit,
    Issue,
    IssueReference,
    PullRequest,
    PullRequestCommit,
    Repository,
    ReviewComment,
    Symbol,
    SymbolVersion,
)


@dataclass(frozen=True, slots=True)
class EvidenceEvent:
    commit_sha: str
    lineage_method: str


@dataclass(frozen=True, slots=True)
class EvidenceSnippet:
    id: str
    source_type: str
    text: str
    source_field: str
    url: str
    commit_id: int | None = None
    pull_request_id: int | None = None
    review_comment_id: int | None = None
    issue_id: int | None = None


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    symbol_id: int
    qualified_name: str
    kind: str
    events: tuple[EvidenceEvent, ...]
    snippets: tuple[EvidenceSnippet, ...]
    truncated: bool
    truncated_snippet_count: int
    omitted_snippet_count: int


def build_evidence_bundle(
    session: Session,
    symbol_id: int,
    max_snippets: int = 40,
    max_chars_per_snippet: int = 2000,
) -> EvidenceBundle:
    if max_snippets < 0 or max_chars_per_snippet < 1:
        raise ValueError("max_snippets must be non-negative and max_chars_per_snippet positive")
    symbol = session.get(Symbol, symbol_id)
    if symbol is None:
        raise ValueError("symbol not found")
    rows = session.execute(
        select(SymbolVersion, Commit)
        .join(Commit, Commit.id == SymbolVersion.commit_id)
        .where(SymbolVersion.symbol_id == symbol_id)
        .order_by(SymbolVersion.id)
    ).all()
    events = tuple(
        EvidenceEvent(commit_sha=commit.sha, lineage_method=version.lineage_method)
        for version, commit in rows
    )
    versions = [(version, commit) for version, commit in rows]
    commits = {commit.id: commit for _, commit in versions}
    commit_ids = tuple(commits)
    repository = session.get(Repository, symbol.repository_id)

    candidates: list[EvidenceSnippet] = []
    for _, commit in versions:
        if commit.message.strip():
            url = commit.url
            if url is None:
                if repository is None:
                    raise ValueError("symbol repository not found")
                url = f"https://github.com/{repository.owner}/{repository.name}/commit/{commit.sha}"
            candidates.append(
                EvidenceSnippet(
                    id=f"commit:{commit.sha}:message",
                    source_type="commit_message",
                    text=commit.message,
                    source_field="message",
                    url=url,
                    commit_id=commit.id,
                )
            )

    if commit_ids:
        prs = tuple(
            session.scalars(
                select(PullRequest)
                .join(PullRequestCommit, PullRequestCommit.pull_request_id == PullRequest.id)
                .where(PullRequestCommit.commit_id.in_(commit_ids))
                .distinct()
                .order_by(PullRequest.number)
            )
        )
    else:
        prs = ()
    pr_ids = tuple(pr.id for pr in prs)
    for pr in prs:
        if pr.title.strip():
            candidates.append(
                EvidenceSnippet(
                    id=f"pr:{pr.number}:title",
                    source_type="pull_request",
                    text=pr.title,
                    source_field="title",
                    url=pr.url,
                    pull_request_id=pr.id,
                )
            )
        if pr.body and pr.body.strip():
            candidates.append(
                EvidenceSnippet(
                    id=f"pr:{pr.number}:body",
                    source_type="pull_request",
                    text=pr.body,
                    source_field="body",
                    url=pr.url,
                    pull_request_id=pr.id,
                )
            )

    if pr_ids:
        comments = tuple(
            session.scalars(
                select(ReviewComment)
                .where(ReviewComment.pull_request_id.in_(pr_ids))
                .order_by(ReviewComment.github_id)
            )
        )
    else:
        comments = ()
    for comment in comments:
        if comment.body.strip():
            candidates.append(
                EvidenceSnippet(
                    id=f"review:{comment.github_id}",
                    source_type="review_comment",
                    text=comment.body,
                    source_field="body",
                    url=comment.url,
                    review_comment_id=comment.id,
                )
            )

    reference_filter = []
    if pr_ids:
        reference_filter.append(IssueReference.pull_request_id.in_(pr_ids))
    if commit_ids:
        reference_filter.append(IssueReference.commit_id.in_(commit_ids))
    if reference_filter:
        issues = tuple(
            session.scalars(
                select(Issue)
                .join(IssueReference, IssueReference.issue_id == Issue.id)
                .where(or_(*reference_filter))
                .distinct()
                .order_by(Issue.number)
            )
        )
    else:
        issues = ()
    for issue in issues:
        if issue.title.strip():
            candidates.append(
                EvidenceSnippet(
                    id=f"issue:{issue.number}:title",
                    source_type="issue",
                    text=issue.title,
                    source_field="title",
                    url=issue.url,
                    issue_id=issue.id,
                )
            )
        if issue.body and issue.body.strip():
            candidates.append(
                EvidenceSnippet(
                    id=f"issue:{issue.number}:body",
                    source_type="issue",
                    text=issue.body,
                    source_field="body",
                    url=issue.url,
                    issue_id=issue.id,
                )
            )

    unique: dict[str, EvidenceSnippet] = {}
    for snippet in candidates:
        unique.setdefault(snippet.id, snippet)
    candidates = list(unique.values())
    omitted_count = max(0, len(candidates) - max_snippets)
    selected = candidates[:max_snippets]
    snippets: list[EvidenceSnippet] = []
    truncated_count = 0
    for snippet in selected:
        if len(snippet.text) > max_chars_per_snippet:
            truncated_count += 1
            snippet = EvidenceSnippet(
                id=snippet.id,
                source_type=snippet.source_type,
                text=snippet.text[:max_chars_per_snippet],
                source_field=snippet.source_field,
                url=snippet.url,
                commit_id=snippet.commit_id,
                pull_request_id=snippet.pull_request_id,
                review_comment_id=snippet.review_comment_id,
                issue_id=snippet.issue_id,
            )
        snippets.append(snippet)
    return EvidenceBundle(
        symbol_id=symbol.id,
        qualified_name=symbol.qualified_name,
        kind=symbol.kind,
        events=events,
        snippets=tuple(snippets),
        truncated=bool(truncated_count or omitted_count),
        truncated_snippet_count=truncated_count,
        omitted_snippet_count=omitted_count,
    )
