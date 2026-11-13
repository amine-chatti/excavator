from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from excavator.infra.db.base import Base


class FileChange(Base):
    __tablename__ = "file_changes"
    __table_args__ = (
        UniqueConstraint("commit_id", "path"),
        CheckConstraint(
            "change_type IN ('added', 'modified', 'deleted', 'renamed', 'copied', 'type_changed')",
            name="change_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    commit_id: Mapped[int] = mapped_column(
        ForeignKey("commits.id", ondelete="CASCADE"),
        nullable=False,
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    old_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_type: Mapped[str] = mapped_column(Text, nullable=False)
