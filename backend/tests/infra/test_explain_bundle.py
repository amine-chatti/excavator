from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.engine import Engine
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
from excavator.infra.explain.bundle import build_evidence_bundle


def _context(
    session: Session,
    *,
    message: str = "Changed parser strategy after benchmark",
    title: str = "Improve parser",
    body: str | None = "The benchmark showed a slow path.",
    review_body: str = "This removes repeated parsing.",
    issue_title: str = "Parser is slow",
    issue_body: str | None = "Avoid the repeated scan.",
) -> tuple[int, int, int, int, int]:
    repository = Repository(owner="owner", name="repo")
    session.add(repository)
    session.flush()
    commit = Commit(
        repository_id=repository.id,
        sha="a" * 40,
        message=message,
        authored_at=datetime(2026, 1, 1, tzinfo=UTC),
        parent_shas=[],
        url=None,
    )
    symbol = Symbol(
        repository_id=repository.id,
        language="python",
        kind="function",
        qualified_name="pkg.parse",
        current_path="pkg/parser.py",
        status="exists",
    )
    session.add_all([commit, symbol])
    session.flush()
    version = SymbolVersion(
        symbol_id=symbol.id,
        commit_id=commit.id,
        path="pkg/parser.py",
        qualified_name="pkg.parse",
        start_line=1,
        end_line=3,
        body_hash="b" * 64,
        parse_status="ok",
        lineage_method="exact",
    )
    pr = PullRequest(
        repository_id=repository.id,
        number=7,
        title=title,
        body=body,
        state="open",
        merged=False,
        merged_at=None,
        merge_method="unknown",
        base_ref="main",
        author_login=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        url="https://github.com/owner/repo/pull/7",
    )
    issue = Issue(
        repository_id=repository.id,
        number=9,
        title=issue_title,
        body=issue_body,
        state="open",
        author_login=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        closed_at=None,
        url="https://github.com/owner/repo/issues/9",
    )
    session.add_all([version, pr, issue])
    session.flush()
    session.add_all(
        [
            PullRequestCommit(pull_request_id=pr.id, commit_id=commit.id),
            IssueReference(pull_request_id=pr.id, issue_id=issue.id, method="plain_reference"),
            ReviewComment(
                github_id=700,
                pull_request_id=pr.id,
                path="pkg/parser.py",
                diff_hunk="@@ -1 +1 @@",
                commit_sha=commit.sha,
                original_commit_sha=commit.sha,
                body=review_body,
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                updated_at=datetime(2026, 1, 1, tzinfo=UTC),
                url="https://github.com/owner/repo/pull/7#comment-700",
            ),
        ]
    )
    session.flush()
    return repository.id, symbol.id, commit.id, pr.id, issue.id


def test_build_bundle_collects_sources_in_deterministic_order(engine: Engine) -> None:
    with Session(engine) as session:
        _, symbol_id, _, _, _ = _context(session)
        bundle = build_evidence_bundle(session, symbol_id)

        assert bundle.qualified_name == "pkg.parse"
        assert bundle.kind == "function"
        assert bundle.events[0].commit_sha == "a" * 40
        assert bundle.events[0].lineage_method == "exact"
        assert [snippet.id for snippet in bundle.snippets] == [
            f"commit:{'a' * 40}:message",
            "pr:7:title",
            "pr:7:body",
            "review:700",
            "issue:9:title",
            "issue:9:body",
        ]
        assert [snippet.source_type for snippet in bundle.snippets] == [
            "commit_message",
            "pull_request",
            "pull_request",
            "review_comment",
            "issue",
            "issue",
        ]
        assert bundle.truncated is False
        assert bundle.truncated_snippet_count == 0
        assert bundle.omitted_snippet_count == 0
        commit_snippet = bundle.snippets[0]
        assert commit_snippet.url == "https://github.com/owner/repo/commit/" + "a" * 40


def test_bundle_truncates_text_and_caps_count(engine: Engine) -> None:
    with Session(engine) as session:
        _, symbol_id, _, _, _ = _context(session)
        bundle = build_evidence_bundle(
            session,
            symbol_id,
            max_snippets=2,
            max_chars_per_snippet=8,
        )

        assert len(bundle.snippets) == 2
        assert bundle.snippets[0].text == "Changed "
        assert bundle.truncated is True
        assert bundle.truncated_snippet_count == 2
        assert bundle.omitted_snippet_count == 4


def test_bundle_skips_empty_sources_and_can_cap_to_zero(engine: Engine) -> None:
    with Session(engine) as session:
        _, symbol_id, _, _, _ = _context(
            session,
            message=" ",
            title=" ",
            body=" ",
            review_body=" ",
            issue_title=" ",
            issue_body=" ",
        )
        bundle = build_evidence_bundle(session, symbol_id)
        assert bundle.snippets == ()
        assert bundle.events
        assert not bundle.truncated

        full = build_evidence_bundle(session, symbol_id, max_snippets=0)
        assert full.snippets == ()
        assert full.omitted_snippet_count == 0


def test_bundle_handles_no_linked_discussions_and_missing_symbol(engine: Engine) -> None:
    with Session(engine) as session:
        repository = Repository(owner="owner", name="empty")
        session.add(repository)
        session.flush()
        commit = Commit(
            repository_id=repository.id,
            sha="c" * 40,
            message="",
            authored_at=datetime(2026, 1, 1, tzinfo=UTC),
            parent_shas=[],
            url="https://github.com/owner/empty/commit/" + "c" * 40,
        )
        symbol = Symbol(
            repository_id=repository.id,
            language="python",
            kind="class",
            qualified_name="pkg.Empty",
            current_path=None,
            status="deleted",
        )
        session.add_all([commit, symbol])
        session.flush()
        session.add(
            SymbolVersion(
                symbol_id=symbol.id,
                commit_id=commit.id,
                path="pkg/empty.py",
                qualified_name="pkg.Empty",
                start_line=None,
                end_line=None,
                body_hash=None,
                parse_status="syntax_error",
                lineage_method="heuristic",
            )
        )
        session.flush()
        bundle = build_evidence_bundle(session, symbol.id)
        assert bundle.snippets == ()
        with pytest.raises(ValueError, match="symbol not found"):
            build_evidence_bundle(session, 999)
        with pytest.raises(ValueError, match="max_chars_per_snippet"):
            build_evidence_bundle(session, symbol.id, max_chars_per_snippet=0)


def test_bundle_without_versions_and_without_repository_url(
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with Session(engine) as session:
        repository_id, symbol_id, _, _, _ = _context(session)
        symbol = session.get(Symbol, symbol_id)
        assert symbol is not None
        empty_symbol = Symbol(
            repository_id=repository_id,
            language="python",
            kind="method",
            qualified_name="pkg.Empty.method",
            current_path=None,
            status="deleted",
        )
        session.add(empty_symbol)
        session.flush()
        empty_bundle = build_evidence_bundle(session, empty_symbol.id)
        assert empty_bundle.events == ()
        assert empty_bundle.snippets == ()

        original_get = session.get

        def without_repository(
            model: Any,
            ident: Any,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            if model is Repository:
                return None
            return original_get(model, ident, *args, **kwargs)

        monkeypatch.setattr(session, "get", without_repository)
        with pytest.raises(ValueError, match="symbol repository not found"):
            build_evidence_bundle(session, symbol.id)
