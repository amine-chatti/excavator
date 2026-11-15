from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from excavator.infra.db.base import Base


class AnalysisClaim(Base):
    __tablename__ = "analysis_claims"
    __table_args__ = (
        UniqueConstraint("analysis_id", "position"),
        CheckConstraint("position >= 0", name="position_non_negative"),
        CheckConstraint("length(text) > 0", name="text_non_empty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
