"""Shared FastAPI dependencies: auth resolution and dataset/version loaders."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Dataset, DatasetVersion, Project, User
from .security import decode_access_token
from .services.ingest import load_version_frame

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = payload.get("sub")
    user = db.get(User, int(user_id)) if user_id else None
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists.",
        )
    return user


def get_owned_project(db: Session, user: User, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def get_owned_project_by_uid(db: Session, user: User, uid: str) -> Project:
    project = db.scalar(select(Project).where(Project.uid == uid))
    if project is None or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def get_owned_dataset(db: Session, user: User, dataset_id: int) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    project = db.get(Project, dataset.project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return dataset


def resolve_version(db: Session, dataset: Dataset,
                    version_id: int | None = None) -> DatasetVersion:
    """Resolve an explicit version or fall back to the dataset's current one."""
    if version_id is not None:
        version = db.get(DatasetVersion, version_id)
        if version is None or version.dataset_id != dataset.id:
            raise HTTPException(status_code=404, detail="Dataset version not found.")
        return version
    if dataset.current_version_id:
        version = db.get(DatasetVersion, dataset.current_version_id)
        if version:
            return version
    if dataset.versions:
        return dataset.versions[-1]
    raise HTTPException(status_code=409, detail="This dataset has no data version yet.")


def load_frame(version: DatasetVersion) -> pd.DataFrame:
    path = Path(version.storage_path)
    if not path.exists():
        raise HTTPException(
            status_code=410,
            detail=(
                "The stored data snapshot for this version is missing from disk. "
                "Re-upload the dataset."
            ),
        )
    try:
        return load_version_frame(path)
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=500, detail=f"Could not read the dataset snapshot: {exc}"
        ) from exc
