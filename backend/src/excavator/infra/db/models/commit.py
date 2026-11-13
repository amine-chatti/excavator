from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from excavator.infra.db.base import Base
from excavator.infra.db.types import UTCDateTime


class Commit(Base):
    __tablename__ = "commits"
    __table_args__ = (
        UniqueConstraint("repository_id", "sha"),
        CheckConstraint("length(sha) = 40", name="sha_length"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    sha: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    author_login: Mapped[str | None] = mapped_column(String, nullable=True)
    authored_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    parent_shas: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
