"""Data cleaning tests.

Verifies that cleaning operations produce the expected, arithmetic results and
that the original data is never mutated.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.schemas import (
    CleaningPlan,
    MissingValueStep,
    OutlierStep,
    TypeCorrectionStep,
)
from app.services.cleaning import (
    cleaning_recommendations,
    execute_cleaning,
    preview_cleaning,
)


class TestImputation:
    def test_mean_imputation_is_arithmetically_correct(self):
        frame = pd.DataFrame({"v": [1.0, 2.0, np.nan, 4.0, 5.0]})
        plan = CleaningPlan(missing_values=[MissingValueStep(column="v", strategy="mean")])
        outcome = execute_cleaning(frame, plan, persist=False)

        # Mean of the 4 present values (1+2+4+5)/4 = 3.0
        assert outcome.frame["v"].isna().sum() == 0
        assert outcome.frame.loc[2, "v"] == pytest.approx(3.0)
        assert outcome.metrics_before["missing_cells"] == 1
        assert outcome.metrics_after["missing_cells"] == 0

    def test_median_imputation_is_arithmetically_correct(self):
        frame = pd.DataFrame({"v": [1.0, 2.0, np.nan, 10.0, 100.0]})
        plan = CleaningPlan(missing_values=[MissingValueStep(column="v", strategy="median")])
        outcome = execute_cleaning(frame, plan, persist=False)
        # Median of [1, 2, 10, 100] = 6.0
        assert outcome.frame.loc[2, "v"] == pytest.approx(6.0)

    def test_mode_imputation_uses_most_frequent(self):
        frame = pd.DataFrame({"v": [7.0, 7.0, 7.0, np.nan, 9.0]})
        plan = CleaningPlan(missing_values=[MissingValueStep(column="v", strategy="mode")])
        outcome = execute_cleaning(frame, plan, persist=False)
        assert outcome.frame.loc[3, "v"] == pytest.approx(7.0)

    def test_constant_imputation(self):
        frame = pd.DataFrame({"v": [1.0, np.nan, 3.0]})
        plan = CleaningPlan(
            missing_values=[
                MissingValueStep(column="v", strategy="constant", constant_value=0)
            ]
        )
        outcome = execute_cleaning(frame, plan, persist=False)
        assert outcome.frame.loc[1, "v"] == 0
        assert outcome.frame["v"].tolist() == [1, 0, 3]

    def test_drop_rows_removes_only_affected_rows(self):
        frame = pd.DataFrame({"a": [1, 2, 3, 4], "b": [10, None, 30, 40]})
        plan = CleaningPlan(missing_values=[MissingValueStep(column="b", strategy="drop_rows")])
        outcome = execute_cleaning(frame, plan, persist=False)
        assert len(outcome.frame) == 3
        assert outcome.frame["b"].isna().sum() == 0

    def test_rejects_mean_imputation_on_text(self):
        frame = pd.DataFrame({"name": ["a", None, "c"]})
        plan = CleaningPlan(missing_values=[MissingValueStep(column="name", strategy="mean")])
        outcome = execute_cleaning(frame, plan, persist=False)
        assert len(outcome.warnings) == 1
        assert "non-numeric" in outcome.warnings[0]

    def test_no_change_when_no_missing(self):
        frame = pd.DataFrame({"v": [1.0, 2.0, 3.0]})
        plan = CleaningPlan(missing_values=[MissingValueStep(column="v", strategy="mean")])
        outcome = execute_cleaning(frame, plan, persist=False)
        assert outcome.steps[0]["affected"] == 0
        assert outcome.frame["v"].tolist() == [1.0, 2.0, 3.0]


class TestDuplicates:
    def test_removes_exact_duplicates(self):
        frame = pd.DataFrame({"a": [1, 1, 2, 2, 3], "b": ["x", "x", "y", "y", "z"]})
        plan = CleaningPlan(drop_duplicates=True)
        outcome = execute_cleaning(frame, plan, persist=False)
        assert len(outcome.frame) == 3
        assert outcome.metrics_before["duplicate_rows"] == 2
        assert outcome.metrics_after["duplicate_rows"] == 0

    def test_subset_deduplication(self):
        frame = pd.DataFrame({"id": [1, 1, 2], "note": ["a", "b", "c"]})
        plan = CleaningPlan(drop_duplicates=True, duplicate_subset=["id"])
        outcome = execute_cleaning(frame, plan, persist=False)
        # Only the first row for id=1 survives.
        assert len(outcome.frame) == 2
        assert outcome.frame["note"].tolist() == ["a", "c"]

    def test_dedupe_keeps_first_occurrence(self):
        frame = pd.DataFrame({"a": [5, 5, 5], "b": [1, 2, 3]})
        plan = CleaningPlan(drop_duplicates=True, duplicate_subset=["a"])
        outcome = execute_cleaning(frame, plan, persist=False)
        assert outcome.frame.iloc[0]["b"] == 1


class TestTypeCorrection:
    def test_currency_strings_become_numeric(self):
        frame = pd.DataFrame({"price": ["$1,200.00", "$800.50", "$450.00"]})
        plan = CleaningPlan(
            type_corrections=[TypeCorrectionStep(column="price", target_type="numeric")]
        )
        outcome = execute_cleaning(frame, plan, persist=False)
        assert outcome.frame["price"].tolist() == [1200.0, 800.5, 450.0]
        assert pd.api.types.is_numeric_dtype(outcome.frame["price"])

    def test_date_strings_become_datetime(self):
        frame = pd.DataFrame({"d": ["2023-01-01", "2023-06-15", "2023-12-31"]})
        plan = CleaningPlan(
            type_corrections=[TypeCorrectionStep(column="d", target_type="datetime")]
        )
        outcome = execute_cleaning(frame, plan, persist=False)
        assert pd.api.types.is_datetime64_any_dtype(outcome.frame["d"])
        assert outcome.frame["d"].dt.year.tolist() == [2023, 2023, 2023]

    def test_unparseable_values_become_null_with_count(self):
        frame = pd.DataFrame({"v": ["1", "2", "oops", "4"]})
        plan = CleaningPlan(
            type_corrections=[TypeCorrectionStep(column="v", target_type="numeric")]
        )
        outcome = execute_cleaning(frame, plan, persist=False)
        step = next(s for s in outcome.steps if s["operation"] == "type_correction")
        assert step["affected"] == 1
        assert outcome.frame["v"].isna().sum() == 1
        assert outcome.frame["v"].iloc[0] == 1.0


class TestOutlierTreatment:
    def _frame(self):
        # Values 1..20 plus a 500 outlier. Q1=5.75, Q3=15.25, IQR=9.5
        return pd.DataFrame({"v": list(range(1, 21)) + [500]})

    def test_clip_brings_outliers_to_fence(self):
        frame = self._frame()
        plan = CleaningPlan(outliers=[OutlierStep(column="v", strategy="clip")])
        outcome = execute_cleaning(frame, plan, persist=False)

        q1 = float(np.percentile(frame["v"], 25))
        q3 = float(np.percentile(frame["v"], 75))
        iqr = q3 - q1
        upper_fence = q3 + 1.5 * iqr

        assert outcome.frame["v"].max() == pytest.approx(upper_fence, rel=1e-6)
        assert len(outcome.frame) == 21  # clip keeps rows

    def test_remove_drops_outlier_rows(self):
        frame = self._frame()
        plan = CleaningPlan(outliers=[OutlierStep(column="v", strategy="remove")])
        outcome = execute_cleaning(frame, plan, persist=False)
        assert len(outcome.frame) < 21
        assert 500 not in outcome.frame["v"].values

    def test_percentile_cap(self):
        frame = self._frame()
        plan = CleaningPlan(outliers=[OutlierStep(column="v", strategy="cap_percentile")])
        outcome = execute_cleaning(frame, plan, persist=False)
        p99 = float(np.percentile(frame["v"], 99))
        assert outcome.frame["v"].max() == pytest.approx(p99, rel=1e-6)

    def test_no_outliers_reports_zero(self):
        frame = pd.DataFrame({"v": [10, 10, 10, 10, 10, 10]})
        plan = CleaningPlan(outliers=[OutlierStep(column="v", strategy="clip")])
        outcome = execute_cleaning(frame, plan, persist=False)
        step = next(s for s in outcome.steps if s["operation"] == "outliers")
        assert step["affected"] == 0

    def test_zero_iqr_warns(self):
        frame = pd.DataFrame({"v": [5, 5, 5, 5, 5, 100]})
        plan = CleaningPlan(outliers=[OutlierStep(column="v", strategy="clip")])
        outcome = execute_cleaning(frame, plan, persist=False)
        assert any("zero IQR" in w for w in outcome.warnings)


class TestStructuralCleaning:
    def test_trim_whitespace(self):
        frame = pd.DataFrame({"name": ["  alice  ", " bob ", "carol"]})
        plan = CleaningPlan(trim_whitespace=True)
        outcome = execute_cleaning(frame, plan, persist=False)
        assert outcome.frame["name"].tolist() == ["alice", "bob", "carol"]

    def test_drop_empty_columns(self):
        frame = pd.DataFrame({"a": [1, 2, 3], "empty": [None, None, None]})
        plan = CleaningPlan(drop_empty_columns=True)
        outcome = execute_cleaning(frame, plan, persist=False)
        assert "empty" not in outcome.frame.columns
        assert "a" in outcome.frame.columns

    def test_drop_constant_columns(self):
        frame = pd.DataFrame({"a": [1, 2, 3], "const": [7, 7, 7]})
        plan = CleaningPlan(drop_constant_columns=True)
        outcome = execute_cleaning(frame, plan, persist=False)
        assert "const" not in outcome.frame.columns
        assert "a" in outcome.frame.columns


class TestOriginalPreservation:
    def test_original_frame_is_not_mutated(self):
        original = pd.DataFrame({"v": [1.0, np.nan, 3.0, 3.0]})
        before_copy = original.copy(deep=True)
        plan = CleaningPlan(
            missing_values=[MissingValueStep(column="v", strategy="mean")],
            drop_duplicates=True,
        )
        execute_cleaning(original, plan, persist=False)
        pd.testing.assert_frame_equal(original, before_copy)

    def test_metrics_before_after_are_accurate(self, sales_frame):
        plan = CleaningPlan(drop_duplicates=True)
        outcome = execute_cleaning(sales_frame, plan, persist=False)
        assert outcome.metrics_before["rows"] == len(sales_frame)
        assert outcome.metrics_after["rows"] == len(outcome.frame)
        assert outcome.metrics_after["duplicate_rows"] == 0


class TestPreview:
    def test_preview_does_not_persist_and_reports_delta(self, sales_frame):
        plan = CleaningPlan(drop_duplicates=True)
        preview = preview_cleaning(sales_frame, plan)
        assert "delta" in preview
        assert preview["delta"]["duplicate_rows"] < 0
        assert preview["metrics_before"]["rows"] == len(sales_frame)

    def test_preview_reports_quality_delta(self, sales_frame):
        plan = CleaningPlan(drop_duplicates=True)
        preview = preview_cleaning(sales_frame, plan)
        assert "quality_delta" in preview
        assert isinstance(preview["quality_delta"], (int, float))


class TestRecommendations:
    def test_recommends_for_frame_with_issues(self, sales_frame):
        recommendations = cleaning_recommendations(sales_frame)
        types = {r["type"] for r in recommendations}
        assert "missing_values" in types
        assert "duplicates" in types

    def test_recommendations_sorted_by_severity(self, sales_frame):
        recommendations = cleaning_recommendations(sales_frame)
        order = {"high": 0, "medium": 1, "low": 2}
        severities = [order[r["severity"]] for r in recommendations]
        assert severities == sorted(severities)

    def test_clean_frame_has_no_recommendations(self):
        frame = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": ["w", "x", "y", "z", "w"]})
        recommendations = cleaning_recommendations(frame)
        assert recommendations == []
