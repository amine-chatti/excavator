from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from excavator.api.dependencies import get_session
from excavator.api.routes.repositories import repository_path
from excavator.infra.analysis_service import AnalysisSummary, UnsupportedLanguageError, analyze_file
from excavator.infra.db.models import Repository
from excavator.infra.git_history import GitHistoryError

router = APIRouter(prefix="/repositories", tags=["analysis"])


def _validate_file_path(value: str) -> str:
    if (
        not value
        or value.startswith(("-", "/"))
        or "\\" in value
        or (len(value) >= 2 and value[1] == ":")
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or any(segment in {"", ".", ".."} for segment in value.split("/"))
    ):
        raise ValueError("file_path must be a safe relative path")
    return value


class AnalysisRequest(BaseModel):
    file_path: str
    ref: str = "HEAD"
    max_commits: int | None = Field(default=None, ge=1)

    _file_path_validator = field_validator("file_path")(_validate_file_path)

    @field_validator("ref")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        if (
            not value
            or value.startswith("-")
            or ".." in value
            or any(character.isspace() for character in value)
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ValueError("ref must be a safe Git reference")
        return value


class AnalysisResponse(BaseModel):
    repository_id: int
    file_path: str
    ref: str
    commit_count: int
    skipped_commit_count: int
    lineage_count: int
    symbol_ids: tuple[int, ...]
    warnings: tuple[str, ...]


def _analysis_response(summary: AnalysisSummary) -> AnalysisResponse:
    return AnalysisResponse(
        repository_id=summary.repository_id,
        file_path=summary.file_path,
        ref=summary.ref,
        commit_count=summary.commit_count,
        skipped_commit_count=summary.skipped_commit_count,
        lineage_count=summary.lineage_count,
        symbol_ids=summary.symbol_ids,
        warnings=summary.warnings,
    )


@router.post("/{repository_id}/analyze", response_model=AnalysisResponse)
def analyze_repository_file(
    repository_id: int,
    payload: AnalysisRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> AnalysisResponse:
    repository = session.get(Repository, repository_id)
    if repository is None:
        raise HTTPException(status_code=404, detail="repository not found")
    try:
        summary = analyze_file(
            session,
            repository_id,
            repository_path(request.app.state.settings.REPOS_ROOT, repository),
            payload.file_path,
            payload.ref,
            payload.max_commits,
        )
    except UnsupportedLanguageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GitHistoryError as exc:
        if str(exc).startswith("no Git history found for path "):
            raise HTTPException(status_code=404, detail="no history found for file") from exc
        raise HTTPException(status_code=502, detail="local Git operation failed") from exc
    return _analysis_response(summary)
