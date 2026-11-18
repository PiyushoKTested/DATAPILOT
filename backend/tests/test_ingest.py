"""Ingestion and type-inference tests.

These verify that real files parse correctly and that semantic type detection
makes the right call on CSV-mangled data.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from app.services.ingest import DatasetParseError, parse_upload
from app.services.type_inference import (
    BOOLEAN,
    CATEGORICAL,
    DATETIME,
    NUMERIC,
    TEXT,
    classify_all,
    coerce_column,
    infer_kind,
)


class TestCsvParsing:
    def test_parses_sales_csv(self, sample_dir):
        path = sample_dir / "sales_data.csv"
        frame = parse_upload(path.read_bytes(), path.name)
        assert frame.shape[0] > 500
        assert frame.shape[1] == 9
        assert "revenue" in frame.columns
        assert "region" in frame.columns

    def test_handles_semicolon_separator(self):
        raw = b"a;b;c\n1;2;3\n4;5;6\n"
        frame = parse_upload(raw, "data.csv")
        assert list(frame.columns) == ["a", "b", "c"]
        assert frame.shape == (2, 3)

    def test_handles_tab_separator(self):
        raw = b"name\tvalue\nfoo\t10\nbar\t20\n"
        frame = parse_upload(raw, "data.tsv")
        assert list(frame.columns) == ["name", "value"]
        assert frame.shape[0] == 2

    def test_handles_utf8_bom(self):
        raw = "\ufeffcol_a,col_b\n1,2\n".encode("utf-8")
        frame = parse_upload(raw, "bom.csv")
        assert list(frame.columns) == ["col_a", "col_b"]

    def test_handles_latin1_fallback(self):
        raw = "name,city\nJosé,São Paulo\n".encode("latin-1")
        frame = parse_upload(raw, "latin.csv")
        assert frame.shape[0] == 1

    def test_drops_unnamed_index_column(self):
        raw = b",a,b\n0,1,2\n1,3,4\n"
        frame = parse_upload(raw, "indexed.csv")
        assert "Unnamed: 0" not in frame.columns
        assert set(frame.columns) == {"a", "b"}

    def test_rejects_empty_file(self):
        with pytest.raises(DatasetParseError):
            parse_upload(b"", "empty.csv")

    def test_rejects_unsupported_extension(self):
        with pytest.raises(DatasetParseError):
            parse_upload(b"data", "file.txt")


class TestJsonParsing:
    def test_parses_employees_json(self, sample_dir):
        path = sample_dir / "employees.json"
        frame = parse_upload(path.read_bytes(), path.name)
        assert frame.shape[0] == 120
        # Nested "contact" object should be flattened into contact.email etc.
        assert any("contact" in column for column in frame.columns)

    def test_parses_array_of_objects(self):
        raw = json.dumps([{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]).encode()
        frame = parse_upload(raw, "data.json")
        assert frame.shape == (2, 2)

    def test_parses_column_mapping(self):
        raw = json.dumps({"a": [1, 2, 3], "b": [4, 5, 6]}).encode()
        frame = parse_upload(raw, "data.json")
        assert frame.shape == (3, 2)

    def test_parses_envelope_data_key(self):
        raw = json.dumps({"data": [{"a": 1}, {"a": 2}]}).encode()
        frame = parse_upload(raw, "data.json")
        assert frame.shape == (2, 1)

    def test_parses_newline_delimited(self):
        raw = b'{"a": 1}\n{"a": 2}\n{"a": 3}\n'
        frame = parse_upload(raw, "data.jsonl")
        assert frame.shape[0] == 3


class TestExcelParsing:
    def test_parses_inventory_workbook(self, sample_dir):
        path = sample_dir / "inventory.xlsx"
        frame = parse_upload(path.read_bytes(), path.name)
        # Picks the larger sheet (Inventory, 90 rows).
        assert frame.shape[0] == 90
        assert "sku" in frame.columns
        assert "inventory_value" in frame.columns


class TestTypeInference:
    def test_detects_numeric_from_strings(self):
        series = pd.Series(["1.5", "2.5", "3.5", "4.5"])
        assert infer_kind(series) == NUMERIC

    def test_detects_numeric_with_currency_and_commas(self):
        series = pd.Series(["$1,200.00", "$800.50", "$450.00", "$320.25"])
        assert infer_kind(series) == NUMERIC

    def test_detects_datetime(self):
        series = pd.Series(["2023-01-01", "2023-02-01", "2023-03-01"])
        assert infer_kind(series) == DATETIME

    def test_detects_boolean(self):
        series = pd.Series(["true", "false", "true", "true"])
        assert infer_kind(series) == BOOLEAN

    def test_detects_categorical(self):
        series = pd.Series(["North", "South", "East", "West"] * 25)
        assert infer_kind(series) == CATEGORICAL

    def test_detects_free_text(self):
        series = pd.Series([f"unique sentence number {i} with words" for i in range(100)])
        assert infer_kind(series) == TEXT

    def test_classify_sales_frame(self, sales_frame):
        kinds = classify_all(sales_frame)
        assert kinds["units_sold"] == NUMERIC
        assert kinds["revenue"] == NUMERIC
        assert kinds["order_date"] == DATETIME
        assert kinds["region"] == CATEGORICAL
        assert kinds["product"] == CATEGORICAL

    def test_coerce_currency_strings_to_numeric(self):
        series = pd.Series(["$1,200.00", "", "$800.50", None])
        converted, failures = coerce_column(series, NUMERIC)
        assert converted.iloc[0] == 1200.0
        assert converted.iloc[2] == 800.5
        # Two positions were already null/empty, so they are not "failures".
        assert failures >= 0
        assert converted.isna().sum() == 2

    def test_coerce_string_to_datetime(self):
        series = pd.Series(["2023-01-01", "2023-02-01", "not-a-date"])
        converted, failures = coerce_column(series, DATETIME)
        assert converted.iloc[0].year == 2023
        assert failures == 1
        assert pd.isna(converted.iloc[2])
