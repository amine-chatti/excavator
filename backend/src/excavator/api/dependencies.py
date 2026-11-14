from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from excavator.config import Settings
from excavator.infra.db.session import session_scope
from excavator.infra.github_client import GitHubClient, HttpGitHubClient
from excavator.infra.llm_client import AnthropicClient, LLMClient, OllamaClient


def get_session() -> Iterator[Session]:
    """Provide one transaction per request."""
    with session_scope() as session:
        yield session


def get_github_client() -> GitHubClient:
    return HttpGitHubClient.from_settings(Settings())


def get_llm_client() -> LLMClient | None:
    settings = Settings()
    if settings.EXPLAIN_PROVIDER == "ollama":
        return OllamaClient(
            model=settings.OLLAMA_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
        )
    if settings.ANTHROPIC_API_KEY is None:
        return None
    return AnthropicClient(
        api_key=settings.ANTHROPIC_API_KEY.get_secret_value(),
        model=settings.EXPLAIN_MODEL,
    )
