"""JSON-safe serialisation helpers.

Pandas/NumPy produce types (np.int64, np.float64, Timestamp, NaN) that the
standard json encoder cannot handle. Every analysis response passes through
these helpers so API output is always valid JSON.
"""
from __future__ import annotations

import math
from datetime import date, datetime, time
from typing import Any

import numpy as np
import pandas as pd


def _clean_float(value: float) -> float | None:
    if math.isnan(value) or math.isinf(value):
        return None
    return float(value)


_ATOMIC_SCALARS = (str, bool, int, float, type(None))


def to_jsonable(value: Any) -> Any:
    """Recursively convert an arbitrary value into JSON-serialisable Python.

    Order matters: numpy scalar types subclass Python numbers/bools, so the
    numpy checks must come first, and plain Python ``int``/``float`` must be
    handled explicitly — otherwise they fall through and become strings.
    """
    # --- numpy scalars first (they subclass Python types) ---------------
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return _clean_float(float(value))

    # --- pandas temporal / numpy datetime -------------------------------
    if isinstance(value, (np.datetime64, pd.Timestamp)):
        if pd.isna(value):
            return None
        return pd.Timestamp(value).isoformat()
    if isinstance(value, np.timedelta64):
        return str(value)

    # --- plain Python scalars -------------------------------------------
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return _clean_float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    # --- containers ------------------------------------------------------
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return [to_jsonable(v) for v in value.tolist()]
    if isinstance(value, pd.Series):
        return [to_jsonable(v) for v in value.tolist()]
    if isinstance(value, pd.DataFrame):
        return to_jsonable(value.to_dict(orient="records"))

    # --- NaN / NaT / pd.NA for anything left over -----------------------
    try:
        if pd.isna(value) is True:
            return None
    except (TypeError, ValueError):
        pass

    try:
        return str(value)
    except Exception:  # pragma: no cover - defensive
        return None


def safe_number(value: Any) -> float | None:
    """Return a finite float or None."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return _clean_float(result)


def round_number(value: Any, digits: int = 4) -> float | None:
    number = safe_number(value)
    if number is None:
        return None
    return round(number, digits)


def round_p_value(value: Any, digits: int = 6) -> float | None:
    """Round a p-value while preserving very small magnitudes.

    Naive decimal rounding turns 1.24e-11 into 0.0, which would misreport a
    highly significant result. Small values keep significant-figure precision
    instead; ordinary values round to ``digits`` decimals.
    """
    number = safe_number(value)
    if number is None:
        return None
    if number == 0.0:
        return 0.0
    if abs(number) < 1e-4:
        # Preserve magnitude with significant-figure formatting.
        return float(f"{number:.6g}")
    return round(number, digits)
