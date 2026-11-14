from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from excavator.config import Settings


def create_db_engine(database_url: str | None = None) -> Engine:
    """Create a synchronous SQLAlchemy engine without connecting at import time."""
    url = database_url or Settings().DATABASE_URL
    return create_engine(url)


def create_session_factory(
    engine: Engine | None = None,
    database_url: str | None = None,
) -> sessionmaker[Session]:
    """Create a session factory for the supplied engine or configured URL."""
    return sessionmaker(bind=engine or create_db_engine(database_url), class_=Session)


@contextmanager
def session_scope(
    session_factory: Callable[[], Session] | None = None,
) -> Iterator[Session]:
    """Commit a session on success, roll it back on failure, and always close it."""
    factory = session_factory or create_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
