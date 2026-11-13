from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from excavator.infra.db.base import Base
from excavator.infra.db.types import UTCDateTime


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Repository(Base):
    __tablename__ = "repository"
    __table_args__ = (
        UniqueConstraint("owner", "name"),
        CheckConstraint(
            "indexing_status IN ('pending', 'running', 'done', 'failed')",
            name="indexing_status_values",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    default_branch: Mapped[str | None] = mapped_column(String, nullable=True)
    indexing_status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="pending",
    )
    head_sha_indexed: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=_utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )
