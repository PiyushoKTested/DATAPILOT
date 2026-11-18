"""Column type inference utilities.

Pandas' native dtype is a starting point, but CSV ingestion makes almost every
numeric column look like `object`. These helpers make a semantic decision about
whether a column is numeric, datetime, boolean, categorical or free text, and can
optionally coerce it.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

NUMERIC = "numeric"
DATETIME = "datetime"
BOOLEAN = "boolean"
CATEGORICAL = "categorical"
TEXT = "text"

BOOLEAN_TRUE = {"true", "yes", "y", "1", "t"}
BOOLEAN_FALSE = {"false", "no", "n", "0", "f"}

# A categorical column has at most this many distinct values (and under 20% of rows).
CATEGORICAL_MAX_UNIQUE = 50
CATEGORICAL_MAX_RATIO = 0.2


@dataclass
class ColumnInfo:
    name: str
    kind: str
    pandas_dtype: str
    non_null_count: int
    null_count: int
    unique_count: int
    sample_values: list


CURRENCY_PREFIX = r"^[\s]*[$€£₹¥₩₽]\s*"


def _numeric_cleanup(series: pd.Series) -> pd.Series:
    """Normalise currency symbols, thousand separators and blanks for parsing."""
    cleaned = series.astype(str).str.strip()
    cleaned = cleaned.str.replace(r"[$€£₹¥₩₽]", "", regex=True)
    cleaned = cleaned.str.replace(",", "", regex=False)
    cleaned = cleaned.str.replace("%", "", regex=False)
    cleaned = cleaned.replace({"": None, "nan": None, "None": None, "NaN": None,
                               "-": None, "n/a": None, "N/A": None})
    return cleaned


def _is_numeric_series(series: pd.Series) -> bool:
    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        return True
    non_null = series.dropna()
    if non_null.empty:
        return False
    if not (non_null.map(lambda v: isinstance(v, (int, float, np.number))).all()):
        # Try a string coercion on a sample (handles "$1,200.00" and "45%").
        sample = _numeric_cleanup(non_null.head(200))
        converted = pd.to_numeric(sample, errors="coerce")
        # Blanks we deliberately nulled out are not evidence of non-numericity.
        parsed_mask = converted.notna() | sample.isna()
        return parsed_mask.mean() >= 0.95
    return True


def _is_datetime_series(series: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    non_null = series.dropna()
    if non_null.empty:
        return False
    if _is_numeric_series(series):
        return False
    sample = non_null.head(100).astype(str)
    # Require the strings to look date-ish before a costly parse.
    looks_datelike = sample.str.contains(r"[-/:]", regex=True).mean() >= 0.8
    if not looks_datelike:
        return False
    try:
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    except (ValueError, TypeError):
        try:
            parsed = pd.to_datetime(sample, errors="coerce")
        except (ValueError, TypeError):
            return False
    return parsed.notna().mean() >= 0.9


def _is_boolean_series(series: pd.Series) -> bool:
    if pd.api.types.is_bool_dtype(series):
        return True
    non_null = series.dropna()
    if non_null.empty or len(non_null) > 0 and non_null.nunique() > 2:
        return False
    values = {str(v).strip().lower() for v in non_null.unique()}
    return bool(values) and values.issubset(BOOLEAN_TRUE | BOOLEAN_FALSE)


def infer_kind(series: pd.Series) -> str:
    """Infer a semantic column kind."""
    if _is_boolean_series(series):
        return BOOLEAN
    if _is_datetime_series(series):
        return DATETIME
    if _is_numeric_series(series):
        return NUMERIC
    non_null = series.dropna()
    if non_null.empty:
        return TEXT
    unique = non_null.nunique()
    total = len(non_null)
    if unique <= 1:
        return CATEGORICAL
    if unique <= CATEGORICAL_MAX_UNIQUE and (unique / total) <= CATEGORICAL_MAX_RATIO:
        return CATEGORICAL
    if unique <= 20 and total <= 60:
        return CATEGORICAL
    return TEXT


def describe_column(df: pd.DataFrame, column: str) -> ColumnInfo:
    series = df[column]
    return ColumnInfo(
        name=column,
        kind=infer_kind(series),
        pandas_dtype=str(series.dtype),
        non_null_count=int(series.notna().sum()),
        null_count=int(series.isna().sum()),
        unique_count=int(series.nunique(dropna=True)),
        sample_values=[_sample(v) for v in series.dropna().head(5).tolist()],
    )


def _sample(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return str(value)
    return str(value) if not isinstance(value, (int, float, bool)) else value


def classify_all(df: pd.DataFrame) -> dict[str, str]:
    return {column: infer_kind(df[column]) for column in df.columns}


def coerce_column(series: pd.Series, target: str) -> tuple[pd.Series, int]:
    """Coerce a series to a target kind. Returns (series, failure_count)."""
    if target == NUMERIC:
        # Always normalise first: the "already numeric" fast path still needs
        # cleanup, because a column of "$1,200.00" strings is classified as
        # numeric yet cannot be converted without stripping the symbol/comma.
        cleaned = _numeric_cleanup(series)
        converted = pd.to_numeric(cleaned, errors="coerce")
        failures = int(converted.isna().sum() - series.isna().sum())
        return converted, max(failures, 0)

    if target == DATETIME:
        converted = pd.to_datetime(series, errors="coerce", format="mixed")
        failures = int(converted.isna().sum() - series.isna().sum())
        return converted, max(failures, 0)

    if target == BOOLEAN:
        mapping = {**{k: True for k in BOOLEAN_TRUE}, **{k: False for k in BOOLEAN_FALSE}}
        lowered = series.astype(str).str.strip().str.lower()
        converted = lowered.map(mapping)
        converted = converted.where(series.notna(), None)
        failures = int(converted.isna().sum() - series.isna().sum())
        return converted, max(failures, 0)

    if target in (CATEGORICAL, TEXT):
        as_str = series.astype("string")
        if target == CATEGORICAL:
            as_str = as_str.astype("category")
        return as_str, 0

    raise ValueError(f"Unknown target type {target!r}")
