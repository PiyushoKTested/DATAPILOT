"""Data cleaning engine.

Design rules:
  * The original dataset version is never mutated — cleaning always produces a
    new immutable version (parquet snapshot).
  * Every operation returns explicit before/after metrics so the UI can show a
    real comparison, and so the operation is auditable.
  * No cleaning runs implicitly: a user-approved ``CleaningPlan`` drives it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..config import settings
from ..schemas import CleaningPlan
from ..utils.serialize import round_number, to_jsonable
from .ingest import save_version_snapshot
from .profiling import compute_quality, profile_dataframe
from .type_inference import CATEGORICAL, DATETIME, NUMERIC, TEXT, classify_all, coerce_column


@dataclass
class CleaningOutcome:
    frame: pd.DataFrame
    summary: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    metrics_before: dict[str, Any] = field(default_factory=dict)
    metrics_after: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _snapshot_metrics(df: pd.DataFrame) -> dict[str, Any]:
    profile = profile_dataframe(df)
    return {
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "missing_cells": int(df.isna().sum().sum()),
        "missing_pct": round_number(
            100 * df.isna().sum().sum() / max(df.shape[0] * df.shape[1], 1)
        ),
        "duplicate_rows": int(df.duplicated().sum()),
        "quality_score": profile["quality"]["score"],
        "quality_grade": profile["quality"]["grade"],
        "column_count": int(df.shape[1]),
    }


def _apply_imputation(df: pd.DataFrame, column: str, strategy: str,
                      constant_value: Any) -> dict[str, Any]:
    if column not in df.columns:
        raise ValueError(f"Column '{column}' does not exist in this dataset.")

    missing_before = int(df[column].isna().sum())
    if missing_before == 0:
        return {
            "column": column,
            "strategy": strategy,
            "affected": 0,
            "detail": f"'{column}' had no missing values; nothing changed.",
        }

    series = df[column]
    kinds = classify_all(df)
    kind = kinds.get(column, TEXT)

    if strategy == "drop_rows":
        df.dropna(subset=[column], inplace=True)
        return {
            "column": column,
            "strategy": strategy,
            "affected": missing_before,
            "detail": f"Dropped {missing_before} rows with missing '{column}'.",
        }

    if strategy == "constant":
        fill_value = constant_value
        if kind == NUMERIC and fill_value is not None:
            fill_value = pd.to_numeric(pd.Series([fill_value]), errors="coerce").iloc[0]
        if fill_value is None:
            fill_value = "" if kind in (CATEGORICAL, TEXT) else 0
        df[column] = series.fillna(fill_value)
        return {
            "column": column,
            "strategy": strategy,
            "affected": missing_before,
            "detail": f"Filled {missing_before} missing '{column}' values with constant {fill_value!r}.",
        }

    if kind in (CATEGORICAL, TEXT) and strategy in ("mean", "median"):
        raise ValueError(
            f"Cannot use '{strategy}' imputation on non-numeric column '{column}'."
        )

    if kind == DATETIME:
        # Arithmetic means are not meaningful for dates; use the median date.
        parsed = pd.to_datetime(series, errors="coerce", format="mixed")
        fill_value = parsed.median()
        df[column] = parsed.fillna(fill_value)
        return {
            "column": column,
            "strategy": "median",
            "affected": missing_before,
            "detail": f"Filled {missing_before} missing dates in '{column}' with the median date {fill_value:%Y-%m-%d}.",
        }

    numeric = pd.to_numeric(series, errors="coerce")
    if strategy == "mean":
        fill_value = numeric.mean()
    elif strategy == "median":
        fill_value = numeric.median()
    elif strategy == "mode":
        mode_series = numeric.mode()
        fill_value = mode_series.iloc[0] if not mode_series.empty else None
    else:
        raise ValueError(f"Unknown imputation strategy {strategy!r}.")

    if fill_value is None or (isinstance(fill_value, float) and np.isnan(fill_value)):
        raise ValueError(f"Cannot compute a '{strategy}' for '{column}' — column is empty.")

    df[column] = numeric.fillna(fill_value)
    return {
        "column": column,
        "strategy": strategy,
        "affected": missing_before,
        "fill_value": round_number(fill_value),
        "detail": (
            f"Filled {missing_before} missing values in '{column}' using the "
            f"{strategy} ({round_number(fill_value)})."
        ),
    }


def preview_cleaning(df: pd.DataFrame, plan: CleaningPlan) -> dict[str, Any]:
    """Run the plan on a copy and report what would change, without persisting."""
    outcome = execute_cleaning(df.copy(), plan, persist=False)
    return {
        "metrics_before": outcome.metrics_before,
        "metrics_after": outcome.metrics_after,
        "steps": outcome.steps,
        "summary": outcome.summary,
        "warnings": outcome.warnings,
        "delta": {
            key: (outcome.metrics_after.get(key) or 0) - (outcome.metrics_before.get(key) or 0)
            for key in ("rows", "columns", "missing_cells", "duplicate_rows")
        },
        "quality_delta": round_number(
            (outcome.metrics_after.get("quality_score") or 0)
            - (outcome.metrics_before.get("quality_score") or 0)
        ),
    }


def execute_cleaning(df: pd.DataFrame, plan: CleaningPlan, *, persist: bool = True,
                     storage_dir=None, dataset_uid: str = "preview",
                     version_number: int = 0) -> CleaningOutcome:
    """Apply a cleaning plan to a dataframe copy."""
    before = _snapshot_metrics(df)
    steps: list[dict[str, Any]] = []
    warnings: list[str] = []

    working = df.copy()

    # 1. Whitespace trimming on text-like columns.
    if plan.trim_whitespace:
        trimmed_columns = 0
        for column in working.columns:
            if working[column].dtype == object or str(working[column].dtype).startswith("string"):
                non_null = working[column].dropna()
                if non_null.empty:
                    continue
                stripped = working[column].astype("string").str.strip()
                working[column] = stripped
                trimmed_columns += 1
        steps.append({
            "operation": "trim_whitespace",
            "affected": trimmed_columns,
            "detail": f"Trimmed leading/trailing whitespace on {trimmed_columns} text columns.",
        })

    # 2. Drop columns that are entirely empty.
    if plan.drop_empty_columns:
        empty_columns = [c for c in working.columns if working[c].isna().all()]
        if empty_columns:
            working.drop(columns=empty_columns, inplace=True)
        steps.append({
            "operation": "drop_empty_columns",
            "affected": len(empty_columns),
            "columns": empty_columns,
            "detail": f"Dropped {len(empty_columns)} fully empty columns.",
        })

    # 3. Drop constant columns.
    if plan.drop_constant_columns:
        constant_columns = [
            c for c in working.columns
            if working[c].nunique(dropna=True) <= 1
        ]
        if constant_columns:
            working.drop(columns=constant_columns, inplace=True)
        steps.append({
            "operation": "drop_constant_columns",
            "affected": len(constant_columns),
            "columns": constant_columns,
            "detail": f"Dropped {len(constant_columns)} constant (single-value) columns.",
        })

    # 4. Type corrections.
    for correction in plan.type_corrections:
        if correction.column not in working.columns:
            warnings.append(f"Skipped type correction: column '{correction.column}' not found.")
            continue
        try:
            converted, failures = coerce_column(working[correction.column], correction.target_type)
            working[correction.column] = converted
            steps.append({
                "operation": "type_correction",
                "column": correction.column,
                "target_type": correction.target_type,
                "affected": failures,
                "detail": (
                    f"Converted '{correction.column}' to {correction.target_type}"
                    + (f"; {failures} values could not be parsed and became null." if failures else ".")
                ),
            })
        except (ValueError, TypeError) as exc:
            warnings.append(f"Type correction failed for '{correction.column}': {exc}")

    # 5. Missing-value imputation.
    for step in plan.missing_values:
        try:
            result = _apply_imputation(
                working, step.column, step.strategy, step.constant_value
            )
            steps.append({"operation": "impute_missing", **result})
        except ValueError as exc:
            warnings.append(str(exc))

    # 6. Duplicate removal.
    if plan.drop_duplicates:
        subset = plan.duplicate_subset or None
        if subset:
            missing_cols = [c for c in subset if c not in working.columns]
            if missing_cols:
                warnings.append(
                    f"Duplicate subset ignored unknown columns: {missing_cols}"
                )
                subset = [c for c in subset if c in working.columns] or None
        dupes_before = int(working.duplicated(subset=subset).sum())
        if dupes_before:
            working.drop_duplicates(subset=subset, inplace=True, keep="first")
        steps.append({
            "operation": "drop_duplicates",
            "affected": dupes_before,
            "subset": subset or "all columns",
            "detail": f"Removed {dupes_before} duplicate rows"
                      + (f" based on {subset}." if subset else " (all columns compared)."),
        })

    # 7. Outlier treatment (IQR based).
    for outlier in plan.outliers:
        column = outlier.column
        if column not in working.columns:
            warnings.append(f"Skipped outlier treatment: column '{column}' not found.")
            continue
        numeric = pd.to_numeric(working[column], errors="coerce")
        if numeric.dropna().empty:
            warnings.append(f"Skipped outlier treatment: '{column}' is not numeric.")
            continue
        q1, q3 = numeric.quantile(0.25), numeric.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            warnings.append(f"Skipped outlier treatment: '{column}' has zero IQR.")
            steps.append({
                "operation": "outliers",
                "column": column,
                "strategy": outlier.strategy,
                "affected": 0,
                "detail": (
                    f"No outlier treatment applied to '{column}': the "
                    "interquartile range is zero (all values nearly identical)."
                ),
            })
            continue
        lower = q1 - outlier.multiplier * iqr
        upper = q3 + outlier.multiplier * iqr
        mask = (numeric < lower) | (numeric > upper)
        affected = int(mask.sum())
        if affected == 0:
            steps.append({
                "operation": "outliers",
                "column": column,
                "strategy": outlier.strategy,
                "affected": 0,
                "detail": f"No outliers found in '{column}' at {outlier.multiplier}×IQR.",
            })
            continue

        if outlier.strategy == "remove":
            working = working.loc[~mask].reset_index(drop=True)
            detail = f"Removed {affected} outlier rows from '{column}'."
        elif outlier.strategy == "clip":
            working[column] = numeric.clip(lower=lower, upper=upper)
            detail = (
                f"Clipped {affected} outliers in '{column}' to the IQR fences "
                f"[{round_number(lower)}, {round_number(upper)}]."
            )
        elif outlier.strategy == "cap_percentile":
            p1, p99 = numeric.quantile(0.01), numeric.quantile(0.99)
            working[column] = numeric.clip(lower=p1, upper=p99)
            detail = (
                f"Capped {affected} outliers in '{column}' to the 1st/99th "
                f"percentiles [{round_number(p1)}, {round_number(p99)}]."
            )
        else:
            detail = f"No outlier action applied to '{column}'."

        steps.append({
            "operation": "outliers",
            "column": column,
            "strategy": outlier.strategy,
            "affected": affected,
            "lower_fence": round_number(lower),
            "upper_fence": round_number(upper),
            "detail": detail,
        })

    # Reset index after any row removal so snapshots are consistent.
    working = working.reset_index(drop=True)
    after = _snapshot_metrics(working)

    summary_bits = [f"{len(steps)} cleaning operation(s) applied"]
    summary_bits.append(f"rows {before['rows']} → {after['rows']}")
    summary_bits.append(f"columns {before['columns']} → {after['columns']}")
    summary_bits.append(
        f"missing cells {before['missing_cells']} → {after['missing_cells']}"
    )
    summary_bits.append(
        f"quality {before['quality_score']} → {after['quality_score']}"
    )

    storage_path = None
    if persist:
        path = save_version_snapshot(
            working,
            storage_dir or settings.STORAGE_DIR,
            dataset_uid,
            version_number,
        )
        storage_path = str(path)

    outcome = CleaningOutcome(
        frame=working,
        summary="; ".join(summary_bits) + ".",
        steps=steps,
        metrics_before=before,
        metrics_after=after,
        warnings=warnings,
    )
    if storage_path:
        outcome.steps.append({"operation": "_storage", "path": storage_path})
    return outcome


def cleaning_recommendations(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Suggest concrete, safe cleaning actions derived from the profile."""
    profile = profile_dataframe(df)
    recommendations: list[dict[str, Any]] = []

    for col in profile["columns"]:
        if col["missing"] > 0:
            kind = col["kind"]
            strategy = "median" if kind == NUMERIC else "mode"
            recommendations.append({
                "type": "missing_values",
                "column": col["name"],
                "severity": "high" if col["missing_pct"] > 20 else "medium",
                "suggested_strategy": strategy,
                "reason": (
                    f"{col['missing']:,} missing values ({col['missing_pct']}%). "
                    f"Suggested: {strategy} imputation."
                ),
            })

    if profile["duplicates"]["duplicate_rows"] > 0:
        recommendations.append({
            "type": "duplicates",
            "severity": "high",
            "count": profile["duplicates"]["duplicate_rows"],
            "reason": f"{profile['duplicates']['duplicate_rows']:,} fully duplicated rows detected.",
            "suggested_strategy": "drop_duplicates",
        })

    for col in profile["columns"]:
        if col["kind"] == NUMERIC and col.get("stats"):
            outliers = col["stats"]["outlier_count"]
            if outliers:
                pct = col["stats"]["outlier_pct"] or 0
                recommendations.append({
                    "type": "outliers",
                    "column": col["name"],
                    "severity": "medium" if pct < 5 else "high",
                    "count": outliers,
                    "reason": (
                        f"{outliers:,} outliers ({pct}% of values) outside "
                        f"[{col['stats']['lower_fence']}, {col['stats']['upper_fence']}]."
                    ),
                    "suggested_strategy": "clip",
                })

    recommendations.sort(
        key=lambda r: {"high": 0, "medium": 1, "low": 2}.get(r["severity"], 3)
    )
    return to_jsonable(recommendations)
