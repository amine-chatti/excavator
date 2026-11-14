from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from excavator.infra.db.base import Base


class EvidenceLink(Base):
    """Quote links whose source slice is validated by core.evidence.validate_quote."""

    __tablename__ = "evidence_links"
    __table_args__ = (
        CheckConstraint(
            "CASE WHEN commit_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN pull_request_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN review_comment_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN issue_id IS NOT NULL THEN 1 ELSE 0 END = 1",
            name="exactly_one_source",
        ),
        CheckConstraint(
            "(commit_id IS NOT NULL AND source_field = 'message') OR "
            "(pull_request_id IS NOT NULL AND source_field IN ('title', 'body')) OR "
            "(review_comment_id IS NOT NULL AND source_field = 'body') OR "
            "(issue_id IS NOT NULL AND source_field IN ('title', 'body'))",
            name="source_field",
        ),
        CheckConstraint(
            "level IN ('direct', 'strong', 'referenced', 'mentioned')",
            name="level",
        ),
        CheckConstraint(
            "epistemic_label IN ('verified', 'inferred')",
            name="epistemic_label",
        ),
        CheckConstraint(
            "(level IN ('direct', 'strong', 'referenced') AND epistemic_label = 'verified') OR "
            "(level = 'mentioned' AND epistemic_label = 'inferred')",
            name="level_label_match",
        ),
        CheckConstraint(
            "quote_start >= 0 AND quote_end > quote_start",
            name="quote_offsets",
        ),
        CheckConstraint(
            "length(quote_text) = quote_end - quote_start",
            name="quote_length",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    claim_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_claims.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    commit_id: Mapped[int | None] = mapped_column(
        ForeignKey("commits.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    pull_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("pull_requests.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    review_comment_id: Mapped[int | None] = mapped_column(
        ForeignKey("review_comments.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    issue_id: Mapped[int | None] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    source_field: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    epistemic_label: Mapped[str] = mapped_column(Text, nullable=False)
    quote_text: Mapped[str] = mapped_column(Text, nullable=False)
    quote_start: Mapped[int] = mapped_column(Integer, nullable=False)
    quote_end: Mapped[int] = mapped_column(Integer, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
