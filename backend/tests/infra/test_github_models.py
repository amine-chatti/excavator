from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy import Table, delete, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from excavator.infra.db.models import (
    Commit,
    FileChange,
    Issue,
    PullRequest,
    PullRequestCommit,
    Repository,
    ReviewComment,
)


def _repository() -> Repository:
    return Repository(owner="octocat", name="hello-world")


def _commit(repository_id: int) -> Commit:
    return Commit(
        repository_id=repository_id,
        sha="a" * 40,
        message="Initial commit",
        authored_at=datetime(2026, 1, 1, tzinfo=UTC),
        parent_shas=[],
        url="https://github.com/octocat/hello-world/commit/" + "a" * 40,
    )


def _pull_request(repository_id: int, number: int = 1) -> PullRequest:
    return PullRequest(
        repository_id=repository_id,
        number=number,
        title="Improve the parser",
        body="Description",
        state="open",
        merged=False,
        merge_method="unknown",
        base_ref="main",
        url="https://github.com/octocat/hello-world/pull/1",
    )


def _issue(repository_id: int, number: int = 1) -> Issue:
    return Issue(
        repository_id=repository_id,
        number=number,
        title="Track a bug",
        body="Description",
        state="open",
        url="https://github.com/octocat/hello-world/issues/1",
    )


def _review_comment(pull_request_id: int, github_id: int = 1001) -> ReviewComment:
    return ReviewComment(
        github_id=github_id,
        pull_request_id=pull_request_id,
        path="src/parser.py",
        diff_hunk="@@ -1,2 +1,2 @@\n-old\n+new",
        commit_sha="a" * 40,
        original_commit_sha="b" * 40,
        line=2,
        start_line=1,
        original_line=2,
        original_start_line=1,
        side="RIGHT",
        start_side="RIGHT",
        subject_type="line",
        body="Please update this.",
        url="https://github.com/octocat/hello-world/pull/1#discussion_r1001",
    )


def test_github_tables_create_successfully_on_sqlite(engine: Engine) -> None:
    table_names = set(inspect(engine).get_table_names())

    assert {
        "file_changes",
        "pull_requests",
        "pull_request_commits",
        "review_comments",
        "issues",
    }.issubset(table_names)


def test_duplicate_file_change_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        commit = _commit(repository.id)
        session.add(commit)
        session.flush()
        session.add_all(
            [
                FileChange(commit_id=commit.id, path="README.md", change_type="added"),
                FileChange(commit_id=commit.id, path="README.md", change_type="modified"),
            ]
        )

        with pytest.raises(IntegrityError):
            session.commit()


def test_duplicate_pull_request_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        session.add_all([_pull_request(repository.id), _pull_request(repository.id)])

        with pytest.raises(IntegrityError):
            session.commit()


def test_duplicate_review_comment_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        pull_request = _pull_request(repository.id)
        session.add(pull_request)
        session.flush()
        session.add_all(
            [
                _review_comment(pull_request.id),
                _review_comment(pull_request.id),
            ]
        )

        with pytest.raises(IntegrityError):
            session.commit()


def test_duplicate_issue_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        session.add_all([_issue(repository.id), _issue(repository.id)])

        with pytest.raises(IntegrityError):
            session.commit()


def test_invalid_change_type_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        commit = _commit(repository.id)
        session.add(commit)
        session.flush()
        session.add(FileChange(commit_id=commit.id, path="x", change_type="unknown"))

        with pytest.raises(IntegrityError):
            session.commit()


def test_invalid_pull_request_state_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        pull_request = _pull_request(repository.id)
        pull_request.state = "draft"
        session.add(pull_request)

        with pytest.raises(IntegrityError):
            session.commit()


def test_invalid_pull_request_merge_method_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        pull_request = _pull_request(repository.id)
        pull_request.merge_method = "manual"
        session.add(pull_request)

        with pytest.raises(IntegrityError):
            session.commit()


def test_invalid_pull_request_merge_sha_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        pull_request = _pull_request(repository.id)
        pull_request.merge_commit_sha = "a" * 39
        session.add(pull_request)

        with pytest.raises(IntegrityError):
            session.commit()


def test_invalid_review_comment_values_are_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        pull_request = _pull_request(repository.id)
        session.add(pull_request)
        session.flush()
        comment = _review_comment(pull_request.id)
        comment.side = "CENTER"
        session.add(comment)

        with pytest.raises(IntegrityError):
            session.commit()


def test_invalid_review_comment_start_side_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        pull_request = _pull_request(repository.id)
        session.add(pull_request)
        session.flush()
        comment = _review_comment(pull_request.id)
        comment.start_side = "CENTER"
        session.add(comment)

        with pytest.raises(IntegrityError):
            session.commit()


def test_invalid_review_comment_subject_type_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        pull_request = _pull_request(repository.id)
        session.add(pull_request)
        session.flush()
        comment = _review_comment(pull_request.id)
        comment.subject_type = "hunk"
        session.add(comment)

        with pytest.raises(IntegrityError):
            session.commit()


def test_invalid_review_comment_line_range_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        pull_request = _pull_request(repository.id)
        session.add(pull_request)
        session.flush()
        comment = _review_comment(pull_request.id)
        comment.start_line = 3
        comment.line = 2
        session.add(comment)

        with pytest.raises(IntegrityError):
            session.commit()


def test_invalid_issue_state_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        issue = _issue(repository.id)
        issue.state = "draft"
        session.add(issue)

        with pytest.raises(IntegrityError):
            session.commit()


def test_foreign_key_violations_are_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        session.add(_pull_request(repository_id=999))

        with pytest.raises(IntegrityError):
            session.commit()


def test_deleting_repository_cascades_through_github_data(engine: Engine) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        commit = _commit(repository.id)
        session.add(commit)
        session.flush()
        session.add(FileChange(commit_id=commit.id, path="README.md", change_type="added"))
        session.add(_pull_request(repository.id))
        session.add(_issue(repository.id))
        session.commit()

        session.execute(delete(Repository).where(Repository.id == repository.id))
        session.commit()

        assert session.execute(select(FileChange)).scalars().all() == []
        assert session.execute(select(PullRequest)).scalars().all() == []
        assert session.execute(select(Issue)).scalars().all() == []


def test_deleting_pull_request_cascades_to_comments_and_links(engine: Engine) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        commit = _commit(repository.id)
        session.add(commit)
        session.flush()
        pull_request = _pull_request(repository.id)
        session.add(pull_request)
        session.flush()
        session.add(_review_comment(pull_request.id))
        session.add(
            PullRequestCommit(
                pull_request_id=pull_request.id,
                commit_id=commit.id,
                ordinal=1,
            )
        )
        session.commit()

        session.execute(delete(PullRequest).where(PullRequest.id == pull_request.id))
        session.commit()

        assert session.execute(select(ReviewComment)).scalars().all() == []
        assert session.execute(select(PullRequestCommit)).scalars().all() == []


def test_github_text_fields_round_trip_verbatim(engine: Engine) -> None:
    title = "Unicode café\n\nTrailing whitespace   \n\t"
    body = "Body with emoji 🚀\nsecond line  "
    diff_hunk = "@@ -1 +1 @@\n-old  \n+new\t"

    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        pull_request = _pull_request(repository.id)
        pull_request.title = title
        pull_request.body = body
        session.add(pull_request)
        session.flush()
        comment = _review_comment(pull_request.id)
        comment.body = body
        comment.diff_hunk = diff_hunk
        session.add(comment)
        issue = _issue(repository.id)
        issue.title = title
        issue.body = body
        session.add(issue)
        session.commit()

        stored_pull_request = session.get(PullRequest, pull_request.id)
        stored_comment = session.get(ReviewComment, comment.id)
        stored_issue = session.get(Issue, issue.id)

    assert stored_pull_request is not None
    assert stored_comment is not None
    assert stored_issue is not None
    assert stored_pull_request.title == title
    assert stored_pull_request.body == body
    assert stored_comment.body == body
    assert stored_comment.diff_hunk == diff_hunk
    assert stored_issue.title == title
    assert stored_issue.body == body


def test_github_constraint_names_follow_expected_convention() -> None:
    expected_names = {
        "uq_file_changes_commit_id_path",
        "ck_file_changes_change_type",
        "uq_pull_requests_repository_id_number",
        "ck_pull_requests_state",
        "ck_pull_requests_merge_method",
        "pk_pull_request_commits",
        "uq_review_comments_github_id",
        "ck_review_comments_line_range",
        "uq_issues_repository_id_number",
        "ck_issues_state",
    }
    tables = [
        cast(Table, FileChange.__table__),
        cast(Table, PullRequest.__table__),
        cast(Table, PullRequestCommit.__table__),
        cast(Table, ReviewComment.__table__),
        cast(Table, Issue.__table__),
    ]
    actual_names = {
        constraint.name
        for table in tables
        for constraint in table.constraints
        if constraint.name in expected_names
    }

    assert actual_names == expected_names
