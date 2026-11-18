"""Exploratory analysis and statistical testing endpoints."""
from __future__ import annotations
import pandas as pd

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_owned_dataset, load_frame, resolve_version
from ..models import AnalysisRun, User
from ..schemas import (
    ChartRequest,
    ConfidenceIntervalRequest,
    CorrelationRequest,
    StatisticalTestRequest,
)
from ..services import statistics_engine as stats
from ..services.eda import ChartError, build_chart, suggest_charts
from ..services.statistics_engine import StatsError

router = APIRouter(prefix="/datasets", tags=["analysis"])


def _record(db: Session, dataset_id: int, version_id: int, analysis_type: str,
            title: str, parameters: dict, result: dict) -> AnalysisRun:
    run = AnalysisRun(
        dataset_id=dataset_id,
        version_id=version_id,
        analysis_type=analysis_type,
        title=title,
        parameters=parameters,
        result=result,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@router.get("/{dataset_id}/charts/suggestions")
def chart_suggestions(
    dataset_id: int,
    version_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, version_id)
    frame = load_frame(version)
    return {"suggestions": suggest_charts(frame)}


@router.post("/{dataset_id}/charts")
def create_chart(
    dataset_id: int,
    payload: ChartRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, payload.version_id)
    frame = load_frame(version)

    kwargs = {
        "x": payload.x,
        "y": payload.y,
        "group_by": payload.group_by,
        "agg": payload.agg,
        "bins": payload.bins,
        "top_n": payload.top_n,
    }
    try:
        if payload.chart_type == "correlation_heatmap":
            chart = build_chart(frame, "correlation_heatmap", method="pearson")
        elif payload.chart_type == "line":
            chart = build_chart(
                frame, "line", x=payload.x, y=payload.y, agg=payload.agg
            )
        elif payload.chart_type == "grouped_aggregate":
            chart = build_chart(
                frame, "grouped_aggregate",
                group_by=payload.group_by or payload.x,
                y=payload.y, agg=payload.agg,
            )
        else:
            chart = build_chart(frame, payload.chart_type, **kwargs)
    except ChartError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    chart["version_id"] = version.id
    _record(
        db, dataset.id, version.id, f"chart:{payload.chart_type}",
        chart.get("title", "Chart"), payload.model_dump(), chart,
    )
    return chart


@router.get("/{dataset_id}/statistics/descriptive")
def descriptive(
    dataset_id: int,
    version_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, version_id)
    frame = load_frame(version)
    return stats.descriptive_statistics(frame)


@router.post("/{dataset_id}/statistics/test")
def run_test(
    dataset_id: int,
    payload: StatisticalTestRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, payload.version_id)
    frame = load_frame(version)

    try:
        if payload.test == "pearson":
            if not payload.x or not payload.y:
                raise StatsError("Pearson correlation requires two columns (x and y).")
            result = stats.pearson_correlation(frame, payload.x, payload.y, payload.alpha)
        elif payload.test == "spearman":
            if not payload.x or not payload.y:
                raise StatsError("Spearman correlation requires two columns (x and y).")
            result = stats.spearman_correlation(frame, payload.x, payload.y, payload.alpha)
        elif payload.test == "ttest_ind":
            if not payload.x or not payload.group_column:
                raise StatsError(
                    "An independent t-test requires a numeric column (x) and a "
                    "group column (group_column)."
                )
            result = stats.independent_ttest(
                frame, payload.x, payload.group_column,
                payload.group_a, payload.group_b, payload.alpha,
            )
        elif payload.test == "ttest_rel":
            if not payload.x or not payload.y:
                raise StatsError("A paired t-test requires two numeric columns (x and y).")
            result = stats.paired_ttest(frame, payload.x, payload.y, payload.alpha)
        elif payload.test == "ttest_1samp":
            if not payload.x or payload.popmean is None:
                raise StatsError(
                    "A one-sample t-test requires a column (x) and a population "
                    "mean (popmean)."
                )
            result = stats.one_sample_ttest(frame, payload.x, payload.popmean, payload.alpha)
        elif payload.test == "chi_square":
            if not payload.x or not payload.y:
                raise StatsError("A chi-square test requires two categorical columns.")
            result = stats.chi_square_test(frame, payload.x, payload.y, payload.alpha)
        elif payload.test == "anova":
            if not payload.x or not payload.group_column:
                raise StatsError(
                    "ANOVA requires a numeric column (x) and a group column."
                )
            result = stats.one_way_anova(frame, payload.x, payload.group_column, payload.alpha)
        else:
            raise StatsError(f"Unsupported test '{payload.test}'.")
    except StatsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result["version_id"] = version.id
    _record(
        db, dataset.id, version.id, f"stats:{payload.test}",
        result.get("label", payload.test), payload.model_dump(), result,
    )
    return result


@router.post("/{dataset_id}/statistics/confidence-interval")
def confidence_interval(
    dataset_id: int,
    payload: ConfidenceIntervalRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, payload.version_id)
    frame = load_frame(version)
    try:
        result = stats.confidence_interval(frame, payload.column, payload.confidence)
    except StatsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result["version_id"] = version.id
    _record(db, dataset.id, version.id, "stats:confidence_interval",
            result["label"], payload.model_dump(), result)
    return result


@router.post("/{dataset_id}/statistics/correlations")
def correlations(
    dataset_id: int,
    payload: CorrelationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, payload.version_id)
    frame = load_frame(version)
    try:
        result = stats.correlation_matrix(frame, payload.method, payload.columns)
    except StatsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result["version_id"] = version.id
    _record(db, dataset.id, version.id, f"stats:correlation_matrix",
            f"{payload.method.capitalize()} correlation matrix",
            payload.model_dump(), result)
    return result


@router.get("/{dataset_id}/statistics/normality")
def normality(
    dataset_id: int,
    column: str = Query(...),
    version_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, version_id)
    frame = load_frame(version)
    try:
        return stats.normality_test(frame, column)
    except StatsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{dataset_id}/analysis/history")
def analysis_history(
    dataset_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    get_owned_dataset(db, user, dataset_id)
    from sqlalchemy import select

    runs = db.scalars(
        select(AnalysisRun)
        .where(AnalysisRun.dataset_id == dataset_id)
        .order_by(AnalysisRun.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": run.uid,
            "analysis_type": run.analysis_type,
            "title": run.title,
            "parameters": run.parameters,
            "created_at": run.created_at.isoformat(),
            "summary": _summarise_run(run),
        }
        for run in runs
    ]


def _summarise_run(run: AnalysisRun) -> str:
    result = run.result or {}
    if isinstance(result, dict):
        if "interpretation" in result:
            return str(result["interpretation"])[:300]
        if "score" in result:
            return f"Quality score {result['score']}"
        if "data" in result:
            return f"{len(result.get('data', []))} plotted values"
    return run.analysis_type

@router.get("/{dataset_id}/insights")
def automatic_insights(
    dataset_id: int,
    version_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Generate explainable insights directly from the selected dataset."""

    import numpy as np

    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, version_id)
    frame = load_frame(version)

    total_rows, total_columns = frame.shape
    insights = []

    def add(category, severity, title, description, recommendation, metric=None):
        insights.append({
            "id": len(insights) + 1,
            "category": category,
            "severity": severity,
            "title": title,
            "description": description,
            "recommendation": recommendation,
            "metric": metric,
        })

    if total_rows == 0 or total_columns == 0:
        return {
            "dataset_name": dataset.name,
            "version_id": version.id,
            "overview": {
                "rows": total_rows,
                "columns": total_columns,
                "insight_count": 0,
            },
            "insights": [],
        }

    # DATA QUALITY
    missing_total = int(frame.isna().sum().sum())
    missing_pct = missing_total / (total_rows * total_columns) * 100
    duplicates = int(frame.duplicated().sum())

    if missing_total:
        add(
            "data_quality",
            "high" if missing_pct >= 20 else "medium",
            "Missing values detected",
            f"{missing_total:,} cells ({missing_pct:.1f}%) contain missing values.",
            "Review missing values and decide whether to impute or remove affected records.",
            f"{missing_pct:.1f}% missing",
        )

    if duplicates:
        add(
            "data_quality",
            "medium",
            "Duplicate records found",
            f"{duplicates:,} duplicate rows were detected.",
            "Check whether these records are legitimate repetitions before removing them.",
            f"{duplicates:,} duplicates",
        )

    # NUMERIC ANALYSIS
    numeric = frame.select_dtypes(include="number")
    for col in numeric.columns:
        series = numeric[col].replace([np.inf, -np.inf], np.nan).dropna()

        if len(series) < 2:
            continue

        mean = float(series.mean())
        median = float(series.median())
        minimum = float(series.min())
        maximum = float(series.max())
        std = float(series.std())

        if mean != 0 and abs(mean - median) / abs(mean) > 0.5:
            add(
                "distribution",
                "medium",
                f"Unusual distribution in {col}",
                f"The mean ({mean:,.2f}) differs considerably from the median ({median:,.2f}).",
                "Inspect the distribution and check for extreme values or skew.",
                f"Mean: {mean:,.2f}",
            )

        q1 = float(series.quantile(0.25))
        q3 = float(series.quantile(0.75))
        iqr = q3 - q1

        if iqr > 0:
            outliers = int(
                ((series < q1 - 1.5 * iqr) | (series > q3 + 1.5 * iqr)).sum()
            )
            if outliers:
                pct = outliers / len(series) * 100
                add(
                    "outlier",
                    "medium" if pct < 5 else "high",
                    f"Potential outliers in {col}",
                    f"{outliers:,} values ({pct:.1f}%) fall outside the 1.5×IQR range.",
                    "Investigate these values before deciding whether they are errors or valid extremes.",
                    f"{outliers:,} outliers",
                )

        if std == 0:
            add(
                "distribution",
                "low",
                f"{col} has no variation",
                "Every available value in this column is identical.",
                "Check whether this column provides useful analytical information.",
                "Zero variation",
            )

        elif minimum == maximum:
            continue

    # CATEGORICAL ANALYSIS
    categorical = frame.select_dtypes(
        include=["object", "category", "bool", "string"]
    )

    for col in categorical.columns:
        counts = frame[col].dropna().value_counts()

        if len(counts) == 0:
            continue

        top_value = str(counts.index[0])
        top_count = int(counts.iloc[0])
        share = top_count / len(frame[col].dropna()) * 100

        if share >= 70 and len(counts) > 1:
            add(
                "category",
                "low",
                f"{col} is dominated by one category",
                f"'{top_value}' represents {share:.1f}% of non-missing values.",
                "Check whether this imbalance is expected and whether smaller categories need separate analysis.",
                f"{share:.1f}% share",
            )

        if len(counts) == 1:
            add(
                "distribution",
                "low",
                f"{col} contains only one category",
                f"All non-missing records have the value '{top_value}'.",
                "Consider whether this column is useful for comparisons.",
                "1 unique value",
            )

    # CORRELATION ANALYSIS
    if len(numeric.columns) >= 2:
        corr = numeric.corr().abs()

        for i, col_a in enumerate(corr.columns):
            for col_b in corr.columns[i + 1:]:
                value = corr.loc[col_a, col_b]

                if pd_is_valid_number(value) and value >= 0.8:
                    add(
                        "relationship",
                        "medium",
                        f"Strong relationship: {col_a} and {col_b}",
                        f"These numeric columns have an absolute correlation of {value:.2f}.",
                        "Investigate whether these variables move together and whether they measure overlapping information.",
                        f"Correlation: {value:.2f}",
                    )

    # OVERVIEW
    insights.sort(
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}.get(item["severity"], 3)
        )
    )

    return {
        "dataset_name": dataset.name,
        "version_id": version.id,
        "overview": {
            "rows": int(total_rows),
            "columns": int(total_columns),
            "numeric_columns": int(len(numeric.columns)),
            "categorical_columns": int(len(categorical.columns)),
            "missing_cells": missing_total,
            "duplicate_rows": duplicates,
            "insight_count": len(insights),
        },
        "insights": insights[:20],
    }


def pd_is_valid_number(value):
    """Safely check whether a correlation is a finite number."""
    import math
    return value is not None and math.isfinite(float(value))
