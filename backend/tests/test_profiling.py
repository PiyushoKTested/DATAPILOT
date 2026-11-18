"""Profiling tests.

Statistics are checked against values computed independently (numpy/statistics
module or hand calculation) rather than against the profiler's own output.
"""
from __future__ import annotations

import math
import statistics

import numpy as np
import pandas as pd
import pytest

from app.services.profiling import (
    compute_quality,
    key_findings,
    numeric_summary_table,
    preview_dataframe,
    profile_dataframe,
)


class TestShapeAndTypes:
    def test_shape_matches_dataframe(self, sales_frame):
        profile = profile_dataframe(sales_frame)
        assert profile["shape"]["rows"] == len(sales_frame)
        assert profile["shape"]["columns"] == len(sales_frame.columns)

    def test_column_groups_partition_all_columns(self, sales_frame):
        profile = profile_dataframe(sales_frame)
        groups = profile["column_groups"]
        grouped = (
            groups["numeric"] + groups["categorical"]
            + groups["datetime"] + groups["text"]
        )
        assert sorted(grouped) == sorted(sales_frame.columns)


class TestMissingValues:
    def test_missing_count_matches_independent_count(self, sales_frame):
        profile = profile_dataframe(sales_frame)
        column = next(c for c in profile["columns"] if c["name"] == "satisfaction_score")
        expected = int(sales_frame["satisfaction_score"].isna().sum())
        assert column["missing"] == expected
        assert expected > 0

    def test_missing_percentage_is_correct(self, sales_frame):
        profile = profile_dataframe(sales_frame)
        column = next(c for c in profile["columns"] if c["name"] == "satisfaction_score")
        expected_pct = 100 * sales_frame["satisfaction_score"].isna().sum() / len(sales_frame)
        # missing_pct is rounded to 4 decimals by contract.
        assert column["missing_pct"] == pytest.approx(expected_pct, abs=1e-3)

    def test_missing_total_matches(self, sales_frame):
        profile = profile_dataframe(sales_frame)
        assert profile["missing_total"] == int(sales_frame.isna().sum().sum())

    def test_missing_by_column_sorted_descending(self, sales_frame):
        profile = profile_dataframe(sales_frame)
        counts = [item["missing"] for item in profile["missing_by_column"]]
        assert counts == sorted(counts, reverse=True)


class TestDuplicates:
    def test_duplicate_count_matches(self, sales_frame):
        profile = profile_dataframe(sales_frame)
        expected = int(sales_frame.duplicated().sum())
        assert profile["duplicates"]["duplicate_rows"] == expected
        assert expected > 0

    def test_no_duplicates_in_clean_frame(self, tiny_frame):
        profile = profile_dataframe(tiny_frame)
        assert profile["duplicates"]["duplicate_rows"] == 0


class TestNumericStatistics:
    """Verify each statistic against Python's `statistics` module."""

    def test_mean_median_std_are_exact(self, tiny_frame):
        profile = profile_dataframe(tiny_frame)
        column = next(c for c in profile["columns"] if c["name"] == "x")
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

        assert column["stats"]["mean"] == pytest.approx(statistics.mean(values))
        assert column["stats"]["mean"] == 5.5
        assert column["stats"]["median"] == pytest.approx(statistics.median(values))
        assert column["stats"]["median"] == 5.5
        # std is rounded to 4 decimals by contract.
        assert column["stats"]["std"] == pytest.approx(
            statistics.stdev(values), abs=1e-4
        )
        assert column["stats"]["min"] == 1
        assert column["stats"]["max"] == 10
        assert column["stats"]["sum"] == 55

    def test_mode_of_known_values(self):
        frame = pd.DataFrame({"v": [1, 2, 2, 3, 4, 2]})
        profile = profile_dataframe(frame)
        column = profile["columns"][0]
        assert column["stats"]["mode"] == 2

    def test_quartiles_match_numpy_linear_interpolation(self, tiny_frame):
        profile = profile_dataframe(tiny_frame)
        column = next(c for c in profile["columns"] if c["name"] == "x")
        values = np.arange(1, 11)
        assert column["stats"]["q1"] == pytest.approx(np.percentile(values, 25))
        assert column["stats"]["q3"] == pytest.approx(np.percentile(values, 75))
        assert column["stats"]["iqr"] == pytest.approx(
            np.percentile(values, 75) - np.percentile(values, 25)
        )

    def test_iqr_outlier_detection_exact(self):
        # 1..99 in steps of 1, plus one value of 1000 (a clear outlier).
        values = list(range(1, 100)) + [1000]
        frame = pd.DataFrame({"v": values})
        profile = profile_dataframe(frame)
        stats_block = profile["columns"][0]["stats"]

        q1 = float(np.percentile(values, 25))
        q3 = float(np.percentile(values, 75))
        iqr = q3 - q1
        expected_outliers = sum(
            1 for v in values if v < q1 - 1.5 * iqr or v > q3 + 1.5 * iqr
        )
        assert stats_block["outlier_count"] == expected_outliers
        assert expected_outliers >= 1  # the 1000 must be caught

    def test_outlier_fences_are_correct(self, tiny_frame):
        profile = profile_dataframe(tiny_frame)
        column = next(c for c in profile["columns"] if c["name"] == "x")
        q1 = column["stats"]["q1"]
        q3 = column["stats"]["q3"]
        iqr = q3 - q1
        assert column["stats"]["lower_fence"] == pytest.approx(q1 - 1.5 * iqr)
        assert column["stats"]["upper_fence"] == pytest.approx(q3 + 1.5 * iqr)

    def test_skewness_zero_for_symmetric_data(self, tiny_frame):
        profile = profile_dataframe(tiny_frame)
        column = next(c for c in profile["columns"] if c["name"] == "x")
        # 1..10 is symmetric, so skewness is exactly 0.
        assert abs(column["stats"]["skewness"]) < 1e-10

    def test_iris_means_match_known_values(self, iris_frame):
        """Canonical iris statistics: sepal_length mean = 5.843333."""
        profile = profile_dataframe(iris_frame)
        column = next(c for c in profile["columns"] if c["name"] == "sepal_length")
        assert column["stats"]["mean"] == pytest.approx(5.8433, abs=1e-3)
        assert column["stats"]["min"] == pytest.approx(4.3)
        assert column["stats"]["max"] == pytest.approx(7.9)
        assert column["stats"]["count"] == 150


class TestCategoricalFrequency:
    def test_frequency_counts_are_correct(self, iris_frame):
        profile = profile_dataframe(iris_frame)
        column = next(c for c in profile["columns"] if c["name"] == "species")
        assert column["unique"] == 3
        counts = {item["value"]: item["count"] for item in column["frequency"]}
        assert counts == {"setosa": 50, "versicolor": 50, "virginica": 50}

    def test_frequency_percentages_sum_to_100(self, iris_frame):
        profile = profile_dataframe(iris_frame)
        column = next(c for c in profile["columns"] if c["name"] == "species")
        total_pct = sum(item["percentage"] for item in column["frequency"])
        assert total_pct == pytest.approx(100.0, abs=0.01)


class TestQualityScore:
    def test_quality_score_within_bounds(self, sales_frame):
        profile = profile_dataframe(sales_frame)
        quality = profile["quality"]
        assert 0 <= quality["score"] <= 100
        assert quality["grade"] in {"A", "B", "C", "D", "F"}

    def test_perfect_data_scores_100(self):
        frame = pd.DataFrame({
            "a": [1, 2, 3, 4, 5, 6, 7, 8],
            "b": ["x", "y", "x", "y", "x", "y", "x", "y"],
        })
        profile = profile_dataframe(frame)
        assert profile["quality"]["score"] == 100.0
        assert profile["quality"]["grade"] == "A"

    def test_quality_components_match_documented_formula(self, sales_frame):
        profile = profile_dataframe(sales_frame)
        quality = profile["quality"]
        components = quality["components"]
        weights = quality["weights"]

        recomputed = (
            components["completeness"] * weights["completeness"]
            + components["uniqueness"] * weights["uniqueness"]
            + components["validity"] * weights["validity"]
            + components["outlier_health"] * weights["outlier_health"]
        )
        assert quality["score"] == pytest.approx(recomputed, abs=0.01)

    def test_weights_sum_to_one(self):
        from app.services.profiling import QUALITY_WEIGHTS

        assert sum(QUALITY_WEIGHTS.values()) == pytest.approx(1.0)

    def test_completeness_component_is_arithmetically_correct(self):
        # 2 rows x 2 cols = 4 cells, 1 missing -> completeness = 75%.
        frame = pd.DataFrame({"a": [1.0, None], "b": [3.0, 4.0]})
        quality = compute_quality(
            frame,
            {"a": "numeric", "b": "numeric"},
            [
                {"kind": "numeric", "non_null": 1,
                 "stats": {"outlier_count": 0}},
                {"kind": "numeric", "non_null": 2,
                 "stats": {"outlier_count": 0}},
            ],
        )
        assert quality["components"]["completeness"] == pytest.approx(75.0)

    def test_duplicate_rows_lower_uniqueness(self):
        frame = pd.DataFrame({"a": [1, 1, 1, 1]})
        quality = compute_quality(
            frame, {"a": "numeric"},
            [{"kind": "numeric", "non_null": 4, "stats": {"outlier_count": 0}}],
        )
        # 3 of 4 rows are duplicates -> uniqueness = 25%.
        assert quality["components"]["uniqueness"] == pytest.approx(25.0)


class TestPreviewAndSummaries:
    def test_preview_limits_rows(self, sales_frame):
        preview = preview_dataframe(sales_frame, limit=10)
        assert len(preview["rows"]) == 10
        assert preview["truncated"] is True
        assert preview["total_rows"] == len(sales_frame)

    def test_numeric_summary_only_includes_numeric(self, sales_frame):
        rows = numeric_summary_table(sales_frame)
        names = [row["column"] for row in rows]
        assert "revenue" in names
        assert "region" not in names
        assert "product" not in names

    def test_findings_are_generated(self, sales_frame):
        profile = profile_dataframe(sales_frame)
        findings = key_findings(profile)
        assert len(findings) >= 3
        assert all(isinstance(f, str) and f for f in findings)
        assert any("rows" in f for f in findings)
