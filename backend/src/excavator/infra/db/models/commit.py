from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from excavator.infra.db.base import Base


class Commit(Base):
    __tablename__ = "commit"
    __table_args__ = (UniqueConstraint("repository_id", "sha"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repository.id"),
        index=True,
        nullable=False,
    )
    sha: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    author_login: Mapped[str | None] = mapped_column(String, nullable=True)
    authored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    parent_shas: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
