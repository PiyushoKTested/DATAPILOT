"""Report generation endpoints (PDF + HTML)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user, get_owned_dataset, load_frame, resolve_version
from ..models import CleaningAction, Conversation, DatasetVersion, Report, User
from ..schemas import ReportOut, ReportRequest
from ..services.eda import (
    bar_chart,
    box_plot,
    build_chart,
    correlation_heatmap,
    histogram,
    pie_chart,
    scatter_plot,
    ChartError,
)
from ..services.profiling import key_findings, numeric_summary_table, profile_dataframe
from ..services.reports import build_html, build_pdf
from ..services.type_inference import NUMERIC, CATEGORICAL, DATETIME, TEXT, classify_all
from .datasets import human_size

router = APIRouter(tags=["reports"])


def _safe_charts(frame, profile: dict) -> list[dict]:
    """Build the chart set for a report, skipping any that the data cannot support."""
    charts: list[dict] = []
    numeric = profile["column_groups"]["numeric"]
    categorical = profile["column_groups"]["categorical"]
    datetimes = profile["column_groups"]["datetime"]

    if numeric:
        try:
            charts.append(histogram(frame, numeric[0], 20))
        except ChartError:
            pass
    if categorical:
        try:
            charts.append(bar_chart(frame, categorical[0], 10))
        except ChartError:
            pass
        try:
            charts.append(pie_chart(frame, categorical[0], 8))
        except ChartError:
            pass
    if len(numeric) >= 2:
        try:
            charts.append(scatter_plot(frame, numeric[0], numeric[1]))
        except ChartError:
            pass
        try:
            charts.append(correlation_heatmap(frame, "pearson"))
        except ChartError:
            pass
        try:
            charts.append(box_plot(frame, numeric[0]))
        except ChartError:
            pass
    if categorical and numeric:
        try:
            charts.append(
                build_chart(
                    frame, "grouped_aggregate",
                    group_by=categorical[0], y=numeric[0], agg="mean",
                )
            )
        except ChartError:
            pass
    return charts


def _collect_sections(
    db: Session,
    dataset,
    version: DatasetVersion,
    frame,
    *,
    include_charts: bool,
    include_statistics: bool,
    include_conversation: bool,
    conversation_id: int | None,
    title: str,
) -> dict:
    from ..services import statistics_engine as stats

    profile = profile_dataframe(frame)
    kinds = classify_all(frame)
    project = dataset.project

    cleaning_actions = db.scalars(
        select(CleaningAction)
        .where(CleaningAction.dataset_id == dataset.id, CleaningAction.is_undone == False)  # noqa: E712
        .order_by(CleaningAction.created_at.asc())
    ).all()

    cleaning_history: list[dict] = []
    before: dict = {}
    after: dict = {}
    for action in cleaning_actions:
        for step in (action.parameters or {}).get("steps", []):
            cleaning_history.append({
                "operation": step.get("operation", ""),
                "column": step.get("column"),
                "affected": step.get("affected"),
                "detail": step.get("detail", ""),
            })
        if not before:
            before = action.metrics_before or {}
        after = action.metrics_after or {}

    statistical_analyses: list[dict] = []

    if include_statistics:
        numeric_cols = profile["column_groups"]["numeric"]
        categorical_cols = profile["column_groups"]["categorical"]

        if len(numeric_cols) >= 2:
            try:
                corr = stats.correlation_matrix(frame, "pearson")
                strongest = corr.get("strongest")
                statistical_analyses.append({
                    "label": "Pearson correlation matrix",
                    "interpretation": corr["interpretation"],
                    "details": [
                        ("Columns analysed", len(corr["columns"])),
                        ("Strongest pair", f"{strongest['a']} ↔ {strongest['b']}" if strongest else "n/a"),
                        ("Strongest r", strongest["r"] if strongest else None),
                        ("Strongest strength", strongest["strength"] if strongest else None),
                    ],
                    "assumptions": corr["assumptions"],
                    "limitations": corr["limitations"],
                })
            except Exception:  # noqa: BLE001 - a report must still generate
                pass

        if numeric_cols:
            try:
                ci = stats.confidence_interval(frame, numeric_cols[0], 0.95)
                statistical_analyses.append({
                    "label": f"95% confidence interval — {numeric_cols[0]}",
                    "interpretation": ci["interpretation"],
                    "details": [
                        ("Sample mean", ci["mean"]),
                        ("Standard error", ci["std_error"]),
                        ("Lower bound", ci["lower"]),
                        ("Upper bound", ci["upper"]),
                        ("n", ci["n"]),
                    ],
                    "assumptions": ci["assumptions"],
                    "limitations": ci["limitations"],
                })
            except Exception:  # noqa: BLE001
                pass

        if numeric_cols and categorical_cols:
            try:
                test = stats.independent_ttest(frame, numeric_cols[0], categorical_cols[0])
                statistical_analyses.append({
                    "label": f"Welch's t-test — {numeric_cols[0]} by {categorical_cols[0]}",
                    "interpretation": test["interpretation"],
                    "details": [
                        ("Groups compared", " vs ".join(test["groups"])),
                        ("t statistic", test["statistic"]),
                        ("p-value", test["p_value"]),
                        ("Significant", test["significant"]),
                        ("Mean difference", test["mean_difference"]),
                    ],
                    "assumptions": test["assumptions"],
                    "limitations": test["limitations"],
                })
            except Exception:  # noqa: BLE001
                pass

        if len(categorical_cols) >= 2:
            try:
                chi = stats.chi_square_test(frame, categorical_cols[0], categorical_cols[1])
                statistical_analyses.append({
                    "label": (
                        f"Chi-square — {categorical_cols[0]} vs {categorical_cols[1]}"
                    ),
                    "interpretation": chi["interpretation"],
                    "details": [
                        ("Chi-square", chi["statistic"]),
                        ("Degrees of freedom", chi["degrees_of_freedom"]),
                        ("p-value", chi["p_value"]),
                        ("Cramér's V", chi["cramers_v"]),
                        ("Significant", chi["significant"]),
                    ],
                    "assumptions": chi["assumptions"],
                    "limitations": chi["limitations"],
                })
            except Exception:  # noqa: BLE001
                pass

    conversation_payload: list[dict] = []
    if include_conversation:
        conversation = None
        if conversation_id is not None:
            conversation = db.get(Conversation, conversation_id)
            if conversation and conversation.dataset_id != dataset.id:
                conversation = None
        if conversation is None:
            conversation = db.scalar(
                select(Conversation)
                .where(Conversation.dataset_id == dataset.id)
                .order_by(Conversation.created_at.desc())
            )
        if conversation:
            labels = {"llm": "Local LLM (Ollama)", "rule_based": "Rule-based engine",
                      "system": "System"}
            for message in conversation.messages:
                conversation_payload.append({
                    "role": message.role,
                    "content": message.content,
                    "engine": message.engine,
                    "engine_label": labels.get(message.engine, message.engine),
                })

    return {
        "title": title,
        "dataset_name": dataset.name,
        "project_name": project.name if project else "n/a",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "app_version": settings.APP_VERSION,
        "overview": {
            "rows": int(frame.shape[0]),
            "columns": int(frame.shape[1]),
            "source_format": dataset.source_format.upper(),
            "original_filename": dataset.original_filename,
            "file_size_human": human_size(dataset.file_size_bytes),
            "version_label": f"v{version.version_number} — {version.label}",
            "numeric_count": len(profile["column_groups"]["numeric"]),
            "categorical_count": len(profile["column_groups"]["categorical"]),
            "datetime_count": len(profile["column_groups"]["datetime"]),
            "missing_cells": profile["missing_total"],
            "duplicate_rows": profile["duplicates"]["duplicate_rows"],
        },
        "quality": profile["quality"],
        "findings": key_findings(profile),
        "column_profile": [
            {k: col[k] for k in ("name", "kind", "non_null", "missing",
                                 "missing_pct", "unique")}
            for col in profile["columns"]
        ],
        "descriptive_statistics": numeric_summary_table(frame),
        "cleaning_history": cleaning_history,
        "cleaning_before": before,
        "cleaning_after": after,
        "statistical_analyses": statistical_analyses,
        "charts": _safe_charts(frame, profile) if include_charts else [],
        "conversation": conversation_payload,
        "limitations": [
            "Results describe only the uploaded sample and do not establish causation.",
            "Statistical tests assume independent observations; repeated measures require "
            "different methods.",
            "Automated semantic type detection is heuristic — verify column types before "
            "relying on aggregate figures.",
            "Missing values were handled per the recorded cleaning plan; a different "
            "approach can change the results.",
            "For large datasets, scatter plots are sampled for rendering, so visual "
            "point density is approximate.",
        ],
    }


@router.post("/datasets/{dataset_id}/reports", response_model=ReportOut)
def generate_report(
    dataset_id: int,
    payload: ReportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportOut:
    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, payload.version_id)
    frame = load_frame(version)

    sections = _collect_sections(
        db, dataset, version, frame,
        include_charts=payload.include_charts,
        include_statistics=payload.include_statistics,
        include_conversation=payload.include_conversation,
        conversation_id=payload.conversation_id,
        title=payload.title,
    )

    settings.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(
        ch if ch.isalnum() or ch in "-_" else "_" for ch in dataset.name
    )[:60]
    filename = f"{safe_name}_v{version.version_number}_{stamp}.{payload.fmt}"
    output_path = settings.REPORT_DIR / filename

    try:
        if payload.fmt == "pdf":
            build_pdf(sections, output_path)
        else:
            output_path.write_text(build_html(sections), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"Report generation failed: {exc}"
        ) from exc

    report = Report(
        dataset_id=dataset.id,
        version_id=version.id,
        title=payload.title,
        fmt=payload.fmt,
        file_path=str(output_path),
        sections={
            "include_charts": payload.include_charts,
            "include_statistics": payload.include_statistics,
            "include_conversation": payload.include_conversation,
        },
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return ReportOut.model_validate(report)


@router.get("/datasets/{dataset_id}/reports", response_model=list[ReportOut])
def list_reports(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ReportOut]:
    get_owned_dataset(db, user, dataset_id)
    reports = db.scalars(
        select(Report)
        .where(Report.dataset_id == dataset_id)
        .order_by(Report.created_at.desc())
    ).all()
    return [ReportOut.model_validate(r) for r in reports]


@router.get("/reports/{report_uid}/download")
def download_report(
    report_uid: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    report = db.scalar(select(Report).where(Report.uid == report_uid))
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    get_owned_dataset(db, user, report.dataset_id)

    path = Path(report.file_path)
    if not path.exists():
        raise HTTPException(
            status_code=410,
            detail="The report file is no longer on disk. Regenerate it.",
        )
    media = (
        "application/pdf" if report.fmt == "pdf"
        else "text/html; charset=utf-8"
    )
    return FileResponse(path, media_type=media, filename=path.name)


@router.delete("/reports/{report_uid}", status_code=204, response_model=None)
def delete_report(
    report_uid: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    report = db.scalar(select(Report).where(Report.uid == report_uid))
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    get_owned_dataset(db, user, report.dataset_id)
    path = Path(report.file_path)
    db.delete(report)
    db.commit()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


@router.get("/datasets/{dataset_id}/dashboard")
def dashboard(
    dataset_id: int,
    version_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Aggregate KPI payload for the dashboard — all values computed live."""
    from ..models import AnalysisRun

    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, version_id)
    frame = load_frame(version)
    profile = profile_dataframe(frame)

    runs = db.scalars(
        select(AnalysisRun)
        .where(AnalysisRun.dataset_id == dataset.id)
        .order_by(AnalysisRun.created_at.desc())
        .limit(8)
    ).all()
    reports = db.scalars(
        select(Report)
        .where(Report.dataset_id == dataset.id)
        .order_by(Report.created_at.desc())
        .limit(5)
    ).all()
    conversations = db.scalars(
        select(Conversation)
        .where(Conversation.dataset_id == dataset.id)
        .order_by(Conversation.created_at.desc())
        .limit(5)
    ).all()

    return {
        "kpis": {
            "rows": int(frame.shape[0]),
            "columns": int(frame.shape[1]),
            "quality_score": profile["quality"]["score"],
            "quality_grade": profile["quality"]["grade"],
            "missing_cells": profile["missing_total"],
            "duplicate_rows": profile["duplicates"]["duplicate_rows"],
            "numeric_columns": len(profile["column_groups"]["numeric"]),
            "categorical_columns": len(profile["column_groups"]["categorical"]),
            "version_count": len(dataset.versions),
            "analysis_count": len(runs),
            "report_count": len(reports),
            "conversation_count": len(conversations),
        },
        "quality": profile["quality"],
        "findings": key_findings(profile),
        "column_groups": profile["column_groups"],
        "recent_analyses": [
            {
                "id": run.uid,
                "title": run.title,
                "analysis_type": run.analysis_type,
                "created_at": run.created_at.isoformat(),
            }
            for run in runs
        ],
        "recent_reports": [
            {
                "uid": report.uid, "title": report.title, "fmt": report.fmt,
                "created_at": report.created_at.isoformat(),
            }
            for report in reports
        ],
        "version": {
            "id": version.id,
            "number": version.version_number,
            "label": version.label,
        },
    }
