"""Exploratory data analysis / chart data generation.

The backend never sends a pre-rendered picture for the interactive views — it
sends the *actual aggregated numbers* computed by pandas so the frontend charts
are always driven by the real dataset. Matplotlib is only used for static images
embedded into PDF reports.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..config import settings
from ..utils.serialize import round_number, to_jsonable
from .type_inference import CATEGORICAL, DATETIME, NUMERIC, TEXT, classify_all


class ChartError(Exception):
    """Raised when a chart request cannot be satisfied by the data."""


def _require_column(df: pd.DataFrame, column: str | None, role: str) -> str:
    if not column:
        raise ChartError(f"A column is required for the {role} axis.")
    if column not in df.columns:
        raise ChartError(f"Column '{column}' does not exist in this dataset.")
    return column


def _numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    series = pd.to_numeric(df[column], errors="coerce")
    if series.notna().sum() == 0:
        raise ChartError(f"Column '{column}' contains no numeric values.")
    return series


_AGG_FUNCS = {
    "mean": "mean",
    "sum": "sum",
    "count": "count",
    "median": "median",
    "min": "min",
    "max": "max",
}


def histogram(df: pd.DataFrame, column: str, bins: int = 20) -> dict[str, Any]:
    column = _require_column(df, column, "x")
    values = _numeric_series(df, column).dropna()
    if values.empty:
        raise ChartError(f"Column '{column}' has no values to bin.")

    bins = max(5, min(int(bins), 100))
    counts, edges = np.histogram(values.to_numpy(), bins=bins)
    labels = [
        f"{round_number(edges[i], 3)}–{round_number(edges[i + 1], 3)}"
        for i in range(len(edges) - 1)
    ]
    return to_jsonable({
        "chart_type": "histogram",
        "title": f"Distribution of {column}",
        "x_label": column,
        "y_label": "Frequency",
        "column": column,
        "bins": bins,
        "data": [
            {"label": labels[i], "value": int(counts[i]),
             "bin_start": round_number(edges[i], 4),
             "bin_end": round_number(edges[i + 1], 4)}
            for i in range(len(counts))
        ],
        "stats": {
            "n": int(values.count()),
            "mean": round_number(values.mean()),
            "median": round_number(values.median()),
            "std": round_number(values.std(ddof=1)) if len(values) > 1 else None,
            "min": round_number(values.min()),
            "max": round_number(values.max()),
        },
    })


def bar_chart(df: pd.DataFrame, column: str, top_n: int = 10,
              value_column: str | None = None, agg: str = "count") -> dict[str, Any]:
    column = _require_column(df, column, "x")
    top_n = max(1, min(int(top_n), settings.MAX_CHART_CATEGORIES))

    if value_column:
        value_column = _require_column(df, value_column, "y")
        frame = df[[column, value_column]].copy()
        frame[value_column] = pd.to_numeric(frame[value_column], errors="coerce")
        frame = frame.dropna()
        grouped = (
            frame.groupby(frame[column].astype(str))[value_column]
            .agg(_AGG_FUNCS.get(agg, "sum"))
            .sort_values(ascending=False)
            .head(top_n)
        )
        y_label = f"{agg}({value_column})"
        agg_note = f"{agg} of '{value_column}' by '{column}'"
    else:
        grouped = (
            df[column].dropna().astype(str).value_counts().head(top_n)
        )
        y_label = "Count"
        agg_note = f"row count by '{column}'"

    if grouped.empty:
        raise ChartError(f"Column '{column}' has no values to chart.")

    return to_jsonable({
        "chart_type": "bar",
        "title": f"{agg_note.capitalize()} (top {len(grouped)})",
        "x_label": column,
        "y_label": y_label,
        "column": column,
        "value_column": value_column,
        "agg": agg,
        "data": [
            {"label": str(index), "value": round_number(value)}
            for index, value in grouped.items()
        ],
    })


def pie_chart(df: pd.DataFrame, column: str, top_n: int = 8) -> dict[str, Any]:
    column = _require_column(df, column, "x")
    top_n = max(2, min(int(top_n), 20))
    counts = df[column].dropna().astype(str).value_counts()
    if counts.empty:
        raise ChartError(f"Column '{column}' has no values to chart.")

    if len(counts) > top_n:
        head = counts.head(top_n - 1)
        other_total = int(counts.iloc[top_n - 1:].sum())
        data = [{"label": str(k), "value": int(v)} for k, v in head.items()]
        data.append({"label": "Other", "value": other_total})
    else:
        data = [{"label": str(k), "value": int(v)} for k, v in counts.items()]

    total = sum(item["value"] for item in data)
    for item in data:
        item["percentage"] = round_number(100 * item["value"] / total) if total else 0.0

    return to_jsonable({
        "chart_type": "pie",
        "title": f"Composition of {column}",
        "column": column,
        "data": data,
        "total": total,
    })


def scatter_plot(df: pd.DataFrame, x: str, y: str,
                 max_points: int | None = None) -> dict[str, Any]:
    x = _require_column(df, x, "x")
    y = _require_column(df, y, "y")
    max_points = max_points or settings.MAX_SCATTER_POINTS

    frame = pd.DataFrame({
        "x": pd.to_numeric(df[x], errors="coerce"),
        "y": pd.to_numeric(df[y], errors="coerce"),
    }).dropna()
    if frame.empty:
        raise ChartError(f"'{x}' and '{y}' share no complete numeric rows.")

    total = len(frame)
    sampled = total > max_points
    if sampled:
        frame = frame.sample(n=max_points, random_state=42).sort_index()

    corr = float(frame["x"].corr(frame["y"])) if len(frame) > 1 else None

    return to_jsonable({
        "chart_type": "scatter",
        "title": f"{y} vs {x}",
        "x_label": x,
        "y_label": y,
        "x": x,
        "y": y,
        "total_points": total,
        "sampled": sampled,
        "pearson_r": round_number(corr, 4),
        "data": [
            {"x": round_number(row.x), "y": round_number(row.y)}
            for row in frame.itertuples(index=False)
        ],
    })


def box_plot(df: pd.DataFrame, column: str, group_by: str | None = None) -> dict[str, Any]:
    column = _require_column(df, column, "x")
    values = pd.to_numeric(df[column], errors="coerce")

    def _summarise(series: pd.Series) -> dict[str, Any] | None:
        clean = series.dropna()
        if clean.empty:
            return None
        q1, q3 = clean.quantile(0.25), clean.quantile(0.75)
        iqr = q3 - q1
        return {
            "min": round_number(clean.min()),
            "q1": round_number(q1),
            "median": round_number(clean.median()),
            "q3": round_number(q3),
            "max": round_number(clean.max()),
            "lower_fence": round_number(q1 - 1.5 * iqr),
            "upper_fence": round_number(q3 + 1.5 * iqr),
            "n": int(clean.count()),
        }

    if group_by:
        group_by = _require_column(df, group_by, "group")
        frame = pd.DataFrame({"value": values, "group": df[group_by].astype(str)}).dropna()
        series_list = []
        for name, chunk in frame.groupby("group"):
            summary = _summarise(chunk["value"])
            if summary:
                series_list.append({"label": str(name), **summary})
        series_list.sort(key=lambda item: item["median"] or 0, reverse=True)
        series_list = series_list[:settings.MAX_CHART_CATEGORIES]
    else:
        summary = _summarise(values)
        if not summary:
            raise ChartError(f"Column '{column}' has no numeric values.")
        series_list = [{"label": column, **summary}]

    if not series_list:
        raise ChartError("No groups with numeric data were found.")

    return to_jsonable({
        "chart_type": "box",
        "title": f"Box plot of {column}" + (f" by {group_by}" if group_by else ""),
        "column": column,
        "group_by": group_by,
        "series": series_list,
        "note": (
            "Whiskers are drawn at 1.5×IQR fences; values beyond them are outliers."
        ),
    })


def line_chart(df: pd.DataFrame, date_column: str, value_column: str | None = None,
               freq: str = "M", agg: str = "mean") -> dict[str, Any]:
    date_column = _require_column(df, date_column, "x")
    parsed = pd.to_datetime(df[date_column], errors="coerce", format="mixed")
    if parsed.notna().sum() == 0:
        raise ChartError(f"Column '{date_column}' contains no parseable dates.")

    frame = pd.DataFrame({"date": parsed})
    if value_column:
        value_column = _require_column(df, value_column, "y")
        frame["value"] = pd.to_numeric(df[value_column], errors="coerce")
        frame = frame.dropna()
        aggregated = (
            frame.set_index("date")["value"]
            .resample(freq)
            .agg(_AGG_FUNCS.get(agg, "mean"))
            .dropna()
        )
        y_label = f"{agg}({value_column})"
    else:
        frame = frame.dropna()
        aggregated = frame.set_index("date").resample(freq).size()
        y_label = "Row count"

    if aggregated.empty:
        raise ChartError("No data points remain after time aggregation.")

    return to_jsonable({
        "chart_type": "line",
        "title": f"{y_label} over time ({date_column})",
        "x_label": date_column,
        "y_label": y_label,
        "date_column": date_column,
        "value_column": value_column,
        "frequency": freq,
        "data": [
            {"label": index.strftime("%Y-%m-%d"), "value": round_number(value)}
            for index, value in aggregated.items()
        ],
    })


def correlation_heatmap(df: pd.DataFrame, method: str = "pearson") -> dict[str, Any]:
    kinds = classify_all(df)
    numeric_columns = [c for c, k in kinds.items() if k == NUMERIC]
    if len(numeric_columns) < 2:
        raise ChartError(
            f"A correlation heatmap needs at least 2 numeric columns; found {len(numeric_columns)}."
        )

    numeric_df = df[numeric_columns].apply(pd.to_numeric, errors="coerce")
    corr = numeric_df.corr(method=method).round(4).fillna(0.0)

    cells = []
    for row_name in corr.index:
        for col_name in corr.columns:
            cells.append({
                "row": str(row_name),
                "col": str(col_name),
                "value": round_number(corr.loc[row_name, col_name], 4),
            })

    return to_jsonable({
        "chart_type": "correlation_heatmap",
        "title": f"{method.capitalize()} correlation heatmap",
        "method": method,
        "columns": numeric_columns,
        "matrix": corr.to_dict(orient="index"),
        "cells": cells,
        "note": "Values range from -1 (perfect negative) to +1 (perfect positive).",
    })


def grouped_aggregate(df: pd.DataFrame, group_by: str, value_column: str,
                      agg: str = "mean", top_n: int = 15) -> dict[str, Any]:
    group_by = _require_column(df, group_by, "group")
    value_column = _require_column(df, value_column, "y")
    top_n = max(1, min(int(top_n), settings.MAX_CHART_CATEGORIES))

    frame = pd.DataFrame({
        "group": df[group_by].astype(str),
        "value": pd.to_numeric(df[value_column], errors="coerce"),
    }).dropna()
    if frame.empty:
        raise ChartError("No numeric data available for the requested grouping.")

    func = _AGG_FUNCS.get(agg, "mean")
    grouped = frame.groupby("group")["value"].agg([func, "count"])
    grouped = grouped.sort_values(func, ascending=False).head(top_n)

    return to_jsonable({
        "chart_type": "grouped_aggregate",
        "title": f"{agg} of {value_column} by {group_by}",
        "group_by": group_by,
        "value_column": value_column,
        "agg": agg,
        "data": [
            {
                "label": str(index),
                "value": round_number(row[func]),
                "count": int(row["count"]),
            }
            for index, row in grouped.iterrows()
        ],
    })


def suggest_charts(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Recommend charts that are actually possible for this dataframe."""
    kinds = classify_all(df)
    suggestions: list[dict[str, Any]] = []
    numeric = [c for c, k in kinds.items() if k == NUMERIC]
    categorical = [c for c, k in kinds.items() if k in (CATEGORICAL, TEXT)]
    datetimes = [c for c, k in kinds.items() if k == DATETIME]

    for column in numeric[:4]:
        suggestions.append({
            "chart_type": "histogram", "x": column,
            "reason": f"Distribution of numeric column '{column}'.",
        })
    for column in categorical[:3]:
        suggestions.append({
            "chart_type": "bar", "x": column,
            "reason": f"Frequency of categories in '{column}'.",
        })
        suggestions.append({
            "chart_type": "pie", "x": column,
            "reason": f"Proportional composition of '{column}'.",
        })
    if len(numeric) >= 2:
        suggestions.append({
            "chart_type": "scatter", "x": numeric[0], "y": numeric[1],
            "reason": f"Relationship between '{numeric[0]}' and '{numeric[1]}'.",
        })
        suggestions.append({
            "chart_type": "correlation_heatmap",
            "reason": "Correlation structure across all numeric columns.",
        })
        suggestions.append({
            "chart_type": "box", "x": numeric[0],
            "reason": f"Spread and outliers in '{numeric[0]}'.",
        })
    if datetimes and numeric:
        suggestions.append({
            "chart_type": "line", "x": datetimes[0], "y": numeric[0],
            "reason": f"Trend of '{numeric[0]}' over '{datetimes[0]}'.",
        })
    if categorical and numeric:
        suggestions.append({
            "chart_type": "grouped_aggregate", "group_by": categorical[0],
            "y": numeric[0],
            "reason": f"Compare mean '{numeric[0]}' across '{categorical[0]}' groups.",
        })
    return to_jsonable(suggestions)


def build_chart(df: pd.DataFrame, chart_type: str, **kwargs) -> dict[str, Any]:
    """Dispatch a chart request to the correct builder."""
    version_note = kwargs.pop("version_id", None)
    del version_note

    if chart_type == "histogram":
        return histogram(df, kwargs.get("x"), kwargs.get("bins", 20))
    if chart_type == "bar":
        return bar_chart(
            df, kwargs.get("x"), kwargs.get("top_n", 10),
            kwargs.get("y"), kwargs.get("agg", "count"),
        )
    if chart_type == "pie":
        return pie_chart(df, kwargs.get("x"), kwargs.get("top_n", 8))
    if chart_type == "scatter":
        return scatter_plot(df, kwargs.get("x"), kwargs.get("y"))
    if chart_type == "box":
        return box_plot(df, kwargs.get("x"), kwargs.get("group_by"))
    if chart_type == "correlation_heatmap":
        return correlation_heatmap(df, kwargs.get("method", "pearson"))
    if chart_type == "grouped_aggregate":
        return grouped_aggregate(
            df, kwargs.get("group_by"), kwargs.get("y"), kwargs.get("agg", "mean")
        )
    if chart_type == "line":
        return line_chart(
            df, kwargs.get("x"), kwargs.get("y"),
            kwargs.get("freq", "M"), kwargs.get("agg", "mean"),
        )
    raise ChartError(f"Unsupported chart type {chart_type!r}.")
