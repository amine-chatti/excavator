from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from excavator.api.dependencies import get_llm_client, get_session
from excavator.infra.db.models import Commit, Symbol, SymbolVersion
from excavator.infra.explain.extractive import extract_symbol_evidence
from excavator.infra.explain.service import (
    ExplanationClaim,
    ExplanationError,
    explain_symbol,
    get_stored_explanation,
)
from excavator.infra.llm_client import LLMClient, LLMClientError, LLMRateLimitError

router = APIRouter(tags=["symbols"])


class SymbolResponse(BaseModel):
    id: int
    repository_id: int
    language: str
    kind: str
    qualified_name: str
    current_path: str | None
    status: str


class SymbolListResponse(BaseModel):
    items: list[SymbolResponse]
    total: int


class LineageVersionResponse(BaseModel):
    commit_sha: str
    commit_message: str
    authored_at: datetime
    path: str
    qualified_name: str
    start_line: int | None
    end_line: int | None
    body_hash: str | None
    parse_status: str
    lineage_method: str


class SymbolLineageResponse(BaseModel):
    symbol: SymbolResponse
    versions: list[LineageVersionResponse]


class ExplanationQuoteResponse(BaseModel):
    snippet_id: str
    source_type: str
    quote: str
    level: str
    epistemic_label: str


class ExplanationClaimResponse(BaseModel):
    position: int
    text: str
    quotes: list[ExplanationQuoteResponse]


class ExplanationResponse(BaseModel):
    status: str
    summary: str | None
    claims: list[ExplanationClaimResponse]
    dropped_claim_count: int
    truncated: bool
    truncated_snippet_count: int
    omitted_snippet_count: int


class StoredExplanationResponse(BaseModel):
    status: str
    summary: str
    claims: list[ExplanationClaimResponse]


class ExtractiveExtractResponse(BaseModel):
    source_kind: Literal["commit", "pull_request", "review_comment", "issue"]
    reference: str | int
    excerpt: str
    lineage_event: Literal["added", "modified", "renamed", "moved", "removed"] | None
    created_at: datetime
    label: Literal["quote"]
    epistemic_label: Literal["verified"]


class ExtractiveExplanationResponse(BaseModel):
    status: Literal["extracts", "no_evidence"]
    extracts: list[ExtractiveExtractResponse]


@router.get("/repositories/{repository_id}/symbols", response_model=SymbolListResponse)
def list_symbols(
    repository_id: int,
    session: Annotated[Session, Depends(get_session)],
    path: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SymbolListResponse:
    filters = [Symbol.repository_id == repository_id]
    if path is not None:
        filters.append(
            or_(
                Symbol.current_path == path,
                Symbol.id.in_(select(SymbolVersion.symbol_id).where(SymbolVersion.path == path)),
            )
        )
    if kind is not None:
        filters.append(Symbol.kind == kind)
    if status is not None:
        filters.append(Symbol.status == status)
    total = session.scalar(select(func.count()).select_from(Symbol).where(*filters)) or 0
    items = list(
        session.scalars(
            select(Symbol).where(*filters).order_by(Symbol.id).offset(offset).limit(limit)
        )
    )
    return SymbolListResponse(
        items=[SymbolResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
    )


@router.get("/symbols/{symbol_id}/lineage", response_model=SymbolLineageResponse)
def get_symbol_lineage(
    symbol_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> SymbolLineageResponse:
    symbol = session.get(Symbol, symbol_id)
    if symbol is None:
        raise HTTPException(status_code=404, detail="symbol not found")
    rows = session.execute(
        select(SymbolVersion, Commit)
        .join(Commit, Commit.id == SymbolVersion.commit_id)
        .where(SymbolVersion.symbol_id == symbol_id)
        .order_by(SymbolVersion.id)
    ).all()
    return SymbolLineageResponse(
        symbol=SymbolResponse.model_validate(symbol, from_attributes=True),
        versions=[
            LineageVersionResponse(
                commit_sha=commit.sha,
                commit_message=(
                    commit.message.splitlines()[0] if commit.message.splitlines() else ""
                ),
                authored_at=commit.authored_at,
                path=version.path,
                qualified_name=version.qualified_name,
                start_line=version.start_line,
                end_line=version.end_line,
                body_hash=version.body_hash,
                parse_status=version.parse_status,
                lineage_method=version.lineage_method,
            )
            for version, commit in rows
        ],
    )


def _claim_response(claim: ExplanationClaim) -> ExplanationClaimResponse:
    return ExplanationClaimResponse(
        position=claim.position,
        text=claim.text,
        quotes=[
            ExplanationQuoteResponse(
                snippet_id=quote.snippet_id,
                source_type=quote.source_type,
                quote=quote.quote,
                level=quote.level,
                epistemic_label=quote.epistemic_label,
            )
            for quote in claim.quotes
        ],
    )


@router.post("/symbols/{symbol_id}/explain", response_model=ExplanationResponse)
def explain_symbol_route(
    symbol_id: int,
    session: Annotated[Session, Depends(get_session)],
    client: Annotated[LLMClient | None, Depends(get_llm_client)],
) -> ExplanationResponse:
    if session.get(Symbol, symbol_id) is None:
        raise HTTPException(status_code=404, detail="symbol not found")
    if client is None:
        raise HTTPException(status_code=503, detail="explanation service is not configured")
    try:
        result = explain_symbol(session, symbol_id, client)
    except LLMRateLimitError:
        raise HTTPException(status_code=429, detail="LLM rate limit exceeded") from None
    except (LLMClientError, ExplanationError):
        raise HTTPException(status_code=502, detail="explanation request failed") from None
    return ExplanationResponse(
        status=result.status,
        summary=result.summary,
        claims=[_claim_response(claim) for claim in result.claims],
        dropped_claim_count=result.dropped_claim_count,
        truncated=result.truncated,
        truncated_snippet_count=result.truncated_snippet_count,
        omitted_snippet_count=result.omitted_snippet_count,
    )


@router.get("/symbols/{symbol_id}/explanation", response_model=StoredExplanationResponse)
def get_symbol_explanation(
    symbol_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> StoredExplanationResponse:
    if session.get(Symbol, symbol_id) is None:
        raise HTTPException(status_code=404, detail="symbol not found")
    result = get_stored_explanation(session, symbol_id)
    if result is None or result.summary is None:
        raise HTTPException(status_code=404, detail="explanation not found")
    return StoredExplanationResponse(
        status=result.status,
        summary=result.summary,
        claims=[_claim_response(claim) for claim in result.claims],
    )


@router.get(
    "/symbols/{symbol_id}/extractive-explanation",
    response_model=ExtractiveExplanationResponse,
)
def get_extractive_explanation(
    symbol_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> ExtractiveExplanationResponse:
    if session.get(Symbol, symbol_id) is None:
        raise HTTPException(status_code=404, detail="symbol not found")
    extracts = extract_symbol_evidence(session, symbol_id)
    return ExtractiveExplanationResponse(
        status="extracts" if extracts else "no_evidence",
        extracts=[
            ExtractiveExtractResponse(
                source_kind=extract.source_kind,
                reference=extract.reference,
                excerpt=extract.excerpt,
                lineage_event=extract.lineage_event,
                created_at=extract.created_at,
                label=extract.label,
                epistemic_label=extract.epistemic_label,
            )
            for extract in extracts
        ],
    )
