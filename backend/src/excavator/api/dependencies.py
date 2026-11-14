from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from excavator.config import Settings
from excavator.infra.db.session import session_scope
from excavator.infra.github_client import GitHubClient, HttpGitHubClient


def get_session() -> Iterator[Session]:
    """Provide one transaction per request."""
    with session_scope() as session:
        yield session


def get_github_client() -> GitHubClient:
    return HttpGitHubClient.from_settings(Settings())
