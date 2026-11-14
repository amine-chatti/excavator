from __future__ import annotations

import sys
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from excavator.infra.db.models import (
    Commit,
    Issue,
    IssueReference,
    PullRequest,
    PullRequestCommit,
    ReviewComment,
    Symbol,
    SymbolVersion,
)
from excavator.infra.explain.bundle import EvidenceSnippet, build_evidence_bundle

SourceKind = Literal["commit", "pull_request", "review_comment", "issue"]
LineageEvent = Literal["added", "modified", "renamed", "moved", "removed"]


@dataclass(frozen=True, slots=True)
class ExtractiveExtract:
    source_kind: SourceKind
    reference: str | int
    excerpt: str
    lineage_event: LineageEvent | None
    created_at: datetime
    label: Literal["quote"] = "quote"
    epistemic_label: Literal["verified"] = "verified"


def _sentences(text: str) -> tuple[str, ...]:
    excerpts: list[str] = []
    start = 0
    for index, character in enumerate(text):
        if character in ".!?" and (index + 1 == len(text) or text[index + 1].isspace()):
            end = index + 1
        elif character in "\r\n":
            end = index
        else:
            continue
        excerpt_start = start
        while excerpt_start < end and text[excerpt_start].isspace():
            excerpt_start += 1
        if excerpt_start < end:
            excerpts.append(text[excerpt_start:end])
        start = index + 1
    excerpt_start = start
    while excerpt_start < len(text) and text[excerpt_start].isspace():
        excerpt_start += 1
    excerpt_end = len(text)
    while excerpt_end > excerpt_start and text[excerpt_end - 1].isspace():
        excerpt_end -= 1
    if excerpt_start < excerpt_end:
        excerpts.append(text[excerpt_start:excerpt_end])
    return tuple(excerpts)


def _single_event(events: Iterable[LineageEvent | None]) -> LineageEvent | None:
    known_events = {event for event in events if event is not None}
    if len(known_events) == 1:
        return next(iter(known_events))
    return None


def _version_events(
    session: Session,
    symbol_id: int,
) -> tuple[dict[int, LineageEvent | None], dict[str, LineageEvent | None]]:
    symbol = session.get_one(Symbol, symbol_id)
    rows = session.execute(
        select(SymbolVersion, Commit)
        .join(Commit, Commit.id == SymbolVersion.commit_id)
        .where(SymbolVersion.symbol_id == symbol_id)
        .order_by(SymbolVersion.id)
    ).all()
    by_commit_id: dict[int, LineageEvent | None] = {}
    by_sha: dict[str, LineageEvent | None] = {}
    previous: SymbolVersion | None = None
    for index, (version, commit) in enumerate(rows):
        event: LineageEvent | None
        if symbol.status == "deleted" and index == len(rows) - 1:
            event = "removed"
        elif previous is None:
            event = "added"
        elif previous.path != version.path:
            event = "moved"
        elif previous.qualified_name != version.qualified_name:
            event = "renamed"
        elif previous.body_hash != version.body_hash:
            event = "modified"
        else:
            event = None
        by_commit_id[commit.id] = event
        by_sha[commit.sha] = event
        previous = version
    return by_commit_id, by_sha


def _linked_events(
    session: Session,
    commit_events: dict[int, LineageEvent | None],
) -> dict[int, list[LineageEvent | None]]:
    pull_request_events: dict[int, list[LineageEvent | None]] = defaultdict(list)
    relations = session.scalars(
        select(PullRequestCommit).where(PullRequestCommit.commit_id.in_(commit_events))
    )
    for relation in relations:
        pull_request_events[relation.pull_request_id].append(commit_events[relation.commit_id])

    return pull_request_events


def _source_details(
    session: Session,
    snippet: EvidenceSnippet,
    commit_events: dict[int, LineageEvent | None],
    events_by_sha: dict[str, LineageEvent | None],
    pull_request_events: dict[int, list[LineageEvent | None]],
) -> tuple[SourceKind, str | int, datetime, LineageEvent | None]:
    if snippet.commit_id is not None:
        commit = session.get_one(Commit, snippet.commit_id)
        return "commit", commit.sha, commit.authored_at, commit_events[commit.id]
    if snippet.pull_request_id is not None:
        pull_request = session.get_one(PullRequest, snippet.pull_request_id)
        return (
            "pull_request",
            pull_request.number,
            pull_request.created_at,
            _single_event(pull_request_events[pull_request.id]),
        )
    if snippet.review_comment_id is not None:
        comment = session.get_one(ReviewComment, snippet.review_comment_id)
        if comment.commit_sha in events_by_sha:
            event = events_by_sha[comment.commit_sha]
        else:
            event = _single_event(pull_request_events[comment.pull_request_id])
        return "review_comment", comment.github_id, comment.created_at, event
    issue = session.get_one(Issue, snippet.issue_id)
    references = session.scalars(select(IssueReference).where(IssueReference.issue_id == issue.id))
    issue_events: list[LineageEvent | None] = []
    for reference in references:
        if reference.commit_id is not None:
            issue_events.append(commit_events[reference.commit_id])
        elif reference.pull_request_id is not None:
            issue_events.extend(pull_request_events[reference.pull_request_id])
    return "issue", issue.number, issue.created_at, _single_event(issue_events)


def extract_symbol_evidence(session: Session, symbol_id: int) -> list[ExtractiveExtract]:
    bundle = build_evidence_bundle(
        session,
        symbol_id,
        max_snippets=sys.maxsize,
        max_chars_per_snippet=sys.maxsize,
    )
    if not bundle.snippets:
        return []
    commit_events, events_by_sha = _version_events(session, symbol_id)
    pull_request_events = _linked_events(session, commit_events)
    source_order: dict[SourceKind, int] = {
        "commit": 0,
        "pull_request": 1,
        "review_comment": 2,
        "issue": 3,
    }
    ordered: list[tuple[tuple[datetime, int, str, str, int], ExtractiveExtract]] = []
    for snippet in bundle.snippets:
        source_kind, reference, created_at, lineage_event = _source_details(
            session,
            snippet,
            commit_events,
            events_by_sha,
            pull_request_events,
        )
        for index, excerpt in enumerate(_sentences(snippet.text)):
            extract = ExtractiveExtract(
                source_kind=source_kind,
                reference=reference,
                excerpt=excerpt,
                lineage_event=lineage_event,
                created_at=created_at,
            )
            ordered.append(
                (
                    (created_at, source_order[source_kind], str(reference), snippet.id, index),
                    extract,
                )
            )
    ordered.sort(key=lambda item: item[0])
    return [extract for _, extract in ordered]
