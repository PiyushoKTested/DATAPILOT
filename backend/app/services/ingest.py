"""Dataset ingestion: CSV / TSV / XLSX / JSON parsing into pandas.

Files are stored on disk as parquet snapshots so analytical reads are fast and
the original upload is preserved separately and immutably.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import HTTPException, UploadFile

from ..config import settings

CSV_ENCODINGS = ("utf-8-sig", "utf-8", "latin-1", "cp1252")
CSV_SEPARATORS = (",", ";", "\t", "|")


class DatasetParseError(Exception):
    """Raised when an uploaded file cannot be parsed into a DataFrame."""


def _sniff_csv_text(raw: bytes) -> str:
    last_error: Exception | None = None
    for encoding in CSV_ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError as exc:  # try the next encoding
            last_error = exc
    raise DatasetParseError(
        f"Could not decode the file as text. Tried {', '.join(CSV_ENCODINGS)}."
    ) from last_error


def _pick_csv_separator(text: str) -> str:
    """Choose the separator that yields the most consistent column count."""
    sample_lines = [line for line in text.splitlines()[:40] if line.strip()]
    if not sample_lines:
        return ","
    best_sep = ","
    best_score = -1.0
    for sep in CSV_SEPARATORS:
        counts = [line.count(sep) for line in sample_lines]
        if not counts or max(counts) == 0:
            continue
        # Reward many fields and consistency across rows.
        if len(set(counts)) == 1:
            score = counts[0] * 10
        else:
            score = max(counts) - (max(counts) - min(counts))
        if score > best_score:
            best_score = score
            best_sep = sep
    return best_sep


def _read_csv(raw: bytes) -> pd.DataFrame:
    text = _sniff_csv_text(raw)
    separator = _pick_csv_separator(text)
    try:
        frame = pd.read_csv(
            io.StringIO(text),
            sep=separator,
            engine="python",
            on_bad_lines="warn",
            skip_blank_lines=True,
        )
    except Exception as exc:  # noqa: BLE001
        raise DatasetParseError(f"CSV parsing failed: {exc}") from exc
    return frame


def _read_excel(raw: bytes) -> pd.DataFrame:
    try:
        sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None, engine="openpyxl")
    except Exception as exc:  # noqa: BLE001
        raise DatasetParseError(f"Excel parsing failed: {exc}") from exc
    if not sheets:
        raise DatasetParseError("The workbook contains no sheets.")
    # Pick the sheet with the most rows (most likely the real data table).
    best_name, best_frame = max(sheets.items(), key=lambda item: len(item[1].index))
    best_frame = best_frame.copy()
    best_frame.attrs["sheet_name"] = best_name
    return best_frame


def _read_json(raw: bytes) -> pd.DataFrame:
    text = _sniff_csv_text(raw)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # Fall back to newline-delimited JSON.
        rows: list[Any] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise DatasetParseError(
                    f"JSON parsing failed near: {line[:80]!r}"
                ) from exc
        payload = rows

    if isinstance(payload, dict):
        # Common envelope shapes: {"data": [...]}, {"rows": [...]}, {"records": [...]}
        for key in ("data", "rows", "records", "results", "items"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            # A dict of columns -> lists.
            if payload and all(isinstance(v, list) for v in payload.values()):
                try:
                    return pd.DataFrame(payload)
                except ValueError:
                    pass
            payload = [payload]

    if not isinstance(payload, list):
        raise DatasetParseError("JSON must contain an array of objects or a column mapping.")
    if not payload:
        raise DatasetParseError("JSON array is empty.")

    try:
        frame = pd.json_normalize(payload)
    except Exception as exc:  # noqa: BLE001
        raise DatasetParseError(f"JSON normalisation failed: {exc}") from exc
    return frame


def parse_upload(raw: bytes, filename: str) -> pd.DataFrame:
    """Parse raw file bytes into a DataFrame based on the file extension."""
    suffix = Path(filename).suffix.lower()
    if suffix in {".csv", ".tsv"}:
        frame = _read_csv(raw)
    elif suffix in {".xlsx", ".xlsm"}:
        frame = _read_excel(raw)
    elif suffix in {".json", ".jsonl", ".ndjson"}:
        frame = _read_json(raw)
    else:
        raise DatasetParseError(f"Unsupported file type {suffix!r}.")

    if frame is None or frame.shape[1] == 0:
        raise DatasetParseError("No tabular columns were detected in the file.")

    frame = sanitise_frame(frame)
    if frame.shape[0] == 0:
        raise DatasetParseError("The file parsed successfully but contains zero data rows.")
    return frame


def sanitise_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalise column names and drop fully-empty index columns."""
    frame = frame.copy()
    # Remove unnamed index columns produced by CSV exports.
    drop_cols = [
        c for c in frame.columns
        if isinstance(c, str) and (c.startswith("Unnamed:") or c.strip() == "")
    ]
    if drop_cols and len(drop_cols) < len(frame.columns):
        frame = frame.drop(columns=drop_cols)

    seen: dict[str, int] = {}
    new_columns: list[str] = []
    for column in frame.columns:
        name = str(column).strip() or "column"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        new_columns.append(name)
    frame.columns = new_columns
    return frame.reset_index(drop=True)


async def read_upload_file(file: UploadFile) -> bytes:
    """Read an UploadFile with size validation."""
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds the {settings.MAX_UPLOAD_MB} MB upload limit.",
            )
        chunks.append(chunk)
    if total == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    return b"".join(chunks)


def save_version_snapshot(frame: pd.DataFrame, storage_dir: Path, dataset_uid: str,
                          version_number: int) -> Path:
    """Persist a dataframe as a parquet snapshot and return its path."""
    storage_dir.mkdir(parents=True, exist_ok=True)
    path = storage_dir / f"{dataset_uid}_v{version_number}.parquet"
    to_store = frame.copy()
    # Parquet needs hashable, uniform column names.
    to_store.columns = [str(c) for c in to_store.columns]
    try:
        to_store.to_parquet(path, index=False, engine="pyarrow")
    except Exception:  # noqa: BLE001 - mixed object columns can break pyarrow
        to_store.astype(str).to_parquet(path, index=False, engine="pyarrow")
    return path


def load_version_frame(path: str | Path) -> pd.DataFrame:
    return pd.read_parquet(path, engine="pyarrow")
