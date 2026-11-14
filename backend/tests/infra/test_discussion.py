from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
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
)
from excavator.infra.github_client import (
    GitHubClientError,
    GitHubRateLimitError,
    IssueData,
    ReviewCommentData,
)
from excavator.infra.persistence.discussion import (
    extract_issue_numbers,
    ingest_discussion,
    persist_issue_references,
    persist_issues,
    persist_review_comments,
)


def _issue(number: int) -> IssueData:
    return IssueData(
        number=number,
        title=f"Issue {number}",
        body=None,
        state="open",
        author_login=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        closed_at=None,
        url=f"https://github.com/owner/repo/issues/{number}",
    )


def _comment(github_id: int) -> ReviewCommentData:
    return ReviewCommentData(
        github_id=github_id,
        review_github_id=None,
        in_reply_to_github_id=None,
        path="src/file.py",
        diff_hunk="@@ -1 +1 @@",
        commit_sha="a" * 40,
        original_commit_sha="b" * 40,
        line=1,
        start_line=None,
        original_line=1,
        original_start_line=None,
        side="RIGHT",
        start_side=None,
        subject_type="line",
        body="review",
        author_login="octocat",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 2, tzinfo=UTC),
        url=f"https://github.com/owner/repo/pull/1#comment-{github_id}",
    )


def _repository(
    session: Session, body: str | None = "Fixes #11 and see #12"
) -> tuple[int, int, int]:
    repository = Repository(owner="owner", name="repo")
    session.add(repository)
    session.flush()
    pr = PullRequest(
        repository_id=repository.id,
        number=1,
        title="PR",
        body=body,
        state="open",
        merged=False,
        merged_at=None,
        merge_method="unknown",
        base_ref="main",
        author_login=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        url="https://github.com/owner/repo/pull/1",
    )
    commit = Commit(
        repository_id=repository.id,
        sha="c" * 40,
        message="resolves #13",
        authored_at=datetime(2026, 1, 1, tzinfo=UTC),
        parent_shas=[],
    )
    session.add_all([pr, commit])
    session.flush()
    session.add(PullRequestCommit(pull_request_id=pr.id, commit_id=commit.id))
    session.flush()
    return repository.id, pr.id, commit.id


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Fixes #123", (123,)),
        ("closes #1, RESOLVED #2", (1, 2)),
        ("Mention #8 and duplicate #8", (8,)),
        ("url https://github.com/x/y/issues/3 and #4", (4,)),
        ("`#5` and ```md\n#6\n``` plus #7", (7,)),
        ("Fix #10; closes #9", (9, 10)),
        ("no references here", ()),
        ("#0 and #abc", ()),
        ("https://x/#1", ()),
        ("~~~\n#21\n~~~ #22", (22,)),
    ],
)
def test_extract_issue_numbers(text: str, expected: tuple[int, ...]) -> None:
    assert extract_issue_numbers(text) == expected


def test_persist_review_comments_is_idempotent_and_skips_unknown_pr(engine: Engine) -> None:
    with Session(engine) as session:
        repository_id, pr_id, _ = _repository(session)
        values: dict[int, tuple[ReviewCommentData, ...]] = {
            1: (_comment(500),),
            999: (_comment(501),),
        }
        first = persist_review_comments(session, repository_id, values)
        session.commit()
        second = persist_review_comments(session, repository_id, values)
        assert first == second
        assert first.review_comment_count == 1
        assert first.skipped_pull_request_count == 1
        assert session.scalars(select(ReviewComment)).one().pull_request_id == pr_id


def test_persist_issues_and_references_are_idempotent(engine: Engine) -> None:
    with Session(engine) as session:
        repository_id, pr_id, commit_id = _repository(session)
        persisted = persist_issues(session, repository_id, (_issue(11), _issue(13)))
        ids = {number: row.id for number, row in persisted.items()}
        pr_refs: dict[int, tuple[tuple[int, str], ...]] = {
            pr_id: ((11, "closing_keyword"), (12, "plain_reference"))
        }
        commit_refs: dict[int, tuple[tuple[int, str], ...]] = {
            commit_id: ((13, "closing_keyword"),)
        }
        first = persist_issue_references(session, ids, pr_refs, commit_refs)
        session.commit()
        persisted_again = persist_issues(session, repository_id, (_issue(11), _issue(13)))
        second = persist_issue_references(
            session,
            {n: row.id for n, row in persisted_again.items()},
            pr_refs,
            commit_refs,
        )
        assert first == second == 2
        assert len(session.scalars(select(Issue)).all()) == 2
        refs = session.scalars(select(IssueReference).order_by(IssueReference.id)).all()
        assert [(r.method, r.pull_request_id, r.commit_id) for r in refs] == [
            ("closing_keyword", pr_id, None),
            ("closing_keyword", None, commit_id),
        ]


def test_ingest_continues_after_item_errors_and_records_failures(engine: Engine) -> None:
    with Session(engine) as session:
        repository_id, _, _ = _repository(session)

        class FakeClient:
            def list_review_comments(
                self, owner: str, name: str, number: int
            ) -> tuple[ReviewCommentData, ...]:
                return (_comment(800),)

            def get_issue(self, owner: str, name: str, number: int) -> IssueData | None:
                if number == 12:
                    raise GitHubClientError("failed")
                return _issue(number)

        result = ingest_discussion(session, repository_id, "owner", "repo", FakeClient())
        assert result.failed_items == ("issue:12",)
        assert result.review_comment_count == 1
        assert result.issue_count == 2
        assert result.issue_reference_count == 2


def test_ingest_distinguishes_closing_and_plain_references(engine: Engine) -> None:
    with Session(engine) as session:
        repository_id, _, _ = _repository(session)

        class FakeClient:
            def list_review_comments(
                self, owner: str, name: str, number: int
            ) -> tuple[ReviewCommentData, ...]:
                return ()

            def get_issue(self, owner: str, name: str, number: int) -> IssueData | None:
                return _issue(number)

        ingest_discussion(session, repository_id, "owner", "repo", FakeClient())
        references = session.scalars(select(IssueReference)).all()
        methods = {reference.issue_id: reference.method for reference in references}
        issues = {issue.number: issue.id for issue in session.scalars(select(Issue))}
        assert methods == {
            issues[11]: "closing_keyword",
            issues[12]: "plain_reference",
            issues[13]: "closing_keyword",
        }


def test_ingest_rate_limit_persists_prior_results_then_raises(engine: Engine) -> None:
    with Session(engine) as session:
        repository_id, _, _ = _repository(session, body="Fixes #11 and #12")

        class FakeClient:
            def list_review_comments(
                self, owner: str, name: str, number: int
            ) -> tuple[ReviewCommentData, ...]:
                return (_comment(801),)

            def get_issue(self, owner: str, name: str, number: int) -> IssueData | None:
                if number == 12:
                    raise GitHubRateLimitError("limited")
                return _issue(number)

        with pytest.raises(GitHubRateLimitError):
            ingest_discussion(session, repository_id, "owner", "repo", FakeClient())
        assert session.scalars(select(ReviewComment)).one().github_id == 801
        assert session.scalars(select(Issue)).one().number == 11
        assert session.scalars(select(IssueReference)).one().method == "closing_keyword"


def test_ingest_skips_pull_requests_without_body(engine: Engine) -> None:
    with Session(engine) as session:
        repository_id, _, _ = _repository(session, body=None)

        class FakeClient:
            def list_review_comments(
                self, owner: str, name: str, number: int
            ) -> tuple[ReviewCommentData, ...]:
                return ()

            def get_issue(self, owner: str, name: str, number: int) -> IssueData | None:
                return _issue(number)

        result = ingest_discussion(session, repository_id, "owner", "repo", FakeClient())
        assert result.issue_count == 1
