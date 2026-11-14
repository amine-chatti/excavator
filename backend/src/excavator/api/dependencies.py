from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from excavator.infra.db.session import session_scope


def get_session() -> Iterator[Session]:
    """Provide one transaction per request."""
    with session_scope() as session:
        yield session
