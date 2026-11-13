from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy import Table, delete, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from excavator.core.evidence import EpistemicLabel, EvidenceLevel, label_for_level
from excavator.infra.db.models import (
    Analysis,
    Commit,
    EvidenceLink,
    Issue,
    IssueReference,
    PullRequest,
    Repository,
    ReviewComment,
    Symbol,
    SymbolVersion,
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


def _pull_request(repository_id: int) -> PullRequest:
    return PullRequest(
        repository_id=repository_id,
        number=1,
        title="Improve the parser",
        body="Description",
        state="open",
        merged=False,
        merge_method="unknown",
        base_ref="main",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
        url="https://github.com/octocat/hello-world/pull/1",
    )


def _issue(repository_id: int) -> Issue:
    return Issue(
        repository_id=repository_id,
        number=1,
        title="Track a bug",
        body="Description",
        state="open",
        created_at=datetime(2026, 1, 3, tzinfo=UTC),
        url="https://github.com/octocat/hello-world/issues/1",
    )


def _review_comment(pull_request_id: int) -> ReviewComment:
    return ReviewComment(
        github_id=1001,
        pull_request_id=pull_request_id,
        path="src/parser.py",
        diff_hunk="@@ -1 +1 @@\n-old\n+new",
        commit_sha="a" * 40,
        original_commit_sha="b" * 40,
        body="Please update this.",
        created_at=datetime(2026, 1, 4, tzinfo=UTC),
        updated_at=datetime(2026, 1, 4, tzinfo=UTC),
        url="https://github.com/octocat/hello-world/pull/1#discussion_r1001",
    )


def _symbol(repository_id: int) -> Symbol:
    return Symbol(
        repository_id=repository_id,
        language="python",
        kind="function",
        qualified_name="excavator.parse",
        current_path="src/parser.py",
        status="exists",
    )


def _symbol_version(symbol_id: int, commit_id: int) -> SymbolVersion:
    return SymbolVersion(
        symbol_id=symbol_id,
        commit_id=commit_id,
        path="src/parser.py",
        qualified_name="excavator.parse",
        start_line=1,
        end_line=3,
        body_hash="b" * 64,
        parse_status="ok",
        lineage_method="exact",
    )


def _analysis(symbol_id: int) -> Analysis:
    return Analysis(
        symbol_id=symbol_id,
        analyzed_commit_sha="a" * 40,
        outcome="insufficient_evidence",
        insufficient_reason="No matching evidence",
    )


def _evidence_link(analysis_id: int, commit_id: int) -> EvidenceLink:
    return EvidenceLink(
        analysis_id=analysis_id,
        commit_id=commit_id,
        source_field="message",
        level="direct",
        method="commit_message",
        epistemic_label="verified",
        quote_text="Initial",
        quote_start=0,
        quote_end=7,
        url="https://github.com/octocat/hello-world/commit/" + "a" * 40,
    )


def _issue_reference(issue_id: int, commit_id: int) -> IssueReference:
    return IssueReference(
        issue_id=issue_id,
        commit_id=commit_id,
        method="plain_reference",
    )


def _persist_repository_and_commit(session: Session) -> Commit:
    repository = _repository()
    session.add(repository)
    session.flush()
    commit = _commit(repository.id)
    session.add(commit)
    session.flush()
    return commit


def _persist_evidence_context(
    session: Session,
) -> tuple[Repository, Commit, PullRequest, ReviewComment, Issue, Analysis]:
    repository = _repository()
    session.add(repository)
    session.flush()
    commit = _commit(repository.id)
    pull_request = _pull_request(repository.id)
    issue = _issue(repository.id)
    session.add_all([commit, pull_request, issue])
    session.flush()
    comment = _review_comment(pull_request.id)
    session.add(comment)
    symbol = _symbol(repository.id)
    session.add(symbol)
    session.flush()
    analysis = _analysis(symbol.id)
    session.add(analysis)
    session.flush()
    return repository, commit, pull_request, comment, issue, analysis


def test_evidence_tables_create_successfully_on_sqlite(engine: Engine) -> None:
    table_names = set(inspect(engine).get_table_names())

    assert {
        "symbols",
        "symbol_versions",
        "analyses",
        "evidence_links",
        "issue_references",
    }.issubset(table_names)


@pytest.mark.parametrize(
    ("field", "value"),
    [("kind", "variable"), ("status", "missing")],
)
def test_symbol_checks_reject_bad_values(
    engine: Engine,
    field: str,
    value: str,
) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        symbol = _symbol(repository.id)
        setattr(symbol, field, value)
        session.add(symbol)

        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("parse_status", "failed"),
        ("lineage_method", "guessed"),
    ],
)
def test_symbol_version_enum_checks_reject_bad_values(
    engine: Engine,
    field: str,
    value: str,
) -> None:
    with Session(engine) as session:
        commit = _persist_repository_and_commit(session)
        symbol = _symbol(commit.repository_id)
        session.add(symbol)
        session.flush()
        version = _symbol_version(symbol.id, commit.id)
        setattr(version, field, value)
        session.add(version)

        with pytest.raises(IntegrityError):
            session.commit()


def test_symbol_version_line_range_check_rejects_bad_values(engine: Engine) -> None:
    with Session(engine) as session:
        commit = _persist_repository_and_commit(session)
        symbol = _symbol(commit.repository_id)
        session.add(symbol)
        session.flush()
        version = _symbol_version(symbol.id, commit.id)
        version.start_line = 0
        session.add(version)

        with pytest.raises(IntegrityError):
            session.commit()


def test_ok_symbol_version_requires_location_and_hash(engine: Engine) -> None:
    with Session(engine) as session:
        commit = _persist_repository_and_commit(session)
        symbol = _symbol(commit.repository_id)
        session.add(symbol)
        session.flush()
        version = _symbol_version(symbol.id, commit.id)
        version.start_line = None
        version.end_line = None
        version.body_hash = None
        session.add(version)

        with pytest.raises(IntegrityError):
            session.commit()


def test_syntax_error_symbol_version_accepts_missing_location_and_hash(
    engine: Engine,
) -> None:
    with Session(engine) as session:
        commit = _persist_repository_and_commit(session)
        symbol = _symbol(commit.repository_id)
        session.add(symbol)
        session.flush()
        version = _symbol_version(symbol.id, commit.id)
        version.start_line = None
        version.end_line = None
        version.body_hash = None
        version.parse_status = "syntax_error"
        session.add(version)
        session.commit()


def test_duplicate_symbol_version_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        commit = _persist_repository_and_commit(session)
        symbol = _symbol(commit.repository_id)
        session.add(symbol)
        session.flush()
        session.add_all(
            [
                _symbol_version(symbol.id, commit.id),
                _symbol_version(symbol.id, commit.id),
            ]
        )

        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        ("insufficient_evidence", None),
        ("evidence_found", "Unexpected reason"),
    ],
)
def test_analysis_reason_must_match_outcome(
    engine: Engine,
    outcome: str,
    reason: str | None,
) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        symbol = _symbol(repository.id)
        session.add(symbol)
        session.flush()
        analysis = Analysis(
            symbol_id=symbol.id,
            analyzed_commit_sha="a" * 40,
            outcome=outcome,
            insufficient_reason=reason,
        )
        session.add(analysis)

        with pytest.raises(IntegrityError):
            session.commit()


def test_analysis_commit_sha_length_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        symbol = _symbol(repository.id)
        session.add(symbol)
        session.flush()
        session.add(
            Analysis(
                symbol_id=symbol.id,
                analyzed_commit_sha="a" * 39,
                outcome="evidence_found",
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()


def test_analysis_outcome_check_rejects_bad_value(engine: Engine) -> None:
    with Session(engine) as session:
        repository = _repository()
        session.add(repository)
        session.flush()
        symbol = _symbol(repository.id)
        session.add(symbol)
        session.flush()
        session.add(
            Analysis(
                symbol_id=symbol.id,
                analyzed_commit_sha="a" * 40,
                outcome="unknown",
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()


def test_evidence_link_requires_exactly_one_source(engine: Engine) -> None:
    with Session(engine) as session:
        _, _, _, _, _, analysis = _persist_evidence_context(session)
        link = EvidenceLink(
            analysis_id=analysis.id,
            source_field="message",
            level="direct",
            method="commit_message",
            epistemic_label="verified",
            quote_text="Initial",
            quote_start=0,
            quote_end=7,
            url="https://example.test/commit",
        )
        session.add(link)

        with pytest.raises(IntegrityError):
            session.commit()


def test_evidence_link_rejects_two_sources(engine: Engine) -> None:
    with Session(engine) as session:
        _, commit, _, _, _, analysis = _persist_evidence_context(session)
        link = _evidence_link(analysis.id, commit.id)
        link.pull_request_id = 1
        session.add(link)

        with pytest.raises(IntegrityError):
            session.commit()


def test_evidence_link_source_field_mismatches_are_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        _, commit, _, _, _, analysis = _persist_evidence_context(session)
        link = _evidence_link(analysis.id, commit.id)
        link.source_field = "title"
        session.add(link)

        with pytest.raises(IntegrityError):
            session.commit()

    with Session(engine) as session:
        _, _, pull_request, comment, _, analysis = _persist_evidence_context(session)
        link = EvidenceLink(
            analysis_id=analysis.id,
            review_comment_id=comment.id,
            source_field="title",
            level="direct",
            method="review",
            epistemic_label="verified",
            quote_text="Please",
            quote_start=0,
            quote_end=6,
            url="https://example.test/comment",
        )
        del pull_request
        session.add(link)

        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("level", "unknown"),
        ("epistemic_label", "uncertain"),
    ],
)
def test_evidence_link_vocabulary_checks_reject_bad_values(
    engine: Engine,
    field: str,
    value: str,
) -> None:
    with Session(engine) as session:
        _, commit, _, _, _, analysis = _persist_evidence_context(session)
        link = _evidence_link(analysis.id, commit.id)
        setattr(link, field, value)
        session.add(link)

        with pytest.raises(IntegrityError):
            session.commit()


def test_evidence_link_quote_checks_reject_bad_values(engine: Engine) -> None:
    with Session(engine) as session:
        _, commit, _, _, _, analysis = _persist_evidence_context(session)
        link = _evidence_link(analysis.id, commit.id)
        link.quote_end = 8
        session.add(link)

        with pytest.raises(IntegrityError):
            session.commit()


def test_evidence_link_quote_offsets_are_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        _, commit, _, _, _, analysis = _persist_evidence_context(session)
        link = _evidence_link(analysis.id, commit.id)
        link.quote_start = -1
        session.add(link)

        with pytest.raises(IntegrityError):
            session.commit()


def test_evidence_link_unicode_quote_round_trips_verbatim(engine: Engine) -> None:
    quote = "café\nsecond"
    with Session(engine) as session:
        _, commit, _, _, _, analysis = _persist_evidence_context(session)
        link = _evidence_link(analysis.id, commit.id)
        link.quote_text = quote
        link.quote_start = 0
        link.quote_end = len(quote)
        session.add(link)
        session.commit()
        stored = session.get(EvidenceLink, link.id)

    assert stored is not None
    assert stored.quote_text == quote


@pytest.mark.parametrize(
    ("level", "label"),
    [(level.value, label.value) for level in EvidenceLevel for label in EpistemicLabel],
)
def test_evidence_link_label_drift_matches_core_vocabulary(
    engine: Engine,
    level: str,
    label: str,
) -> None:
    with Session(engine) as session:
        _, commit, _, _, _, analysis = _persist_evidence_context(session)
        link = _evidence_link(analysis.id, commit.id)
        link.level = level
        link.epistemic_label = label
        session.add(link)

        matches_core = label == label_for_level(EvidenceLevel(level)).value
        if matches_core:
            session.commit()
        else:
            with pytest.raises(IntegrityError):
                session.commit()


def test_issue_reference_requires_exactly_one_source(engine: Engine) -> None:
    with Session(engine) as session:
        _, _, _, _, issue, _ = _persist_evidence_context(session)
        session.add(IssueReference(issue_id=issue.id, method="plain_reference"))

        with pytest.raises(IntegrityError):
            session.commit()


def test_issue_reference_rejects_two_sources(engine: Engine) -> None:
    with Session(engine) as session:
        _, commit, pull_request, _, issue, _ = _persist_evidence_context(session)
        session.add(
            IssueReference(
                commit_id=commit.id,
                pull_request_id=pull_request.id,
                issue_id=issue.id,
                method="plain_reference",
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()


def test_issue_reference_method_check_rejects_bad_value(engine: Engine) -> None:
    with Session(engine) as session:
        _, commit, _, _, issue, _ = _persist_evidence_context(session)
        session.add(
            IssueReference(
                commit_id=commit.id,
                issue_id=issue.id,
                method="inferred",
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()


def test_issue_reference_commit_unique_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        _, commit, _, _, issue, _ = _persist_evidence_context(session)
        session.add_all(
            [
                _issue_reference(issue.id, commit.id),
                _issue_reference(issue.id, commit.id),
            ]
        )

        with pytest.raises(IntegrityError):
            session.commit()


def test_issue_reference_pull_request_unique_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        _, _, pull_request, _, issue, _ = _persist_evidence_context(session)
        session.add_all(
            [
                IssueReference(
                    pull_request_id=pull_request.id,
                    issue_id=issue.id,
                    method="plain_reference",
                ),
                IssueReference(
                    pull_request_id=pull_request.id,
                    issue_id=issue.id,
                    method="plain_reference",
                ),
            ]
        )

        with pytest.raises(IntegrityError):
            session.commit()


def test_foreign_key_violations_are_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        session.add(
            Symbol(
                repository_id=999,
                language="python",
                kind="function",
                qualified_name="missing",
                status="exists",
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()


def test_cascades_remove_evidence_graph_rows(engine: Engine) -> None:
    with Session(engine) as session:
        repository, commit, _, _, _, analysis = _persist_evidence_context(session)
        symbol = session.execute(select(Symbol)).scalar_one()
        version = _symbol_version(symbol.id, commit.id)
        session.add(version)
        session.add(_evidence_link(analysis.id, commit.id))
        session.commit()

        session.execute(delete(Repository).where(Repository.id == repository.id))
        session.commit()

        assert session.execute(select(Symbol)).scalars().all() == []
        assert session.execute(select(SymbolVersion)).scalars().all() == []
        assert session.execute(select(Analysis)).scalars().all() == []
        assert session.execute(select(EvidenceLink)).scalars().all() == []


def test_deleting_source_row_removes_evidence_links(engine: Engine) -> None:
    with Session(engine) as session:
        _, commit, _, _, _, analysis = _persist_evidence_context(session)
        session.add(_evidence_link(analysis.id, commit.id))
        session.commit()

        session.execute(delete(Commit).where(Commit.id == commit.id))
        session.commit()

        assert session.execute(select(EvidenceLink)).scalars().all() == []


def test_constraint_and_index_names_fit_postgresql_limit() -> None:
    tables = [
        cast(Table, Symbol.__table__),
        cast(Table, SymbolVersion.__table__),
        cast(Table, Analysis.__table__),
        cast(Table, EvidenceLink.__table__),
        cast(Table, IssueReference.__table__),
    ]
    names = {
        name
        for table in tables
        for name in [
            *(constraint.name for constraint in table.constraints),
            *(index.name for index in table.indexes),
        ]
        if isinstance(name, str)
    }

    assert all(len(name) <= 63 for name in names)


def test_evidence_constraint_names_are_exact() -> None:
    expected_names = {
        "ck_symbols_kind",
        "ck_symbols_status",
        "uq_symbol_versions_symbol_id_commit_id",
        "ck_symbol_versions_parse_status",
        "ck_symbol_versions_lineage_method",
        "ck_symbol_versions_line_range",
        "ck_symbol_versions_ok_requires_location",
        "ck_analyses_outcome",
        "ck_analyses_reason_matches_outcome",
        "ck_analyses_commit_sha_length",
        "ck_evidence_links_exactly_one_source",
        "ck_evidence_links_source_field",
        "ck_evidence_links_level",
        "ck_evidence_links_epistemic_label",
        "ck_evidence_links_level_label_match",
        "ck_evidence_links_quote_offsets",
        "ck_evidence_links_quote_length",
        "ck_issue_references_exactly_one_source",
        "ck_issue_references_method",
        "uq_issue_references_pull_request_id_issue_id_method",
        "uq_issue_references_commit_id_issue_id_method",
    }
    tables = [
        cast(Table, Symbol.__table__),
        cast(Table, SymbolVersion.__table__),
        cast(Table, Analysis.__table__),
        cast(Table, EvidenceLink.__table__),
        cast(Table, IssueReference.__table__),
    ]
    actual_names = {
        constraint.name
        for table in tables
        for constraint in table.constraints
        if constraint.name in expected_names
    }

    assert actual_names == expected_names
