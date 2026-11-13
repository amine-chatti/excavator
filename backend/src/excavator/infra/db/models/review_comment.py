from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from excavator.infra.db.base import Base
from excavator.infra.db.types import UTCDateTime


class ReviewComment(Base):
    __tablename__ = "review_comments"
    __table_args__ = (
        UniqueConstraint("github_id"),
        CheckConstraint(
            "start_line IS NULL OR line IS NULL OR start_line <= line",
            name="line_range",
        ),
        CheckConstraint(
            "side IS NULL OR side IN ('LEFT', 'RIGHT')",
            name="side",
        ),
        CheckConstraint(
            "start_side IS NULL OR start_side IN ('LEFT', 'RIGHT')",
            name="start_side",
        ),
        CheckConstraint(
            "subject_type IS NULL OR subject_type IN ('line', 'file')",
            name="subject_type",
        ),
        CheckConstraint("length(commit_sha) = 40", name="commit_sha_length"),
        CheckConstraint(
            "length(original_commit_sha) = 40",
            name="original_commit_sha_length",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pull_request_id: Mapped[int] = mapped_column(
        ForeignKey("pull_requests.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    review_github_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    in_reply_to_github_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    diff_hunk: Mapped[str] = mapped_column(Text, nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    original_commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_start_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    side: Mapped[str | None] = mapped_column(String, nullable=True)
    start_side: Mapped[str | None] = mapped_column(String, nullable=True)
    subject_type: Mapped[str | None] = mapped_column(String, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_login: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
