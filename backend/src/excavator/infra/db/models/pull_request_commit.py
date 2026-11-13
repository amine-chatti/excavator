from __future__ import annotations

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from excavator.infra.db.base import Base


class PullRequestCommit(Base):
    """Links established by GitHub's PR-commit listing, not by inference."""

    __tablename__ = "pull_request_commits"

    pull_request_id: Mapped[int] = mapped_column(
        ForeignKey("pull_requests.id", ondelete="CASCADE"),
        primary_key=True,
    )
    commit_id: Mapped[int] = mapped_column(
        ForeignKey("commits.id", ondelete="CASCADE"),
        primary_key=True,
    )
    ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
