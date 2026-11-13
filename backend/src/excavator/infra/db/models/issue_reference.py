from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from excavator.infra.db.base import Base


class IssueReference(Base):
    __tablename__ = "issue_references"
    __table_args__ = (
        CheckConstraint(
            "CASE WHEN commit_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN pull_request_id IS NOT NULL THEN 1 ELSE 0 END = 1",
            name="exactly_one_source",
        ),
        CheckConstraint(
            "method IN ('closing_keyword', 'plain_reference')",
            name="method",
        ),
        UniqueConstraint("pull_request_id", "issue_id", "method"),
        UniqueConstraint("commit_id", "issue_id", "method"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    commit_id: Mapped[int | None] = mapped_column(
        ForeignKey("commits.id", ondelete="CASCADE"),
        nullable=True,
    )
    pull_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("pull_requests.id", ondelete="CASCADE"),
        nullable=True,
    )
    issue_id: Mapped[int] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"),
        nullable=False,
    )
    method: Mapped[str] = mapped_column(Text, nullable=False)
