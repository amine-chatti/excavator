from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from excavator.api.dependencies import get_session
from excavator.infra.db.models import Repository
from excavator.infra.git_clone import GitCloneError, clone_repository

router = APIRouter(prefix="/repositories", tags=["repositories"])


def _validate_identifier(value: str) -> str:
    if (
        value in {".", ".."}
        or not value
        or any(
            not (character.isascii() and (character.isalnum() or character in "._-"))
            for character in value
        )
    ):
        raise ValueError("must contain only ASCII letters, numbers, '.', '_' or '-'")
    return value


class RepositoryCreate(BaseModel):
    owner: str
    name: str
    clone: bool = False

    _owner_validator = field_validator("owner")(_validate_identifier)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = _validate_identifier(value)
        if value.endswith(".git"):
            raise ValueError("name must not end with '.git'")
        return value


class RepositoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner: str
    name: str
    default_branch: str | None
    indexing_status: str
    head_sha_indexed: str | None
    created_at: datetime
    updated_at: datetime


def repository_path(root: Path, repository: Repository) -> Path:
    resolved_root = root.expanduser().resolve()
    candidate = (resolved_root / repository.owner / repository.name).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("repository path is outside REPOS_ROOT") from exc
    return candidate


@router.post("", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
def create_repository(
    payload: RepositoryCreate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> Repository:
    existing = session.scalar(
        select(Repository).where(
            Repository.owner == payload.owner,
            Repository.name == payload.name,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="repository already exists")

    root = request.app.state.settings.REPOS_ROOT
    candidate = (root.expanduser().resolve() / payload.owner / payload.name).resolve()
    try:
        candidate.relative_to(root.expanduser().resolve())
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid repository path") from None
    if payload.clone and not candidate.exists():
        try:
            clone_repository(
                payload.owner,
                payload.name,
                root,
                request.app.state.settings.GIT_REMOTE_BASE,
                allow_local=request.app.state.settings.ALLOW_LOCAL_REMOTES,
            )
        except FileExistsError:
            raise HTTPException(status_code=409, detail="repository already exists") from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except GitCloneError:
            raise HTTPException(status_code=502, detail="repository clone failed") from None
    if not candidate.is_dir():
        raise HTTPException(status_code=404, detail="repository directory not found")

    repository = Repository(owner=payload.owner, name=payload.name)
    session.add(repository)
    session.flush()
    return repository


@router.get("", response_model=list[RepositoryResponse])
def list_repositories(
    session: Annotated[Session, Depends(get_session)],
) -> list[Repository]:
    return list(session.scalars(select(Repository).order_by(Repository.id)))
