"""Dataset upload, listing, preview and version management."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import (
    get_current_user,
    get_owned_dataset,
    get_owned_project,
    load_frame,
    resolve_version,
)
from ..models import Dataset, DatasetVersion, User
from ..schemas import (
    DatasetOut,
    DatasetRenameRequest,
    VersionOut,
)
from ..services.ingest import (
    DatasetParseError,
    parse_upload,
    read_upload_file,
    save_version_snapshot,
)
from ..services.profiling import preview_dataframe, profile_dataframe

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _serialise(dataset: Dataset) -> DatasetOut:
    return DatasetOut(
        id=dataset.id,
        uid=dataset.uid,
        project_id=dataset.project_id,
        name=dataset.name,
        original_filename=dataset.original_filename,
        source_format=dataset.source_format,
        file_size_bytes=dataset.file_size_bytes,
        current_version_id=dataset.current_version_id,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
        versions=[VersionOut.model_validate(v) for v in dataset.versions],
    )


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"


@router.post(
    "/upload", response_model=DatasetOut, status_code=status.HTTP_201_CREATED
)
async def upload_dataset(
    project_id: int = Form(...),
    name: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DatasetOut:
    project = get_owned_project(db, user, project_id)

    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{suffix}'. Allowed: "
                + ", ".join(settings.ALLOWED_EXTENSIONS)
            ),
        )

    raw = await read_upload_file(file)
    try:
        frame = parse_upload(raw, filename)
    except DatasetParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    dataset = Dataset(
        project_id=project.id,
        name=(name.strip() or Path(filename).stem)[:200],
        original_filename=filename[:255],
        source_format=suffix.lstrip("."),
        file_size_bytes=len(raw),
    )
    db.add(dataset)
    db.flush()  # obtain dataset.uid and id

    # Always keep the untouched original bytes for audit/re-download.
    original_dir = settings.STORAGE_DIR / "original"
    original_dir.mkdir(parents=True, exist_ok=True)
    original_path = original_dir / f"{dataset.uid}_{filename}"
    try:
        original_path.write_bytes(raw)
    except OSError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Could not store the uploaded file: {exc}"
        ) from exc

    path = save_version_snapshot(frame, settings.STORAGE_DIR, dataset.uid, 1)
    profile = profile_dataframe(frame)

    version = DatasetVersion(
        dataset_id=dataset.id,
        version_number=1,
        storage_path=str(path),
        row_count=int(frame.shape[0]),
        column_count=int(frame.shape[1]),
        column_names=[str(c) for c in frame.columns],
        dtypes={str(c): str(dtype) for c, dtype in frame.dtypes.items()},
        label="Original upload",
        is_original=True,
        profile=profile,
        quality_score=profile["quality"]["score"],
    )
    db.add(version)
    db.flush()
    dataset.current_version_id = version.id
    db.commit()
    db.refresh(dataset)
    return _serialise(dataset)


@router.get("", response_model=list[DatasetOut])
def list_datasets(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DatasetOut]:
    query = select(Dataset).join(Dataset.project).where(Dataset.project.has(owner_id=user.id))
    if project_id is not None:
        get_owned_project(db, user, project_id)
        query = select(Dataset).where(Dataset.project_id == project_id)
    datasets = db.scalars(query.order_by(Dataset.updated_at.desc())).unique().all()
    return [_serialise(d) for d in datasets]


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DatasetOut:
    return _serialise(get_owned_dataset(db, user, dataset_id))


@router.patch("/{dataset_id}", response_model=DatasetOut)
def rename_dataset(
    dataset_id: int,
    payload: DatasetRenameRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DatasetOut:
    dataset = get_owned_dataset(db, user, dataset_id)
    dataset.name = payload.name.strip()
    db.commit()
    db.refresh(dataset)
    return _serialise(dataset)

@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    dataset = get_owned_dataset(db, user, dataset_id)
    paths = [Path(v.storage_path) for v in dataset.versions]
    db.delete(dataset)
    db.commit()
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


@router.get("/{dataset_id}/preview")
def dataset_preview(
    dataset_id: int,
    version_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, version_id)
    frame = load_frame(version)
    payload = preview_dataframe(frame, limit)
    payload["version_id"] = version.id
    payload["version_number"] = version.version_number
    payload["version_label"] = version.label
    return payload


@router.get("/{dataset_id}/versions", response_model=list[VersionOut])
def list_versions(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[VersionOut]:
    dataset = get_owned_dataset(db, user, dataset_id)
    return [VersionOut.model_validate(v) for v in dataset.versions]


@router.post("/{dataset_id}/versions/{version_id}/activate", response_model=DatasetOut)
def activate_version(
    dataset_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DatasetOut:
    """Switch the dataset's current version (used for undo / browsing history)."""
    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, version_id)
    dataset.current_version_id = version.id
    db.commit()
    db.refresh(dataset)
    return _serialise(dataset)


@router.get("/{dataset_id}/download")
def download_dataset(
    dataset_id: int,
    version_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stream a CSV of the selected version (real data, not a cached copy)."""
    import io

    from fastapi.responses import StreamingResponse

    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, version_id)
    frame = load_frame(version)
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False)
    buffer.seek(0)
    filename = f"{dataset.name.replace(' ', '_')}_v{version.version_number}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
