from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from excavator.infra.db.base import Base
from excavator.infra.db.types import UTCDateTime


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('evidence_found', 'insufficient_evidence')",
            name="outcome",
        ),
        CheckConstraint(
            "(outcome = 'insufficient_evidence' AND insufficient_reason IS NOT NULL) OR "
            "(outcome = 'evidence_found' AND insufficient_reason IS NULL)",
            name="reason_matches_outcome",
        ),
        CheckConstraint("length(analyzed_commit_sha) = 40", name="commit_sha_length"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol_id: Mapped[int] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    analyzed_commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    insufficient_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=_utc_now,
        nullable=False,
    )
