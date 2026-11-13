from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from excavator.infra.db.base import Base


class SymbolVersion(Base):
    __tablename__ = "symbol_versions"
    __table_args__ = (
        UniqueConstraint("symbol_id", "commit_id"),
        CheckConstraint(
            "(start_line IS NULL AND end_line IS NULL) OR "
            "(start_line IS NOT NULL AND end_line IS NOT NULL AND "
            "start_line >= 1 AND end_line >= start_line)",
            name="line_range",
        ),
        CheckConstraint(
            "parse_status <> 'ok' OR "
            "(start_line IS NOT NULL AND end_line IS NOT NULL AND body_hash IS NOT NULL)",
            name="ok_requires_location",
        ),
        CheckConstraint(
            "parse_status IN ('ok', 'syntax_error')",
            name="parse_status",
        ),
        CheckConstraint(
            "lineage_method IN ('exact', 'rename_detected', 'heuristic')",
            name="lineage_method",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol_id: Mapped[int] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    commit_id: Mapped[int] = mapped_column(
        ForeignKey("commits.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    qualified_name: Mapped[str] = mapped_column(Text, nullable=False)
    start_line: Mapped[int | None] = mapped_column(nullable=True)
    end_line: Mapped[int | None] = mapped_column(nullable=True)
    body_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parse_status: Mapped[str] = mapped_column(Text, nullable=False)
    lineage_method: Mapped[str] = mapped_column(Text, nullable=False)
