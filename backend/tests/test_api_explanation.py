from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from sqlite3 import Connection

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from excavator.api.dependencies import get_llm_client, get_session
from excavator.api.main import create_app
from excavator.infra.db.base import Base
from excavator.infra.db.models import Commit, Repository, Symbol, SymbolVersion
from excavator.infra.llm_client import LLMClientError, LLMRateLimitError


@pytest.fixture
def explanation_api(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, Session, int]]:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection: Connection, _: object) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = Session(engine)
    repository = Repository(owner="owner", name="repo")
    session.add(repository)
    session.flush()
    commit = Commit(
        repository_id=repository.id,
        sha="f" * 40,
        message="The new lookup reduces repeated work.",
        authored_at=datetime(2026, 3, 1, tzinfo=UTC),
        parent_shas=[],
        url=None,
    )
    symbol = Symbol(
        repository_id=repository.id,
        language="python",
        kind="function",
        qualified_name="pkg.lookup",
        current_path="pkg/lookup.py",
        status="exists",
    )
    session.add_all([commit, symbol])
    session.flush()
    session.add(
        SymbolVersion(
            symbol_id=symbol.id,
            commit_id=commit.id,
            path="pkg/lookup.py",
            qualified_name="pkg.lookup",
            start_line=1,
            end_line=2,
            body_hash="1" * 64,
            parse_status="ok",
            lineage_method="exact",
        )
    )
    session.commit()
    app = create_app()

    def provide_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = provide_session
    try:
        with TestClient(app) as test_client:
            yield test_client, session, symbol.id
    finally:
        session.close()
        engine.dispose()


class FakeLLM:
    def __init__(self, response: str | Exception) -> None:
        self.response = response

    def complete(self, system: str, user: str) -> str:
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _valid_response() -> str:
    return json.dumps(
        {
            "summary": "The lookup reduces repeated work.",
            "claims": [
                {
                    "text": "It avoids repeated work.",
                    "quotes": [
                        {
                            "snippet_id": f"commit:{'f' * 40}:message",
                            "quote": "reduces repeated work",
                        }
                    ],
                }
            ],
        }
    )


def test_explain_api_success_and_get_stored_explanation(
    explanation_api: tuple[TestClient, Session, int],
) -> None:
    test_client, _, symbol_id = explanation_api
    app = test_client.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_llm_client] = lambda: FakeLLM(_valid_response())

    posted = test_client.post(f"/symbols/{symbol_id}/explain")
    assert posted.status_code == 200
    body = posted.json()
    assert body["status"] == "explained"
    assert body["summary"] == "The lookup reduces repeated work."
    assert body["dropped_claim_count"] == 0
    assert body["truncated"] is False
    quote = body["claims"][0]["quotes"][0]
    assert quote == {
        "snippet_id": f"commit:{'f' * 40}:message",
        "source_type": "commit_message",
        "quote": "reduces repeated work",
        "level": "mentioned",
        "epistemic_label": "inferred",
    }

    fetched = test_client.get(f"/symbols/{symbol_id}/explanation")
    assert fetched.status_code == 200
    assert fetched.json() == {
        "status": "explained",
        "summary": "The lookup reduces repeated work.",
        "claims": body["claims"],
    }


def test_explain_api_unknown_symbol_is_404(
    explanation_api: tuple[TestClient, Session, int],
) -> None:
    test_client, _, _ = explanation_api
    assert test_client.post("/symbols/999/explain").status_code == 404
    assert test_client.get("/symbols/999/explanation").status_code == 404


def test_explain_api_without_key_is_503(
    explanation_api: tuple[TestClient, Session, int],
) -> None:
    test_client, _, symbol_id = explanation_api
    response = test_client.post(f"/symbols/{symbol_id}/explain")
    assert response.status_code == 503
    assert response.json() == {"detail": "explanation service is not configured"}


@pytest.mark.parametrize(
    ("client_response", "status", "detail"),
    [
        (LLMRateLimitError("provider detail"), 429, "LLM rate limit exceeded"),
        (LLMClientError("secret key or path"), 502, "explanation request failed"),
        ("invalid JSON", 502, "explanation request failed"),
    ],
)
def test_explain_api_maps_client_errors(
    explanation_api: tuple[TestClient, Session, int],
    client_response: str | Exception,
    status: int,
    detail: str,
) -> None:
    test_client, _, symbol_id = explanation_api
    app = test_client.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_llm_client] = lambda: FakeLLM(client_response)
    response = test_client.post(f"/symbols/{symbol_id}/explain")
    assert response.status_code == status
    if status == 200:
        assert response.json()["status"] == detail
    else:
        assert response.json() == {"detail": detail}
    assert "secret key or path" not in response.text


def test_get_explanation_without_prior_explanation_is_404(
    explanation_api: tuple[TestClient, Session, int],
) -> None:
    test_client, _, symbol_id = explanation_api
    response = test_client.get(f"/symbols/{symbol_id}/explanation")
    assert response.status_code == 404
    assert response.json() == {"detail": "explanation not found"}
