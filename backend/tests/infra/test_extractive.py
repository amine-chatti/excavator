from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
from excavator.infra.explain.extractive import extract_symbol_evidence


def _make_commit(
    session: Session,
    repository_id: int,
    sha_character: str,
    index: int,
    message: str,
) -> Commit:
    commit = Commit(
        repository_id=repository_id,
        sha=sha_character * 40,
        message=message,
        authored_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index),
        parent_shas=[],
        url=None,
    )
    session.add(commit)
    session.flush()
    return commit


def _add_version(
    session: Session,
    symbol_id: int,
    commit_id: int,
    path: str,
    qualified_name: str,
    body_hash: str,
) -> None:
    session.add(
        SymbolVersion(
            symbol_id=symbol_id,
            commit_id=commit_id,
            path=path,
            qualified_name=qualified_name,
            start_line=1,
            end_line=2,
            body_hash=body_hash * 64,
            parse_status="ok",
            lineage_method="exact",
        )
    )
    session.flush()


def _extract_context(session: Session) -> tuple[int, dict[tuple[str, str | int], list[str]]]:
    repository = Repository(owner="owner", name="extractive")
    session.add(repository)
    session.flush()
    symbol = Symbol(
        repository_id=repository.id,
        language="python",
        kind="function",
        qualified_name="pkg.lookup",
        current_path="pkg/lookup.py",
        status="exists",
    )
    session.add(symbol)
    session.flush()

    messages = {
        "a": "  Added the symbol. Second sentence! Trailing phrase without punctuation  ",
        "b": "Changed the body.",
        "c": "Renamed the symbol.",
        "d": "Moved the file.",
        "e": "No change in this version.",
        "f": "Removed the symbol.",
    }
    commits = {
        character: _make_commit(session, repository.id, character, index, messages[character])
        for index, character in enumerate(messages)
    }
    _add_version(session, symbol.id, commits["a"].id, "pkg/lookup.py", "pkg.lookup", "a")
    _add_version(session, symbol.id, commits["b"].id, "pkg/lookup.py", "pkg.lookup", "b")
    _add_version(
        session,
        symbol.id,
        commits["c"].id,
        "pkg/lookup.py",
        "pkg.lookup_renamed",
        "c",
    )
    _add_version(
        session,
        symbol.id,
        commits["d"].id,
        "new/lookup.py",
        "pkg.lookup_renamed",
        "c",
    )
    _add_version(
        session,
        symbol.id,
        commits["e"].id,
        "new/lookup.py",
        "pkg.lookup_renamed",
        "c",
    )
    _add_version(
        session,
        symbol.id,
        commits["f"].id,
        "new/lookup.py",
        "pkg.lookup_renamed",
        "c",
    )
    symbol.status = "deleted"

    pr = PullRequest(
        repository_id=repository.id,
        number=7,
        title="PR title sentence.",
        body="PR body sentence.",
        state="closed",
        merged=True,
        merged_at=datetime(2026, 1, 2, tzinfo=UTC),
        merge_method="merge",
        base_ref="main",
        head_sha=commits["b"].sha,
        author_login=None,
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
        url="https://github.com/owner/extractive/pull/7",
    )
    second_pr = PullRequest(
        repository_id=repository.id,
        number=8,
        title="Second PR title.",
        body=None,
        state="closed",
        merged=True,
        merged_at=datetime(2026, 1, 3, tzinfo=UTC),
        merge_method="merge",
        base_ref="main",
        head_sha=commits["e"].sha,
        author_login=None,
        created_at=datetime(2026, 1, 3, tzinfo=UTC),
        url="https://github.com/owner/extractive/pull/8",
    )
    session.add_all([pr, second_pr])
    session.flush()
    session.add_all(
        [
            PullRequestCommit(pull_request_id=pr.id, commit_id=commits["b"].id),
            PullRequestCommit(pull_request_id=pr.id, commit_id=commits["e"].id),
            PullRequestCommit(pull_request_id=second_pr.id, commit_id=commits["e"].id),
            ReviewComment(
                github_id=700,
                pull_request_id=pr.id,
                path="pkg/lookup.py",
                diff_hunk="@@ -1 +1 @@",
                commit_sha=commits["c"].sha,
                original_commit_sha=commits["c"].sha,
                body="Review comment sentence.",
                created_at=datetime(2026, 1, 4, tzinfo=UTC),
                updated_at=datetime(2026, 1, 4, tzinfo=UTC),
                url="https://github.com/owner/extractive/pull/7#comment-700",
            ),
            ReviewComment(
                github_id=701,
                pull_request_id=second_pr.id,
                path="new/lookup.py",
                diff_hunk="@@ -1 +1 @@",
                commit_sha="0" * 40,
                original_commit_sha="0" * 40,
                body="Fallback review comment.",
                created_at=datetime(2026, 1, 5, tzinfo=UTC),
                updated_at=datetime(2026, 1, 5, tzinfo=UTC),
                url="https://github.com/owner/extractive/pull/8#comment-701",
            ),
        ]
    )

    issues = [
        Issue(
            repository_id=repository.id,
            number=31,
            title="Issue combines lineage events.",
            body=None,
            state="closed",
            author_login=None,
            created_at=datetime(2026, 1, 6, tzinfo=UTC),
            closed_at=datetime(2026, 1, 7, tzinfo=UTC),
            url="https://github.com/owner/extractive/issues/31",
        ),
        Issue(
            repository_id=repository.id,
            number=32,
            title="Issue references a move.",
            body=None,
            state="open",
            author_login=None,
            created_at=datetime(2026, 1, 7, tzinfo=UTC),
            closed_at=None,
            url="https://github.com/owner/extractive/issues/32",
        ),
        Issue(
            repository_id=repository.id,
            number=33,
            title="Issue references the PR with no transition\nThe second line is exact.",
            body=None,
            state="open",
            author_login=None,
            created_at=datetime(2026, 1, 8, tzinfo=UTC),
            closed_at=None,
            url="https://github.com/owner/extractive/issues/33",
        ),
    ]
    session.add_all(issues)
    session.flush()
    session.add_all(
        [
            IssueReference(
                commit_id=commits["d"].id,
                issue_id=issues[0].id,
                method="plain_reference",
            ),
            IssueReference(
                pull_request_id=pr.id,
                issue_id=issues[0].id,
                method="plain_reference",
            ),
            IssueReference(
                commit_id=commits["d"].id,
                issue_id=issues[1].id,
                method="plain_reference",
            ),
            IssueReference(
                pull_request_id=second_pr.id,
                issue_id=issues[2].id,
                method="plain_reference",
            ),
        ]
    )
    session.flush()
    session.commit()

    sources: dict[tuple[str, str | int], list[str]] = {
        ("commit", commit.sha): [commit.message] for commit in commits.values()
    }
    sources.update(
        {
            ("pull_request", 7): [pr.title, pr.body or ""],
            ("pull_request", 8): [second_pr.title],
            ("review_comment", 700): ["Review comment sentence."],
            ("review_comment", 701): ["Fallback review comment."],
            ("issue", 31): ["Issue combines lineage events."],
            ("issue", 32): ["Issue references a move."],
            ("issue", 33): [
                "Issue references the PR with no transition\nThe second line is exact."
            ],
        }
    )
    return symbol.id, sources


def test_extractive_evidence_covers_sources_events_order_and_verbatim_text(
    engine: Engine,
) -> None:
    with Session(engine) as session:
        symbol_id, sources = _extract_context(session)

        extracts = extract_symbol_evidence(session, symbol_id)
        repeated = extract_symbol_evidence(session, symbol_id)

        assert extracts == repeated
        assert {extract.source_kind for extract in extracts} == {
            "commit",
            "pull_request",
            "review_comment",
            "issue",
        }
        assert [extract.created_at for extract in extracts] == sorted(
            extract.created_at for extract in extracts
        )
        assert all(extract.label == "quote" for extract in extracts)
        assert all(extract.epistemic_label == "verified" for extract in extracts)
        for extract in extracts:
            source_texts = sources[(extract.source_kind, extract.reference)]
            assert any(extract.excerpt in source for source in source_texts)

        event_by_commit = {
            extract.reference: extract.lineage_event
            for extract in extracts
            if extract.source_kind == "commit"
        }
        assert event_by_commit == {
            "a" * 40: "added",
            "b" * 40: "modified",
            "c" * 40: "renamed",
            "d" * 40: "moved",
            "e" * 40: None,
            "f" * 40: "removed",
        }
        assert next(
            item for item in extracts if item.source_kind == "pull_request"
        ).lineage_event == ("modified")
        assert (
            next(
                item
                for item in extracts
                if item.source_kind == "review_comment" and item.reference == 700
            ).lineage_event
            == "renamed"
        )
        assert (
            next(
                item
                for item in extracts
                if item.source_kind == "review_comment" and item.reference == 701
            ).lineage_event
            is None
        )
        assert (
            next(
                item for item in extracts if item.source_kind == "issue" and item.reference == 31
            ).lineage_event
            is None
        )
        assert (
            next(
                item for item in extracts if item.source_kind == "issue" and item.reference == 32
            ).lineage_event
            == "moved"
        )
        assert extracts[0].excerpt == "Added the symbol."
        assert extracts[1].excerpt == "Second sentence!"
        assert extracts[2].excerpt == "Trailing phrase without punctuation"
        assert [
            item.excerpt
            for item in extracts
            if item.source_kind == "issue" and item.reference == 33
        ] == [
            "Issue references the PR with no transition",
            "The second line is exact.",
        ]


def test_extractive_evidence_is_empty_without_source_text(engine: Engine) -> None:
    with Session(engine) as session:
        repository = Repository(owner="owner", name="empty-extractive")
        session.add(repository)
        session.flush()
        symbol = Symbol(
            repository_id=repository.id,
            language="python",
            kind="function",
            qualified_name="pkg.empty",
            current_path="pkg/empty.py",
            status="exists",
        )
        commit = Commit(
            repository_id=repository.id,
            sha="9" * 40,
            message="  ",
            authored_at=datetime(2026, 1, 1, tzinfo=UTC),
            parent_shas=[],
            url=None,
        )
        session.add_all([symbol, commit])
        session.flush()
        _add_version(session, symbol.id, commit.id, "pkg/empty.py", "pkg.empty", "9")

        assert extract_symbol_evidence(session, symbol.id) == []
