"""Project management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_owned_project
from ..models import Dataset, DatasetVersion, Project, User
from ..schemas import (
    DatasetSummary,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def _summarise_dataset(dataset: Dataset, db: Session) -> DatasetSummary:
    version = (
        db.get(DatasetVersion, dataset.current_version_id)
        if dataset.current_version_id else None
    )
    return DatasetSummary(
        id=dataset.id,
        uid=dataset.uid,
        name=dataset.name,
        original_filename=dataset.original_filename,
        source_format=dataset.source_format,
        file_size_bytes=dataset.file_size_bytes,
        row_count=version.row_count if version else None,
        column_count=version.column_count if version else None,
        quality_score=version.quality_score if version else None,
        version_count=len(dataset.versions),
        created_at=dataset.created_at,
    )


def _serialise_project(project: Project, db: Session) -> ProjectOut:
    return ProjectOut(
        id=project.id,
        uid=project.uid,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
        updated_at=project.updated_at,
        datasets=[_summarise_dataset(d, db) for d in project.datasets],
    )


@router.get("", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[ProjectOut]:
    projects = db.scalars(
        select(Project)
        .where(Project.owner_id == user.id)
        .order_by(Project.updated_at.desc())
    ).unique().all()
    return [_serialise_project(p, db) for p in projects]


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectOut:
    project = Project(
        owner_id=user.id,
        name=payload.name.strip(),
        description=payload.description.strip(),
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _serialise_project(project, db)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectOut:
    project = get_owned_project(db, user, project_id)
    return _serialise_project(project, db)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectOut:
    project = get_owned_project(db, user, project_id)
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Project name cannot be empty.")
        project.name = name
    if payload.description is not None:
        project.description = payload.description.strip()
    db.commit()
    db.refresh(project)
    return _serialise_project(project, db)

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    project = get_owned_project(db, user, project_id)
    db.delete(project)
    db.commit()
