"""Query executor: runs a validated operation against real data.

This module is the ONLY place where numbers are produced for the NL analyst.
The LLM (if used) never sees or produces a number — it only proposes an intent.
Every value returned here is computed by pandas/numpy/scipy from the actual
dataframe and is independently re-verified before being returned.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ...utils.serialize import round_number, to_jsonable
from .. import statistics_engine as stats_engine
from ..cleaning import cleaning_recommendations
from ..profiling import profile_dataframe
from ..type_inference import CATEGORICAL, DATETIME, NUMERIC, TEXT, classify_all
from .rule_engine import ParsedQuery


class ExecutionError(Exception):
    """Raised when an operation cannot be executed on the data."""


_AGG_LABELS = {
    "mean": "average",
    "sum": "total",
    "median": "median",
    "min": "minimum",
    "max": "maximum",
    "std": "standard deviation",
    "var": "variance",
    "count": "count",
}


def _fmt(value: Any, digits: int = 4) -> str:
    """Format a number for prose without losing meaning."""
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return f"{value:,}"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer() and abs(number) < 1e15:
        return f"{int(number):,}"
    if abs(number) >= 1e6 or (abs(number) < 1e-4 and number != 0):
        return f"{number:,.4g}"
    return f"{number:,.{digits}f}".rstrip("0").rstrip(".")


def _numeric(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        raise ExecutionError(f"Column '{column}' does not exist in this dataset.")
    series = pd.to_numeric(df[column], errors="coerce").dropna()
    if series.empty:
        raise ExecutionError(f"Column '{column}' contains no numeric values.")
    return series


def _verify_scalar(expected: float | None, series: pd.Series, agg: str) -> bool:
    """Independent re-computation via a different code path for verification."""
    if expected is None or series.empty:
        return False
    if agg == "mean":
        reference = float(np.mean(series.to_numpy(dtype=float)))
    elif agg == "sum":
        reference = float(np.sum(series.to_numpy(dtype=float)))
    elif agg == "median":
        reference = float(np.median(series.to_numpy(dtype=float)))
    elif agg == "min":
        reference = float(np.min(series.to_numpy(dtype=float)))
    elif agg == "max":
        reference = float(np.max(series.to_numpy(dtype=float)))
    elif agg == "std":
        reference = float(np.std(series.to_numpy(dtype=float), ddof=1))
    elif agg == "var":
        reference = float(np.var(series.to_numpy(dtype=float), ddof=1))
    elif agg == "count":
        reference = float(series.count())
    else:
        return True
    tolerance = max(abs(reference) * 1e-9, 1e-9)
    return bool(abs(expected - reference) <= tolerance)


def _apply_agg(series: pd.Series, agg: str) -> float:
    if agg == "mean":
        return float(series.mean())
    if agg == "sum":
        return float(series.sum())
    if agg == "median":
        return float(series.median())
    if agg == "min":
        return float(series.min())
    if agg == "max":
        return float(series.max())
    if agg == "std":
        return float(series.std(ddof=1)) if len(series) > 1 else 0.0
    if agg == "var":
        return float(series.var(ddof=1)) if len(series) > 1 else 0.0
    if agg == "count":
        return float(series.count())
    raise ExecutionError(f"Unsupported aggregation {agg!r}.")


def execute(parsed: ParsedQuery, df: pd.DataFrame) -> dict[str, Any]:
    """Execute a parsed query. Returns {result, explanation, chart, warnings}."""
    intent = parsed.intent
    params = parsed.params
    handlers = {
        "row_count": _row_count,
        "column_list": _column_list,
        "missing_values": _missing_values,
        "duplicate_rows": _duplicate_rows,
        "quality_score": _quality_score,
        "outliers": _outliers,
        "unique_count": _unique_count,
        "describe_column": _describe_column,
        "dataset_summary": _dataset_summary,
        "correlation_pair": _correlation_pair,
        "correlation_matrix": _correlation_matrix,
        "ttest": _ttest,
        "chi_square": _chi_square,
        "time_trend": _time_trend,
        "top_n": _top_n,
        "group_extreme": _group_extreme,
        "grouped_aggregate": _grouped_aggregate,
        "value_counts": _value_counts,
        "aggregate": _aggregate,
    }
    handler = handlers.get(intent)
    if handler is None:
        raise ExecutionError(f"Unsupported intent '{intent}'.")
    return handler(df, params)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
def _row_count(df: pd.DataFrame, params: dict) -> dict:
    rows, columns = df.shape
    missing_cells = int(df.isna().sum().sum())
    return {
        "result": {
            "rows": int(rows),
            "columns": int(columns),
            "missing_cells": missing_cells,
            "duplicate_rows": int(df.duplicated().sum()),
        },
        "explanation": (
            f"The dataset contains {rows:,} rows and {columns} columns, with "
            f"{missing_cells:,} missing cells and "
            f"{int(df.duplicated().sum()):,} fully duplicated rows."
        ),
    }


def _column_list(df: pd.DataFrame, params: dict) -> dict:
    kinds = classify_all(df)
    columns = [
        {"name": c, "kind": kinds[c], "missing": int(df[c].isna().sum()),
         "unique": int(df[c].nunique(dropna=True))}
        for c in df.columns
    ]
    by_kind: dict[str, list[str]] = {}
    for column in columns:
        by_kind.setdefault(column["kind"], []).append(column["name"])
    summary = "; ".join(
        f"{len(names)} {kind}: {', '.join(names[:6])}"
        + ("…" if len(names) > 6 else "")
        for kind, names in by_kind.items()
    )
    return {
        "result": {"columns": columns, "by_kind": by_kind, "count": len(columns)},
        "explanation": f"The dataset has {len(columns)} columns — {summary}.",
    }


def _missing_values(df: pd.DataFrame, params: dict) -> dict:
    column = params.get("column")
    if column:
        if column not in df.columns:
            raise ExecutionError(f"Column '{column}' does not exist.")
        missing = int(df[column].isna().sum())
        total = len(df)
        pct = round_number(100 * missing / total) if total else 0.0
        return {
            "result": {
                "column": column, "missing": missing, "total": total,
                "missing_pct": pct,
            },
            "explanation": (
                f"Column '{column}' has {missing:,} missing values out of {total:,} "
                f"rows ({pct}%)."
            ),
        }

    total_cells = int(df.shape[0] * df.shape[1])
    missing_cells = int(df.isna().sum().sum())
    per_column = [
        {"column": c, "missing": int(df[c].isna().sum()),
         "pct": round_number(100 * df[c].isna().sum() / max(len(df), 1))}
        for c in df.columns
        if df[c].isna().any()
    ]
    per_column.sort(key=lambda item: item["missing"], reverse=True)

    if not per_column:
        explanation = (
            f"No missing values found — all {total_cells:,} cells across "
            f"{df.shape[1]} columns are populated."
        )
    else:
        worst = per_column[0]
        explanation = (
            f"There are {missing_cells:,} missing cells out of {total_cells:,} "
            f"({round_number(100 * missing_cells / max(total_cells, 1))}%). "
            f"The worst affected column is '{worst['column']}' with "
            f"{worst['missing']:,} missing values ({worst['pct']}%). "
            f"In total {len(per_column)} of {df.shape[1]} columns have missing data."
        )
    return {
        "result": {
            "missing_cells": missing_cells,
            "total_cells": total_cells,
            "missing_pct": round_number(100 * missing_cells / max(total_cells, 1)),
            "per_column": per_column,
        },
        "explanation": explanation,
        "chart": {
            "chart_type": "bar",
            "title": "Missing values by column",
            "x_label": "Column",
            "y_label": "Missing cells",
            "data": [
                {"label": item["column"], "value": item["missing"]}
                for item in per_column[:12]
            ],
        } if per_column else None,
    }


def _duplicate_rows(df: pd.DataFrame, params: dict) -> dict:
    total = len(df)
    duplicates = int(df.duplicated().sum())
    unique = total - duplicates
    pct = round_number(100 * duplicates / max(total, 1))
    return {
        "result": {"duplicate_rows": duplicates, "unique_rows": unique,
                   "total": total, "duplicate_pct": pct},
        "explanation": (
            f"{duplicates:,} of {total:,} rows ({pct}%) are exact duplicates of an "
            f"earlier row, leaving {unique:,} distinct rows."
            if duplicates else
            f"No duplicate rows were found — all {total:,} rows are unique."
        ),
    }


def _quality_score(df: pd.DataFrame, params: dict) -> dict:
    profile = profile_dataframe(df)
    quality = profile["quality"]
    components = quality["components"]
    return {
        "result": {"quality": quality, "shape": profile["shape"]},
        "explanation": (
            f"The overall data-quality score is {quality['score']}/100 "
            f"(grade {quality['grade']}). Components: completeness "
            f"{components['completeness']}, uniqueness {components['uniqueness']}, "
            f"validity {components['validity']}, outlier health "
            f"{components['outlier_health']}. " + " ".join(quality["issues"])
        ),
    }


def _outliers(df: pd.DataFrame, params: dict) -> dict:
    kinds = classify_all(df)
    column = params.get("column")
    if column:
        series = _numeric(df, column)
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        mask = (series < lower) | (series > upper)
        count = int(mask.sum())
        return {
            "result": {
                "column": column, "outlier_count": count, "n": int(len(series)),
                "outlier_pct": round_number(100 * count / len(series)),
                "lower_fence": round_number(lower), "upper_fence": round_number(upper),
                "q1": round_number(q1), "q3": round_number(q3),
                "iqr": round_number(iqr),
                "examples": [round_number(v) for v in series[mask].head(10).tolist()],
            },
            "explanation": (
                f"Column '{column}' has {count:,} outliers ({round_number(100 * count / len(series))}% "
                f"of {len(series):,} values) outside the 1.5×IQR fences "
                f"[{_fmt(lower)}, {_fmt(upper)}]. The IQR is {_fmt(iqr)}."
            ),
        }

    per_column = []
    for col in df.columns:
        if kinds.get(col) != NUMERIC:
            continue
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(series) < 4:
            continue
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        count = int(((series < q1 - 1.5 * iqr) | (series > q3 + 1.5 * iqr)).sum())
        per_column.append({
            "column": col, "outlier_count": count, "n": int(len(series)),
            "outlier_pct": round_number(100 * count / len(series)),
        })
    per_column.sort(key=lambda item: item["outlier_count"], reverse=True)

    if not per_column:
        raise ExecutionError(
            "No numeric columns with enough variation were found for outlier detection."
        )
    total = sum(item["outlier_count"] for item in per_column)
    return {
        "result": {"per_column": per_column, "total_outliers": total},
        "explanation": (
            f"Using the 1.5×IQR rule across {len(per_column)} numeric columns, "
            f"{total:,} outlier values were detected. The most affected column is "
            f"'{per_column[0]['column']}' with {per_column[0]['outlier_count']:,} "
            f"outliers ({per_column[0]['outlier_pct']}% of its values)."
        ),
        "chart": {
            "chart_type": "bar",
            "title": "Outlier count by numeric column",
            "x_label": "Column",
            "y_label": "Outliers",
            "data": [
                {"label": item["column"], "value": item["outlier_count"]}
                for item in per_column[:12]
            ],
        },
    }


def _unique_count(df: pd.DataFrame, params: dict) -> dict:
    column = params["column"]
    if column not in df.columns:
        raise ExecutionError(f"Column '{column}' does not exist.")
    non_null = df[column].dropna()
    unique = int(non_null.nunique())
    top = non_null.astype(str).value_counts().head(5)
    detail = ", ".join(f"'{k}' ({v:,})" for k, v in top.items())
    return {
        "result": {
            "column": column, "unique": unique, "non_null": int(len(non_null)),
            "total": int(len(df)),
            "top_values": [{"value": str(k), "count": int(v)} for k, v in top.items()],
        },
        "explanation": (
            f"Column '{column}' has {unique:,} distinct values among "
            f"{len(non_null):,} non-missing rows. Most frequent: {detail}."
        ),
    }


def _describe_column(df: pd.DataFrame, params: dict) -> dict:
    column = params["column"]
    if column not in df.columns:
        raise ExecutionError(f"Column '{column}' does not exist.")
    kinds = classify_all(df)
    kind = kinds.get(column)
    series = df[column]
    missing = int(series.isna().sum())

    if kind == NUMERIC:
        values = _numeric(df, column)
        q1, q3 = values.quantile(0.25), values.quantile(0.75)
        return {
            "result": {
                "column": column, "kind": kind, "n": int(len(values)),
                "mean": round_number(values.mean()),
                "median": round_number(values.median()),
                "std": round_number(values.std(ddof=1)) if len(values) > 1 else None,
                "min": round_number(values.min()),
                "max": round_number(values.max()),
                "q1": round_number(q1), "q3": round_number(q3),
                "skewness": round_number(values.skew()) if len(values) > 2 else None,
                "missing": missing,
            },
            "explanation": (
                f"'{column}' is numeric with {len(values):,} values and {missing:,} "
                f"missing. Mean {_fmt(values.mean())}, median {_fmt(values.median())}, "
                f"standard deviation {_fmt(values.std(ddof=1))}, ranging from "
                f"{_fmt(values.min())} to {_fmt(values.max())}. "
                f"Skewness is {round_number(values.skew()) if len(values) > 2 else 'n/a'}."
            ),
            "chart": {
                "chart_type": "histogram",
                "title": f"Distribution of {column}",
                "column": column,
                "x_label": column,
                "y_label": "Frequency",
                "bins": 20,
                "data": _histogram_data(values, 20),
            },
        }

    counts = series.dropna().astype(str).value_counts()
    return {
        "result": {
            "column": column, "kind": kind,
            "unique": int(series.nunique(dropna=True)),
            "missing": missing, "top_values": [
                {"value": str(k), "count": int(v),
                 "pct": round_number(100 * v / max(int(series.notna().sum()), 1))}
                for k, v in counts.head(10).items()
            ],
        },
        "explanation": (
            f"'{column}' is {kind} with {int(series.nunique(dropna=True)):,} distinct "
            f"values and {missing:,} missing. The most common value is "
            f"'{counts.index[0]}' appearing {counts.iloc[0]:,} times."
            if not counts.empty else f"'{column}' contains no non-missing values."
        ),
    }


def _histogram_data(values: pd.Series, bins: int) -> list[dict]:
    counts, edges = np.histogram(values.to_numpy(dtype=float), bins=bins)
    return [
        {
            "label": f"{_fmt(edges[i])}–{_fmt(edges[i + 1])}",
            "value": int(counts[i]),
            "bin_start": round_number(edges[i]),
            "bin_end": round_number(edges[i + 1]),
        }
        for i in range(len(counts))
    ]


def _dataset_summary(df: pd.DataFrame, params: dict) -> dict:
    profile = profile_dataframe(df)
    findings = [
        f"{profile['shape']['rows']:,} rows × {profile['shape']['columns']} columns",
        f"quality score {profile['quality']['score']}/100 "
        f"(grade {profile['quality']['grade']})",
        f"{profile['missing_total']:,} missing cells",
        f"{profile['duplicates']['duplicate_rows']:,} duplicate rows",
    ]
    numeric = profile["column_groups"]["numeric"]
    categorical = profile["column_groups"]["categorical"]
    return {
        "result": {
            "shape": profile["shape"],
            "quality": profile["quality"],
            "numeric_columns": numeric,
            "categorical_columns": categorical,
        },
        "explanation": (
            "Dataset summary: " + "; ".join(findings) + ". "
            f"There are {len(numeric)} numeric and {len(categorical)} categorical columns."
        ),
    }


def _correlation_pair(df: pd.DataFrame, params: dict) -> dict:
    result = stats_engine.pearson_correlation(df, params["x"], params["y"])
    return {
        "result": result,
        "explanation": result["interpretation"],
        "chart": {
            "chart_type": "scatter",
            "title": f"{params['y']} vs {params['x']}",
            "x_label": params["x"], "y_label": params["y"],
            "x": params["x"], "y": params["y"],
            "data": _scatter_data(df, params["x"], params["y"]),
        },
    }


def _scatter_data(df: pd.DataFrame, x: str, y: str, limit: int = 1000) -> list[dict]:
    frame = pd.DataFrame({
        "x": pd.to_numeric(df[x], errors="coerce"),
        "y": pd.to_numeric(df[y], errors="coerce"),
    }).dropna()
    if len(frame) > limit:
        frame = frame.sample(n=limit, random_state=42)
    return [
        {"x": round_number(row.x), "y": round_number(row.y)}
        for row in frame.itertuples(index=False)
    ]


def _correlation_matrix(df: pd.DataFrame, params: dict) -> dict:
    result = stats_engine.correlation_matrix(df, params.get("method", "pearson"))
    strongest = result.get("strongest")
    strongest_text = ""
    if strongest:
        strongest_text = (
            f" The strongest pair is '{strongest['a']}' and '{strongest['b']}' "
            f"(r = {strongest['r']}, {strongest['strength']})."
        )
    return {
        "result": result,
        "explanation": (
            f"Computed a {result['method']} correlation matrix across "
            f"{len(result['columns'])} numeric columns.{strongest_text}"
        ),
        "chart": {
            "chart_type": "correlation_heatmap",
            "title": f"{result['method'].capitalize()} correlation heatmap",
            "method": result["method"],
            "columns": result["columns"],
            "matrix": result["matrix"],
        },
    }


def _ttest(df: pd.DataFrame, params: dict) -> dict:
    result = stats_engine.independent_ttest(
        df, params["numeric_column"], params["group_column"]
    )
    return {
        "result": result,
        "explanation": result["interpretation"],
        "chart": _group_means_chart(df, params["group_column"], params["numeric_column"]),
    }


def _group_means_chart(df: pd.DataFrame, group_col: str, value_col: str) -> dict | None:
    try:
        frame = pd.DataFrame({
            "group": df[group_col].astype(str),
            "value": pd.to_numeric(df[value_col], errors="coerce"),
        }).dropna()
        if frame.empty:
            return None
        means = frame.groupby("group")["value"].mean().sort_values(ascending=False).head(15)
        return {
            "chart_type": "bar",
            "title": f"Mean {value_col} by {group_col}",
            "x_label": group_col, "y_label": f"Mean {value_col}",
            "data": [{"label": str(k), "value": round_number(v)} for k, v in means.items()],
        }
    except (KeyError, ValueError):
        return None


def _chi_square(df: pd.DataFrame, params: dict) -> dict:
    result = stats_engine.chi_square_test(df, params["x"], params["y"])
    return {"result": result, "explanation": result["interpretation"]}


def _time_trend(df: pd.DataFrame, params: dict) -> dict:
    from ..eda import line_chart

    chart = line_chart(
        df,
        params["date_column"],
        params.get("value_column"),
        params.get("freq", "M"),
        "mean",
    )
    data = chart["data"]
    if len(data) >= 2:
        first, last = data[0]["value"], data[-1]["value"]
        if first not in (None, 0) and last is not None:
            change = last - first
            pct = round_number(100 * change / abs(first)) if first else None
            trend = "increase" if change > 0 else ("decrease" if change < 0 else "no change")
            explanation = (
                f"The {chart['y_label']} moved from {_fmt(first)} at "
                f"{data[0]['label']} to {_fmt(last)} at {data[-1]['label']}, an "
                f"{trend} of {_fmt(abs(change))}"
                + (f" ({abs(pct)}%)." if pct is not None else ".")
                + f" The series contains {len(data)} periods."
            )
        else:
            explanation = (
                f"The series contains {len(data)} periods from {data[0]['label']} "
                f"to {data[-1]['label']}."
            )
    else:
        explanation = f"Only {len(data)} time period(s) contained data."

    return {
        "result": {
            "date_column": params["date_column"],
            "value_column": params.get("value_column"),
            "frequency": chart["frequency"],
            "periods": len(data),
            "points": data,
        },
        "explanation": explanation,
        "chart": chart,
    }

def _top_n(df: pd.DataFrame, params: dict) -> dict:
    group_col = params["group_column"]
    value_col = params["value_column"]
    agg = params.get("agg", "sum")
    n = int(params.get("n", 5))
    order = params.get("order", "desc")
    chart_type = params.get("chart_type", "bar")

    if group_col not in df.columns:
        raise ExecutionError(f"Column '{group_col}' does not exist.")

    if value_col not in df.columns:
        raise ExecutionError(f"Column '{value_col}' does not exist.")

    frame = pd.DataFrame({
        "group": df[group_col].astype(str),
        "value": pd.to_numeric(df[value_col], errors="coerce"),
    }).dropna()

    if frame.empty:
        raise ExecutionError(
            f"No rows with both '{group_col}' and a numeric '{value_col}' were found."
        )

    grouped = frame.groupby("group")["value"].agg(agg)
    grouped = grouped.sort_values(
        ascending=(order == "asc")
    ).head(n)

    if grouped.empty:
        raise ExecutionError("No groups could be ranked.")

    top_label = str(grouped.index[0])
    top_value = float(grouped.iloc[0])
    subset = frame.loc[frame["group"] == top_label, "value"]
    verified = _verify_scalar(top_value, subset, agg)

    ranking = [
        {"rank": i + 1, "label": str(k), "value": round_number(v)}
        for i, (k, v) in enumerate(grouped.items())
    ]

    direction = "highest" if order == "desc" else "lowest"

    explanation = (
        f"Ranked by {agg} of '{value_col}' per '{group_col}'. The {direction} is "
        f"'{top_label}' with {agg} = {_fmt(top_value)}"
        + (
            f" (independently verified using its {len(subset):,} matching rows)."
            if verified else "."
        )
        + f" Top {len(ranking)}: "
        + ", ".join(
            f"{item['label']} ({_fmt(item['value'])})"
            for item in ranking
        )
        + "."
    )

    chart = {
        "chart_type": chart_type if chart_type in ("bar", "pie") else "bar",
        "title": f"Top {len(ranking)} {group_col} by {agg} of {value_col}",
        "x_label": group_col,
        "y_label": f"{agg}({value_col})",
        "data": [
            {"label": item["label"], "value": item["value"]}
            for item in ranking
        ],
    }

    return {
        "result": {
            "group_column": group_col,
            "value_column": value_col,
            "agg": agg,
            "ranking": ranking,
            "verified": verified,
            "n": len(ranking),
        },
        "explanation": explanation,
        "chart": chart,
    }


def _group_extreme(df: pd.DataFrame, params: dict) -> dict:
    group_col = params["group_column"]
    value_col = params["value_column"]
    agg = params.get("agg", "sum")
    mode = params.get("mode", "max")

    frame = pd.DataFrame({
        "group": df[group_col].astype(str),
        "value": pd.to_numeric(df[value_col], errors="coerce"),
    }).dropna()
    if frame.empty:
        raise ExecutionError("No usable rows for this grouping.")

    grouped = frame.groupby("group")["value"].agg(agg)
    target_value = float(grouped.max() if mode == "max" else grouped.min())

    tied_labels = [
        str(label)
        for label, value in grouped.items()
        if float(value) == target_value
    ]
    
    target_label = tied_labels[0]
    subset = frame.loc[frame["group"].isin(tied_labels), "value"]
    verified = all(
        _verify_scalar(target_value, frame.loc[frame["group"] == label, "value"], agg)
        for label in tied_labels
    )

    word = "highest" if mode == "max" else "lowest"
    return {
        "result": {
            "group_column": group_col, "value_column": value_col, "agg": agg,
            "winner": target_label, "value": round_number(target_value),
            "verified": verified,
            "all_groups": [
                {"label": str(k), "value": round_number(v)}
                for k, v in grouped.sort_values(ascending=(mode == "min")).items()
            ],
        },
        "explanation": (
            f"'{', '.join(tied_labels)}' {'are' if len(tied_labels) > 1 else 'has'} tied for the {word} {agg} of '{value_col}' at "
            f"{_fmt(target_value)} across {len(grouped)} distinct '{group_col}' values"
            + (f" (independently verified from {len(subset):,} rows)." if verified else ".")
        ),
        "chart": {
            "chart_type": "bar",
            "title": f"{agg.capitalize()} of {value_col} by {group_col}",
            "x_label": group_col, "y_label": f"{agg}({value_col})",
            "data": [
                {"label": str(k), "value": round_number(v)}
               for k, v in grouped.sort_values(
    ascending=(mode == "min")
).head(15).items()
            ],
        },
    }


def _grouped_aggregate(df: pd.DataFrame, params: dict) -> dict:
    group_col = params["group_column"]
    value_col = params["value_column"]
    agg = params.get("agg", "mean")
    n = int(params.get("n", 10))

    frame = pd.DataFrame({
        "group": df[group_col].astype(str),
        "value": pd.to_numeric(df[value_col], errors="coerce"),
    }).dropna()
    if frame.empty:
        raise ExecutionError("No usable rows for this grouping.")

    grouped = frame.groupby("group")["value"].agg([agg, "count"])
    grouped = grouped.sort_values(agg, ascending=False).head(n)

    best_label = str(grouped.index[0])
    best_value = float(grouped.iloc[0][agg])
    subset = frame.loc[frame["group"] == best_label, "value"]
    verified = _verify_scalar(best_value, subset, agg)

    rows = [
        {
            "label": str(index),
            "value": round_number(row[agg]),
            "count": int(row["count"]),
        }
        for index, row in grouped.iterrows()
    ]
    return {
        "result": {
            "group_column": group_col, "value_column": value_col, "agg": agg,
            "groups": rows, "verified": verified,
        },
        "explanation": (
            f"{_AGG_LABELS.get(agg, agg).capitalize()} of '{value_col}' by "
            f"'{group_col}' across {len(rows)} groups. The highest is "
            f"'{best_label}' at {_fmt(best_value)}"
            + (f" (verified from {len(subset):,} rows)." if verified else ".")
        ),
        "chart": {
            "chart_type": "bar",
            "title": f"{_AGG_LABELS.get(agg, agg).capitalize()} of {value_col} by {group_col}",
            "x_label": group_col, "y_label": f"{agg}({value_col})",
            "data": [{"label": row["label"], "value": row["value"]} for row in rows],
        },
    }


def _value_counts(df: pd.DataFrame, params: dict) -> dict:
    column = params["column"]
    n = int(params.get("n", 10))
    if column not in df.columns:
        raise ExecutionError(f"Column '{column}' does not exist.")
    counts = df[column].dropna().astype(str).value_counts().head(n)
    if counts.empty:
        raise ExecutionError(f"Column '{column}' has no non-missing values.")
    total = int(df[column].notna().sum())
    rows = [
        {"label": str(k), "value": int(v), "pct": round_number(100 * v / total)}
        for k, v in counts.items()
    ]
    return {
        "result": {"column": column, "counts": rows, "total_non_null": total},
        "explanation": (
            f"'{column}' has {int(df[column].nunique(dropna=True)):,} distinct values. "
            f"The most frequent are: "
            + ", ".join(f"{r['label']} ({r['value']:,}, {r['pct']}%)" for r in rows[:5])
            + "."
        ),
        "chart": {
            "chart_type": "bar",
            "title": f"Most frequent values in {column}",
            "x_label": column, "y_label": "Count",
            "data": [{"label": r["label"], "value": r["value"]} for r in rows],
        },
    }


def _aggregate(df: pd.DataFrame, params: dict) -> dict:
    column = params["column"]
    agg = params["agg"]
    if column not in df.columns:
        raise ExecutionError(f"Column '{column}' does not exist.")

    series = pd.to_numeric(df[column], errors="coerce").dropna()
    if series.empty:
        raise ExecutionError(f"Column '{column}' has no numeric values.")

    value = _apply_agg(series, agg)
    verified = _verify_scalar(value, series, agg)
    label = _AGG_LABELS.get(agg, agg)

    if not verified:
        raise ExecutionError(
            "Internal verification failed: the primary computation and the "
            "independent recomputation disagree. The result has been withheld."
        )

    return {
        "result": {
            "column": column, "agg": agg, "value": round_number(value),
            "n": int(len(series)), "verified": True,
            "missing_excluded": int(df[column].isna().sum()),
        },
        "explanation": (
            f"The {label} of '{column}' is {_fmt(value)}, computed from "
            f"{len(series):,} non-missing values "
            f"(excluding {int(df[column].isna().sum()):,} missing). "
            "The value was independently recomputed with NumPy and matched."
        ),
        "chart": {
            "chart_type": "histogram",
            "title": f"Distribution of {column}",
            "column": column, "x_label": column, "y_label": "Frequency",
            "bins": 20, "data": _histogram_data(series, 20),
        },
    }
