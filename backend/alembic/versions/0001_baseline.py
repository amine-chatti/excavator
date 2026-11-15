"""Create the initial Excavator schema."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("default_branch", sa.String(), nullable=True),
        sa.Column("indexing_status", sa.String(), nullable=False),
        sa.Column("head_sha_indexed", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_repositories"),
        sa.UniqueConstraint("owner", "name", name="uq_repositories_owner_name"),
        sa.CheckConstraint(
            "indexing_status IN ('pending', 'running', 'done', 'failed')",
            name="ck_repositories_indexing_status_values",
        ),
    )
    op.create_table(
        "commits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("sha", sa.String(length=40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("author_login", sa.String(), nullable=True),
        sa.Column("authored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("parent_shas", sa.JSON(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name="fk_commits_repository_id_repositories",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_commits"),
        sa.UniqueConstraint("repository_id", "sha", name="uq_commits_repository_id_sha"),
        sa.CheckConstraint("length(sha) = 40", name="ck_commits_sha_length"),
    )
    op.create_table(
        "issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("author_login", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name="fk_issues_repository_id_repositories",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_issues"),
        sa.UniqueConstraint("repository_id", "number", name="uq_issues_repository_id_number"),
        sa.CheckConstraint("state IN ('open', 'closed')", name="ck_issues_state"),
    )
    op.create_table(
        "pull_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("merged", sa.Boolean(), nullable=False),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("merge_commit_sha", sa.String(length=40), nullable=True),
        sa.Column("merge_method", sa.Text(), nullable=False),
        sa.Column("base_ref", sa.Text(), nullable=False),
        sa.Column("head_sha", sa.String(length=40), nullable=True),
        sa.Column("author_login", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name="fk_pull_requests_repository_id_repositories",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pull_requests"),
        sa.UniqueConstraint(
            "repository_id", "number", name="uq_pull_requests_repository_id_number"
        ),
        sa.CheckConstraint("state IN ('open', 'closed')", name="ck_pull_requests_state"),
        sa.CheckConstraint(
            "merge_method IN ('merge', 'squash', 'rebase', 'unknown')",
            name="ck_pull_requests_merge_method",
        ),
        sa.CheckConstraint(
            "merge_commit_sha IS NULL OR length(merge_commit_sha) = 40",
            name="ck_pull_requests_merge_commit_sha_length",
        ),
        sa.CheckConstraint(
            "head_sha IS NULL OR length(head_sha) = 40",
            name="ck_pull_requests_head_sha_length",
        ),
    )
    op.create_table(
        "symbols",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("qualified_name", sa.Text(), nullable=False),
        sa.Column("current_path", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name="fk_symbols_repository_id_repositories",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_symbols"),
        sa.CheckConstraint(
            "kind IN ('function', 'class', 'method')",
            name="ck_symbols_kind",
        ),
        sa.CheckConstraint("status IN ('exists', 'deleted')", name="ck_symbols_status"),
    )
    op.create_table(
        "analyses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol_id", sa.Integer(), nullable=False),
        sa.Column("analyzed_commit_sha", sa.String(length=40), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("insufficient_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["symbol_id"], ["symbols.id"], name="fk_analyses_symbol_id_symbols", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_analyses"),
        sa.CheckConstraint(
            "outcome IN ('evidence_found', 'insufficient_evidence')",
            name="ck_analyses_outcome",
        ),
        sa.CheckConstraint(
            "(outcome = 'insufficient_evidence' AND insufficient_reason IS NOT NULL) OR "
            "(outcome = 'evidence_found' AND insufficient_reason IS NULL)",
            name="ck_analyses_reason_matches_outcome",
        ),
        sa.CheckConstraint(
            "length(analyzed_commit_sha) = 40", name="ck_analyses_commit_sha_length"
        ),
    )
    op.create_table(
        "file_changes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("commit_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("old_path", sa.Text(), nullable=True),
        sa.Column("change_type", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["commit_id"],
            ["commits.id"],
            name="fk_file_changes_commit_id_commits",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_file_changes"),
        sa.UniqueConstraint("commit_id", "path", name="uq_file_changes_commit_id_path"),
        sa.CheckConstraint(
            "change_type IN ('added', 'modified', 'deleted', 'renamed', 'copied', 'type_changed')",
            name="ck_file_changes_change_type",
        ),
    )
    op.create_table(
        "issue_references",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("commit_id", sa.Integer(), nullable=True),
        sa.Column("pull_request_id", sa.Integer(), nullable=True),
        sa.Column("issue_id", sa.Integer(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["commit_id"],
            ["commits.id"],
            name="fk_issue_references_commit_id_commits",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pull_request_id"],
            ["pull_requests.id"],
            name="fk_issue_references_pull_request_id_pull_requests",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["issue_id"],
            ["issues.id"],
            name="fk_issue_references_issue_id_issues",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_issue_references"),
        sa.UniqueConstraint(
            "pull_request_id",
            "issue_id",
            "method",
            name="uq_issue_references_pull_request_id_issue_id_method",
        ),
        sa.UniqueConstraint(
            "commit_id",
            "issue_id",
            "method",
            name="uq_issue_references_commit_id_issue_id_method",
        ),
        sa.CheckConstraint(
            "CASE WHEN commit_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN pull_request_id IS NOT NULL THEN 1 ELSE 0 END = 1",
            name="ck_issue_references_exactly_one_source",
        ),
        sa.CheckConstraint(
            "method IN ('closing_keyword', 'plain_reference')",
            name="ck_issue_references_method",
        ),
    )
    op.create_table(
        "pull_request_commits",
        sa.Column("pull_request_id", sa.Integer(), nullable=False),
        sa.Column("commit_id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["pull_request_id"],
            ["pull_requests.id"],
            name="fk_pull_request_commits_pull_request_id_pull_requests",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["commit_id"],
            ["commits.id"],
            name="fk_pull_request_commits_commit_id_commits",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "pull_request_id",
            "commit_id",
            name="pk_pull_request_commits",
        ),
    )
    op.create_table(
        "review_comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("pull_request_id", sa.Integer(), nullable=False),
        sa.Column("review_github_id", sa.BigInteger(), nullable=True),
        sa.Column("in_reply_to_github_id", sa.BigInteger(), nullable=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("diff_hunk", sa.Text(), nullable=False),
        sa.Column("commit_sha", sa.String(length=40), nullable=False),
        sa.Column("original_commit_sha", sa.String(length=40), nullable=False),
        sa.Column("line", sa.Integer(), nullable=True),
        sa.Column("start_line", sa.Integer(), nullable=True),
        sa.Column("original_line", sa.Integer(), nullable=True),
        sa.Column("original_start_line", sa.Integer(), nullable=True),
        sa.Column("side", sa.String(), nullable=True),
        sa.Column("start_side", sa.String(), nullable=True),
        sa.Column("subject_type", sa.String(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_login", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["pull_request_id"],
            ["pull_requests.id"],
            name="fk_review_comments_pull_request_id_pull_requests",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_comments"),
        sa.UniqueConstraint("github_id", name="uq_review_comments_github_id"),
        sa.CheckConstraint(
            "start_line IS NULL OR line IS NULL OR start_line <= line",
            name="ck_review_comments_line_range",
        ),
        sa.CheckConstraint(
            "side IS NULL OR side IN ('LEFT', 'RIGHT')",
            name="ck_review_comments_side",
        ),
        sa.CheckConstraint(
            "start_side IS NULL OR start_side IN ('LEFT', 'RIGHT')",
            name="ck_review_comments_start_side",
        ),
        sa.CheckConstraint(
            "subject_type IS NULL OR subject_type IN ('line', 'file')",
            name="ck_review_comments_subject_type",
        ),
        sa.CheckConstraint("length(commit_sha) = 40", name="ck_review_comments_commit_sha_length"),
        sa.CheckConstraint(
            "length(original_commit_sha) = 40",
            name="ck_review_comments_original_commit_sha_length",
        ),
    )
    op.create_table(
        "symbol_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol_id", sa.Integer(), nullable=False),
        sa.Column("commit_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("qualified_name", sa.Text(), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=True),
        sa.Column("end_line", sa.Integer(), nullable=True),
        sa.Column("body_hash", sa.String(length=64), nullable=True),
        sa.Column("parse_status", sa.Text(), nullable=False),
        sa.Column("lineage_method", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["symbol_id"],
            ["symbols.id"],
            name="fk_symbol_versions_symbol_id_symbols",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["commit_id"],
            ["commits.id"],
            name="fk_symbol_versions_commit_id_commits",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_symbol_versions"),
        sa.UniqueConstraint(
            "symbol_id", "commit_id", name="uq_symbol_versions_symbol_id_commit_id"
        ),
        sa.CheckConstraint(
            "(start_line IS NULL AND end_line IS NULL) OR "
            "(start_line IS NOT NULL AND end_line IS NOT NULL AND "
            "start_line >= 1 AND end_line >= start_line)",
            name="ck_symbol_versions_line_range",
        ),
        sa.CheckConstraint(
            "parse_status <> 'ok' OR "
            "(start_line IS NOT NULL AND end_line IS NOT NULL AND body_hash IS NOT NULL)",
            name="ck_symbol_versions_ok_requires_location",
        ),
        sa.CheckConstraint(
            "parse_status IN ('ok', 'syntax_error')",
            name="ck_symbol_versions_parse_status",
        ),
        sa.CheckConstraint(
            "lineage_method IN ('exact', 'rename_detected', 'heuristic')",
            name="ck_symbol_versions_lineage_method",
        ),
    )
    op.create_table(
        "evidence_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("analysis_id", sa.Integer(), nullable=False),
        sa.Column("commit_id", sa.Integer(), nullable=True),
        sa.Column("pull_request_id", sa.Integer(), nullable=True),
        sa.Column("review_comment_id", sa.Integer(), nullable=True),
        sa.Column("issue_id", sa.Integer(), nullable=True),
        sa.Column("source_field", sa.Text(), nullable=False),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("epistemic_label", sa.Text(), nullable=False),
        sa.Column("quote_text", sa.Text(), nullable=False),
        sa.Column("quote_start", sa.Integer(), nullable=False),
        sa.Column("quote_end", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analyses.id"],
            name="fk_evidence_links_analysis_id_analyses",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["commit_id"],
            ["commits.id"],
            name="fk_evidence_links_commit_id_commits",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pull_request_id"],
            ["pull_requests.id"],
            name="fk_evidence_links_pull_request_id_pull_requests",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["review_comment_id"],
            ["review_comments.id"],
            name="fk_evidence_links_review_comment_id_review_comments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["issue_id"],
            ["issues.id"],
            name="fk_evidence_links_issue_id_issues",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_links"),
        sa.CheckConstraint(
            "CASE WHEN commit_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN pull_request_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN review_comment_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN issue_id IS NOT NULL THEN 1 ELSE 0 END = 1",
            name="ck_evidence_links_exactly_one_source",
        ),
        sa.CheckConstraint(
            "(commit_id IS NOT NULL AND source_field = 'message') OR "
            "(pull_request_id IS NOT NULL AND source_field IN ('title', 'body')) OR "
            "(review_comment_id IS NOT NULL AND source_field = 'body') OR "
            "(issue_id IS NOT NULL AND source_field IN ('title', 'body'))",
            name="ck_evidence_links_source_field",
        ),
        sa.CheckConstraint(
            "level IN ('direct', 'strong', 'referenced', 'mentioned')",
            name="ck_evidence_links_level",
        ),
        sa.CheckConstraint(
            "epistemic_label IN ('verified', 'inferred')",
            name="ck_evidence_links_epistemic_label",
        ),
        sa.CheckConstraint(
            "(level IN ('direct', 'strong', 'referenced') AND epistemic_label = 'verified') OR "
            "(level = 'mentioned' AND epistemic_label = 'inferred')",
            name="ck_evidence_links_level_label_match",
        ),
        sa.CheckConstraint(
            "quote_start >= 0 AND quote_end > quote_start",
            name="ck_evidence_links_quote_offsets",
        ),
        sa.CheckConstraint(
            "length(quote_text) = quote_end - quote_start",
            name="ck_evidence_links_quote_length",
        ),
    )

    op.create_index("ix_symbols_repository_id", "symbols", ["repository_id"])
    op.create_index(
        "ix_symbols_repository_id_current_path_qualified_name",
        "symbols",
        ["repository_id", "current_path", "qualified_name"],
    )
    op.create_index("ix_analyses_symbol_id", "analyses", ["symbol_id"])
    op.create_index("ix_pull_request_commits_commit_id", "pull_request_commits", ["commit_id"])
    op.create_index("ix_review_comments_pull_request_id", "review_comments", ["pull_request_id"])
    op.create_index("ix_symbol_versions_symbol_id", "symbol_versions", ["symbol_id"])
    op.create_index("ix_symbol_versions_commit_id", "symbol_versions", ["commit_id"])
    op.create_index("ix_evidence_links_analysis_id", "evidence_links", ["analysis_id"])
    op.create_index("ix_evidence_links_commit_id", "evidence_links", ["commit_id"])
    op.create_index("ix_evidence_links_pull_request_id", "evidence_links", ["pull_request_id"])
    op.create_index("ix_evidence_links_review_comment_id", "evidence_links", ["review_comment_id"])
    op.create_index("ix_evidence_links_issue_id", "evidence_links", ["issue_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_links_issue_id", table_name="evidence_links")
    op.drop_index("ix_evidence_links_review_comment_id", table_name="evidence_links")
    op.drop_index("ix_evidence_links_pull_request_id", table_name="evidence_links")
    op.drop_index("ix_evidence_links_commit_id", table_name="evidence_links")
    op.drop_index("ix_evidence_links_analysis_id", table_name="evidence_links")
    op.drop_index("ix_symbol_versions_commit_id", table_name="symbol_versions")
    op.drop_index("ix_symbol_versions_symbol_id", table_name="symbol_versions")
    op.drop_index("ix_review_comments_pull_request_id", table_name="review_comments")
    op.drop_index("ix_pull_request_commits_commit_id", table_name="pull_request_commits")
    op.drop_index("ix_analyses_symbol_id", table_name="analyses")
    op.drop_index(
        "ix_symbols_repository_id_current_path_qualified_name",
        table_name="symbols",
    )
    op.drop_index("ix_symbols_repository_id", table_name="symbols")
    for table in (
        "evidence_links",
        "symbol_versions",
        "review_comments",
        "pull_request_commits",
        "issue_references",
        "file_changes",
        "analyses",
        "symbols",
        "pull_requests",
        "issues",
        "commits",
        "repositories",
    ):
        op.drop_table(table)
