from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from excavator.infra.db.base import Base
from excavator.infra.db.types import UTCDateTime


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PullRequest(Base):
    __tablename__ = "pull_requests"
    __table_args__ = (
        UniqueConstraint("repository_id", "number"),
        CheckConstraint("state IN ('open', 'closed')", name="state"),
        CheckConstraint(
            "merge_method IN ('merge', 'squash', 'rebase', 'unknown')",
            name="merge_method",
        ),
        CheckConstraint(
            "merge_commit_sha IS NULL OR length(merge_commit_sha) = 40",
            name="merge_commit_sha_length",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    merged: Mapped[bool] = mapped_column(Boolean, nullable=False)
    merged_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    merge_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    merge_method: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="unknown",
    )
    base_ref: Mapped[str] = mapped_column(Text, nullable=False)
    head_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    author_login: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=_utc_now,
        nullable=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
