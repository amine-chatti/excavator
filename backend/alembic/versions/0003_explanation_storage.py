"""Store explanation summaries and claims."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003_explanation_storage"
down_revision = "0002_nullable_commit_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("explanation_summary", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_analyses_explanation_summary_outcome",
        "analyses",
        "explanation_summary IS NULL OR outcome = 'evidence_found'",
    )
    op.create_table(
        "analysis_claims",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("analysis_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analyses.id"],
            name="fk_analysis_claims_analysis_id_analyses",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_analysis_claims"),
        sa.UniqueConstraint(
            "analysis_id",
            "position",
            name="uq_analysis_claims_analysis_id_position",
        ),
        sa.CheckConstraint("position >= 0", name="ck_analysis_claims_position_non_negative"),
        sa.CheckConstraint("length(text) > 0", name="ck_analysis_claims_text_non_empty"),
    )
    op.create_index(
        "ix_analysis_claims_analysis_id",
        "analysis_claims",
        ["analysis_id"],
    )
    op.add_column("evidence_links", sa.Column("claim_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_evidence_links_claim_id_analysis_claims",
        "evidence_links",
        "analysis_claims",
        ["claim_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_evidence_links_claim_id", "evidence_links", ["claim_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_links_claim_id", table_name="evidence_links")
    op.drop_constraint(
        "fk_evidence_links_claim_id_analysis_claims",
        "evidence_links",
        type_="foreignkey",
    )
    op.drop_column("evidence_links", "claim_id")
    op.drop_index("ix_analysis_claims_analysis_id", table_name="analysis_claims")
    op.drop_table("analysis_claims")
    op.drop_constraint(
        "ck_analyses_explanation_summary_outcome",
        "analyses",
        type_="check",
    )
    op.drop_column("analyses", "explanation_summary")
