
"""Data cleaning endpoints: preview, apply, history, undo, and PDF report."""

from __future__ import annotations

import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import (
    get_current_user,
    get_owned_dataset,
    load_frame,
    resolve_version,
)
from ..models import CleaningAction, DatasetVersion, User
from ..schemas import (
    CleaningActionOut,
    CleaningPlan,
    CleaningPreviewRequest,
    DatasetOut,
)
from ..services.cleaning import (
    cleaning_recommendations,
    execute_cleaning,
    preview_cleaning,
)
from ..services.profiling import profile_dataframe
from .datasets import _serialise


router = APIRouter(prefix="/datasets", tags=["cleaning"])


@router.get("/{dataset_id}/cleaning/recommendations")
def get_recommendations(
    dataset_id: int,
    version_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, version_id)
    frame = load_frame(version)

    return {
        "version_id": version.id,
        "recommendations": cleaning_recommendations(frame),
    }


@router.post("/{dataset_id}/cleaning/preview")
def preview(
    dataset_id: int,
    payload: CleaningPreviewRequest,
    version_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Preview a cleaning plan without persisting changes."""

    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, version_id)
    frame = load_frame(version)
    plan = CleaningPlan(**payload.model_dump())

    try:
        return preview_cleaning(frame, plan)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/{dataset_id}/cleaning/apply",
    response_model=DatasetOut,
)
def apply_cleaning(
    dataset_id: int,
    payload: CleaningPreviewRequest,
    version_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DatasetOut:
    dataset = get_owned_dataset(db, user, dataset_id)
    source_version = resolve_version(db, dataset, version_id)
    frame = load_frame(source_version)
    plan = CleaningPlan(**payload.model_dump())

    next_number = (
        max((v.version_number for v in dataset.versions), default=0) + 1
    )

    try:
        outcome = execute_cleaning(
            frame,
            plan,
            persist=True,
            storage_dir=settings.STORAGE_DIR,
            dataset_uid=dataset.uid,
            version_number=next_number,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    storage_path = None

    for step in outcome.steps:
        if step.get("operation") == "_storage":
            storage_path = step["path"]

    if not storage_path:
        raise HTTPException(
            status_code=500,
            detail="Failed to persist the cleaned data.",
        )

    profile = profile_dataframe(outcome.frame)
    label = (plan.label or "Cleaning step").strip()[:200]

    new_version = DatasetVersion(
        dataset_id=dataset.id,
        version_number=next_number,
        storage_path=storage_path,
        row_count=int(outcome.frame.shape[0]),
        column_count=int(outcome.frame.shape[1]),
        column_names=[str(c) for c in outcome.frame.columns],
        dtypes={
            str(c): str(dt)
            for c, dt in outcome.frame.dtypes.items()
        },
        label=label,
        parent_version_id=source_version.id,
        profile=profile,
        quality_score=profile["quality"]["score"],
        is_original=False,
    )

    db.add(new_version)
    db.flush()

    visible_steps = [
        step
        for step in outcome.steps
        if not str(step.get("operation", "")).startswith("_")
    ]

    action = CleaningAction(
        dataset_id=dataset.id,
        source_version_id=source_version.id,
        result_version_id=new_version.id,
        operation="cleaning_plan",
        parameters={
            "plan": plan.model_dump(),
            "steps": visible_steps,
            "warnings": outcome.warnings,
        },
        summary=outcome.summary,
        metrics_before=outcome.metrics_before,
        metrics_after=outcome.metrics_after,
    )

    db.add(action)

    dataset.current_version_id = new_version.id

    db.commit()
    db.refresh(dataset)

    return _serialise(dataset)


@router.get(
    "/{dataset_id}/cleaning/history",
    response_model=list[CleaningActionOut],
)
def history(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CleaningActionOut]:
    get_owned_dataset(db, user, dataset_id)

    actions = db.scalars(
        select(CleaningAction)
        .where(CleaningAction.dataset_id == dataset_id)
        .order_by(CleaningAction.created_at.desc())
    ).all()

    return [
        CleaningActionOut.model_validate(action)
        for action in actions
    ]


@router.post(
    "/{dataset_id}/cleaning/undo/{action_id}",
    response_model=DatasetOut,
)
def undo_cleaning(
    dataset_id: int,
    action_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DatasetOut:
    """Undo cleaning by restoring the source dataset version."""

    dataset = get_owned_dataset(db, user, dataset_id)

    action = db.get(CleaningAction, action_id)

    if action is None or action.dataset_id != dataset.id:
        raise HTTPException(
            status_code=404,
            detail="Cleaning action not found.",
        )

    if action.is_undone:
        raise HTTPException(
            status_code=409,
            detail="This action is already undone.",
        )

    source_version = db.get(
        DatasetVersion,
        action.source_version_id,
    )

    if source_version is None:
        raise HTTPException(
            status_code=410,
            detail="The source version for this action no longer exists.",
        )

    dataset.current_version_id = source_version.id
    action.is_undone = True

    db.commit()
    db.refresh(dataset)

    return _serialise(dataset)


@router.get("/{dataset_id}/cleaning/report.pdf")
def download_cleaning_report(
    dataset_id: int,
    version_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate and download a PDF cleaning report."""

    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, version_id)
    frame = load_frame(version)

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=30,
        leftMargin=30,
        topMargin=35,
        bottomMargin=35,
    )

    story = []

    story.append(
        Paragraph("DataPilot - Cleaning Report", styles["Title"])
    )
    story.append(Spacer(1, 10))

    story.append(
        Paragraph(
            f"Dataset: {dataset.name}",
            styles["Heading2"],
        )
    )
    story.append(
        Paragraph(
            f"Version: {version.version_number} - "
            f"{version.label or 'Dataset version'}",
            styles["Normal"],
        )
    )
    story.append(
        Paragraph(
            f"Generated: {datetime.now().strftime('%d %B %Y, %I:%M %p')}",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 16))

    story.append(
        Paragraph("Dataset Overview", styles["Heading2"])
    )

    overview = [
        ["Metric", "Value"],
        ["Rows", str(len(frame))],
        ["Columns", str(len(frame.columns))],
        ["Missing cells", str(int(frame.isna().sum().sum()))],
        ["Duplicate rows", str(int(frame.duplicated().sum()))],
        ["Version ID", str(version.id)],
    ]

    table = Table(overview, colWidths=[180, 300])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("PADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    story.append(table)
    story.append(Spacer(1, 16))

    story.append(
        Paragraph("Column Information", styles["Heading2"])
    )

    columns = [["Column", "Data type", "Missing values"]]

    for col in frame.columns:
        columns.append(
            [
                str(col)[:60],
                str(frame[col].dtype),
                str(int(frame[col].isna().sum())),
            ]
        )

    table = Table(columns, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story.append(table)
    story.append(Spacer(1, 16))

    actions = db.scalars(
        select(CleaningAction)
        .where(CleaningAction.dataset_id == dataset_id)
        .order_by(CleaningAction.created_at.desc())
    ).all()

    story.append(
        Paragraph("Cleaning History", styles["Heading2"])
    )

    history_rows = [
        ["Date", "Operation", "Summary", "Status"]
    ]

    for action in actions:
        history_rows.append(
            [
                action.created_at.strftime("%d-%m-%Y %H:%M")
                if action.created_at
                else "-",
                str(action.operation),
                str(action.summary or "-")[:100],
                "Undone" if action.is_undone else "Applied",
            ]
        )

    if not actions:
        history_rows.append(
            ["-", "-", "No cleaning actions recorded", "-"]
        )

    table = Table(
        history_rows,
        repeatRows=1,
        colWidths=[100, 110, 390, 70],
    )

    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("PADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    story.append(table)
    story.append(Spacer(1, 16))

    story.append(
        Paragraph(
            "Cleaned Data Preview (First 15 Rows)",
            styles["Heading2"],
        )
    )

    preview_frame = frame.iloc[:15, :8].fillna("-").astype(str)

    if len(preview_frame.columns) > 0:
        preview_rows = [
            [str(col)[:25] for col in preview_frame.columns]
        ]

        preview_rows.extend(
            [
                [value[:35] for value in row]
                for row in preview_frame.values.tolist()
            ]
        )

        table = Table(preview_rows, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("PADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )

        story.append(table)

    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            "Generated by DataPilot. "
            "This report reflects the selected dataset version.",
            styles["Italic"],
        )
    )

    doc.build(story)
    buffer.seek(0)

    filename = (
        f"datapilot_cleaning_report_v{version.version_number}.pdf"
    )

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )
