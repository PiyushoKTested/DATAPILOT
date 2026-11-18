"""Automated data profiling.

Produces per-column statistics, missing/duplicate detection, IQR outlier counts
and a documented data-quality score. Every number comes from the actual data.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..config import settings
from ..utils.serialize import round_number, safe_number, to_jsonable
from .type_inference import CATEGORICAL, DATETIME, NUMERIC, TEXT, classify_all

# ---------------------------------------------------------------------------
# Data-quality scoring (documented methodology)
# ---------------------------------------------------------------------------
# The score is a weighted sum of four components, each in [0, 100]:
#
#   1. Completeness  (weight 0.40) = 100 * (1 - missing_cells / total_cells)
#   2. Uniqueness    (weight 0.25) = 100 * (1 - duplicate_rows / total_rows)
#   3. Validity      (weight 0.20) = 100 * (1 - invalid_typed_cells / total_cells)
#        "invalid" = values that failed numeric/datetime parsing in a column that
#        is predominantly of that type (structural type damage).
#   4. Outlier health (weight 0.15) = 100 * (1 - outlier_cells / numeric_cells)
#        Outliers use the 1.5 * IQR rule per numeric column.
#
# Each component is reported alongside the final score so the number is fully
# auditable rather than a magic value.
QUALITY_WEIGHTS = {
    "completeness": 0.40,
    "uniqueness": 0.25,
    "validity": 0.20,
    "outlier_health": 0.15,
}


def _describe_numeric(series: pd.Series) -> dict[str, Any]:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return {}
    q1 = float(clean.quantile(0.25))
    q3 = float(clean.quantile(0.75))
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    outlier_mask = (clean < lower) | (clean > upper)
    mode_series = clean.mode()
    return {
        "count": int(clean.count()),
        "mean": round_number(clean.mean()),
        "median": round_number(clean.median()),
        "mode": round_number(mode_series.iloc[0]) if not mode_series.empty else None,
        "std": round_number(clean.std(ddof=1)) if len(clean) > 1 else None,
        "variance": round_number(clean.var(ddof=1)) if len(clean) > 1 else None,
        "min": round_number(clean.min()),
        "max": round_number(clean.max()),
        "q1": round_number(q1),
        "q3": round_number(q3),
        "iqr": round_number(iqr),
        "range": round_number(clean.max() - clean.min()),
        "skewness": round_number(clean.skew()) if len(clean) > 2 else None,
        "kurtosis": round_number(clean.kurt()) if len(clean) > 3 else None,
        "sum": round_number(clean.sum()),
        "lower_fence": round_number(lower),
        "upper_fence": round_number(upper),
        "outlier_count": int(outlier_mask.sum()),
        "outlier_pct": round_number(100 * outlier_mask.mean()),
        "zeros": int((clean == 0).sum()),
        "negatives": int((clean < 0).sum()),
    }


def _describe_datetime(series: pd.Series) -> dict[str, Any]:
    parsed = pd.to_datetime(series, errors="coerce", format="mixed").dropna()
    if parsed.empty:
        return {}
    span_days = (parsed.max() - parsed.min()).total_seconds() / 86400
    return {
        "count": int(parsed.count()),
        "min": parsed.min().isoformat(),
        "max": parsed.max().isoformat(),
        "span_days": round_number(span_days),
        "unique_dates": int(parsed.dt.date.nunique()),
    }


def _frequency_table(series: pd.Series, top_n: int = 10) -> list[dict[str, Any]]:
    counts = series.dropna().astype(str).value_counts().head(top_n)
    total = int(series.notna().sum())
    return [
        {
            "value": str(index),
            "count": int(count),
            "percentage": round_number(100 * count / total) if total else 0.0,
        }
        for index, count in counts.items()
    ]


def profile_column(df: pd.DataFrame, column: str, kind: str) -> dict[str, Any]:
    series = df[column]
    total = len(series)
    nulls = int(series.isna().sum())
    info: dict[str, Any] = {
        "name": column,
        "kind": kind,
        "pandas_dtype": str(series.dtype),
        "count": total,
        "non_null": int(total - nulls),
        "missing": nulls,
        "missing_pct": round_number(100 * nulls / total) if total else 0.0,
        "unique": int(series.nunique(dropna=True)),
        "unique_pct": round_number(100 * series.nunique(dropna=True) / max(total - nulls, 1)),
        "memory_bytes": int(series.memory_usage(deep=True)),
    }

    if kind == NUMERIC:
        info["stats"] = _describe_numeric(series)
    elif kind == DATETIME:
        info["stats"] = _describe_datetime(series)
    else:
        info["frequency"] = _frequency_table(series)
        non_null = series.dropna().astype(str)
        if not non_null.empty:
            lengths = non_null.str.len()
            info["stats"] = {
                "count": int(non_null.count()),
                "min_length": int(lengths.min()),
                "max_length": int(lengths.max()),
                "avg_length": round_number(lengths.mean()),
                "top_value": str(non_null.mode().iloc[0]) if not non_null.mode().empty else None,
            }
    info["sample_values"] = [to_jsonable(v) for v in series.dropna().head(5).tolist()]
    return info


def compute_quality(df: pd.DataFrame, column_kinds: dict[str, str],
                    column_profiles: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute the documented data-quality score with its components."""
    n_rows, n_cols = df.shape
    total_cells = max(n_rows * n_cols, 1)

    missing_cells = int(df.isna().sum().sum())
    completeness = 100.0 * (1 - missing_cells / total_cells)

    duplicate_rows = int(df.duplicated().sum())
    uniqueness = 100.0 * (1 - duplicate_rows / max(n_rows, 1))

    # Validity: cells that are non-null text in a numeric/datetime column that
    # fail to parse. This catches structural type damage from imports.
    invalid_cells = 0
    checked_cells = 0
    for column, kind in column_kinds.items():
        series = df[column]
        non_null = series.dropna()
        if non_null.empty:
            continue
        if kind == NUMERIC:
            checked_cells += len(non_null)
            coerced = pd.to_numeric(
                non_null.astype(str).str.replace(",", "", regex=False), errors="coerce"
            )
            invalid_cells += int(coerced.isna().sum())
        elif kind == DATETIME:
            checked_cells += len(non_null)
            coerced = pd.to_datetime(non_null, errors="coerce", format="mixed")
            invalid_cells += int(coerced.isna().sum())
    validity = 100.0 * (1 - invalid_cells / max(checked_cells, 1)) if checked_cells else 100.0

    numeric_cells = int(
        sum(p["non_null"] for p in column_profiles if p["kind"] == NUMERIC)
    )
    outlier_cells = int(
        sum(
            p.get("stats", {}).get("outlier_count", 0)
            for p in column_profiles
            if p["kind"] == NUMERIC
        )
    )
    outlier_health = (
        100.0 * (1 - outlier_cells / numeric_cells) if numeric_cells else 100.0
    )

    components = {
        "completeness": round_number(completeness, 2),
        "uniqueness": round_number(uniqueness, 2),
        "validity": round_number(validity, 2),
        "outlier_health": round_number(outlier_health, 2),
    }
    overall = sum(components[name] * weight for name, weight in QUALITY_WEIGHTS.items())

    grade = "A"
    for threshold, letter in ((90, "A"), (80, "B"), (70, "C"), (60, "D")):
        if overall >= threshold:
            grade = letter
            break
    else:
        grade = "F"

    issues: list[str] = []
    if missing_cells:
        issues.append(
            f"{missing_cells:,} missing cells ({100 * missing_cells / total_cells:.1f}% of the table)."
        )
    if duplicate_rows:
        issues.append(f"{duplicate_rows:,} fully duplicated rows.")
    if invalid_cells:
        issues.append(f"{invalid_cells:,} values failed type validation.")
    if outlier_cells:
        issues.append(
            f"{outlier_cells:,} numeric outliers detected by the 1.5×IQR rule."
        )
    if not issues:
        issues.append("No structural data-quality issues detected.")

    return {
        "score": round_number(overall, 2),
        "grade": grade,
        "components": components,
        "weights": QUALITY_WEIGHTS,
        "methodology": (
            "Weighted mean of completeness (40%), uniqueness (25%), validity (20%) "
            "and outlier health (15%). Each component is computed from the actual "
            "cell counts in this dataset version."
        ),
        "counts": {
            "rows": n_rows,
            "columns": n_cols,
            "cells": total_cells,
            "missing_cells": missing_cells,
            "duplicate_rows": duplicate_rows,
            "invalid_cells": invalid_cells,
            "numeric_cells": numeric_cells,
            "outlier_cells": outlier_cells,
        },
        "issues": issues,
    }


def profile_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    """Full profile document for a dataframe."""
    column_kinds = classify_all(df)
    column_profiles = [profile_column(df, c, column_kinds[c]) for c in df.columns]
    quality = compute_quality(df, column_kinds, column_profiles)

    numeric_columns = [c for c, k in column_kinds.items() if k == NUMERIC]
    categorical_columns = [c for c, k in column_kinds.items() if k == CATEGORICAL]
    datetime_columns = [c for c, k in column_kinds.items() if k == DATETIME]
    text_columns = [c for c, k in column_kinds.items() if k == TEXT]

    missing_by_column = sorted(
        (
            {"column": p["name"], "missing": p["missing"], "pct": p["missing_pct"]}
            for p in column_profiles
            if p["missing"] > 0
        ),
        key=lambda item: item["missing"],
        reverse=True,
    )

    return {
        "shape": {"rows": int(df.shape[0]), "columns": int(df.shape[1])},
        "column_kinds": column_kinds,
        "column_groups": {
            "numeric": numeric_columns,
            "categorical": categorical_columns,
            "datetime": datetime_columns,
            "text": text_columns,
        },
        "columns": column_profiles,
        "quality": quality,
        "duplicates": {
            "duplicate_rows": int(df.duplicated().sum()),
            "duplicate_pct": round_number(100 * df.duplicated().mean()) if len(df) else 0.0,
        },
        "missing_by_column": missing_by_column,
        "missing_total": int(df.isna().sum().sum()),
        "memory_bytes": int(df.memory_usage(deep=True).sum()),
    }


def preview_dataframe(df: pd.DataFrame, limit: int | None = None) -> dict[str, Any]:
    limit = limit or settings.PREVIEW_ROWS
    head = df.head(limit)
    rows = []
    for record in head.to_dict(orient="records"):
        rows.append({str(k): to_jsonable(v) for k, v in record.items()})
    return {
        "columns": [str(c) for c in head.columns],
        "rows": rows,
        "total_rows": int(len(df)),
        "returned_rows": len(rows),
        "truncated": len(df) > len(rows),
    }


def numeric_summary_table(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Rows for the descriptive-statistics table in the UI and reports."""
    kinds = classify_all(df)
    rows: list[dict[str, Any]] = []
    for column, kind in kinds.items():
        if kind != NUMERIC:
            continue
        stats = _describe_numeric(df[column])
        if not stats:
            continue
        rows.append({"column": column, **stats})
    return rows


def key_findings(profile: dict[str, Any]) -> list[str]:
    """Derive human-readable findings from the computed profile."""
    findings: list[str] = []
    shape = profile["shape"]
    findings.append(
        f"Dataset contains {shape['rows']:,} rows across {shape['columns']} columns."
    )
    quality = profile["quality"]
    findings.append(
        f"Overall data quality is {quality['score']}/100 (grade {quality['grade']})."
    )

    missing = profile["missing_by_column"]
    if missing:
        worst = missing[0]
        findings.append(
            f"Highest missing-value concentration: '{worst['column']}' "
            f"({worst['missing']:,} cells, {worst['pct']}%)."
        )
    else:
        findings.append("No missing values detected in any column.")

    dupes = profile["duplicates"]["duplicate_rows"]
    if dupes:
        findings.append(f"{dupes:,} fully duplicated rows were found.")

    numeric = [p for p in profile["columns"] if p["kind"] == NUMERIC and p.get("stats")]
    if numeric:
        most_skewed = max(
            numeric,
            key=lambda p: abs(p["stats"].get("skewness") or 0),
        )
        skew = most_skewed["stats"].get("skewness")
        if skew is not None:
            direction = "right" if skew > 0 else "left"
            findings.append(
                f"'{most_skewed['name']}' is the most skewed numeric column "
                f"(skewness {skew}, {direction}-tailed)."
            )
        with_outliers = [p for p in numeric if p["stats"]["outlier_count"] > 0]
        if with_outliers:
            top = max(with_outliers, key=lambda p: p["stats"]["outlier_count"])
            findings.append(
                f"'{top['name']}' has the most IQR outliers "
                f"({top['stats']['outlier_count']} values)."
            )

    categorical = [
        p for p in profile["columns"]
        if p["kind"] == CATEGORICAL and p.get("frequency")
    ]
    if categorical:
        widest = max(categorical, key=lambda p: p["unique"])
        top = widest["frequency"][0] if widest["frequency"] else None
        findings.append(
            f"'{widest['name']}' has {widest['unique']} distinct categories"
            + (f", most frequent: '{top['value']}' ({top['percentage']}%)." if top else ".")
        )

    return findings
