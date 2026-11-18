"""Automated profiling endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_owned_dataset, load_frame, resolve_version
from ..models import User
from ..services.cleaning import cleaning_recommendations
from ..services.profiling import (
    key_findings,
    numeric_summary_table,
    profile_dataframe,
)

router = APIRouter(prefix="/datasets", tags=["profiling"])


@router.get("/{dataset_id}/profile")
def get_profile(
    dataset_id: int,
    version_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, version_id)
    frame = load_frame(version)
    profile = profile_dataframe(frame)
    return {
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "version_id": version.id,
        "version_number": version.version_number,
        "version_label": version.label,
        "profile": profile,
        "findings": key_findings(profile),
        "numeric_summary": numeric_summary_table(frame),
        "recommendations": cleaning_recommendations(frame),
    }


@router.get("/{dataset_id}/findings")
def get_findings(
    dataset_id: int,
    version_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, version_id)
    frame = load_frame(version)
    profile = profile_dataframe(frame)
    return {
        "findings": key_findings(profile),
        "quality": profile["quality"],
        "shape": profile["shape"],
    }


@router.get("/{dataset_id}/quality")
def get_quality(
    dataset_id: int,
    version_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, version_id)
    frame = load_frame(version)
    return profile_dataframe(frame)["quality"]


@router.get("/{dataset_id}/columns")
def get_columns(
    dataset_id: int,
    version_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Lightweight column metadata for building UI controls and queries."""
    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, version_id)
    frame = load_frame(version)
    profile = profile_dataframe(frame)
    return {
        "version_id": version.id,
        "version_number": version.version_number,
        "shape": profile["shape"],
        "columns": [
            {
                "name": column["name"],
                "kind": column["kind"],
                "missing": column["missing"],
                "unique": column["unique"],
                "pandas_dtype": column["pandas_dtype"],
            }
            for column in profile["columns"]
        ],
        "column_groups": profile["column_groups"],
    }


@router.get("/{dataset_id}/stats/summary")
def get_stats_summary(
    dataset_id: int,
    version_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, version_id)
    frame = load_frame(version)
    return {
        "rows": numeric_summary_table(frame),
        "note": "Standard deviation uses the sample estimator (ddof=1). "
                "Outliers use the 1.5×IQR rule.",
    }
