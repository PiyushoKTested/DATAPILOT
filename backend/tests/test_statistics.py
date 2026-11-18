"""Statistical correctness tests.

Every statistic is compared against an independently computed reference value,
either from scipy called directly in the test or from a hand-derived constant.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats as scipy_stats

from app.services import statistics_engine as engine


class TestPearson:
    def test_perfect_positive_correlation(self, tiny_frame):
        result = engine.pearson_correlation(tiny_frame, "x", "y")
        assert result["statistic"] == pytest.approx(1.0, abs=1e-9)
        assert result["p_value"] == pytest.approx(0.0, abs=1e-9)
        assert result["significant"] is True
        assert result["r_squared"] == pytest.approx(1.0, abs=1e-9)

    def test_perfect_negative_correlation(self, tiny_frame):
        result = engine.pearson_correlation(tiny_frame, "x", "z")
        assert result["statistic"] == pytest.approx(-1.0, abs=1e-9)
        assert "negative" in result["strength"]

    def test_matches_scipy_directly(self, sales_frame):
        clean = sales_frame[["units_sold", "revenue"]].apply(
            pd.to_numeric, errors="coerce"
        ).dropna()
        expected_r, expected_p = scipy_stats.pearsonr(clean["units_sold"], clean["revenue"])

        result = engine.pearson_correlation(sales_frame, "units_sold", "revenue")
        # The engine rounds r to 6 decimals by contract.
        assert result["statistic"] == pytest.approx(expected_r, abs=1e-6)
        assert result["p_value"] == pytest.approx(expected_p, rel=1e-4, abs=1e-12)
        assert result["n"] == len(clean)

    def test_reports_assumptions_and_limitations(self, sales_frame):
        result = engine.pearson_correlation(sales_frame, "units_sold", "revenue")
        assert len(result["assumptions"]) >= 3
        assert len(result["limitations"]) >= 2
        assert any("causation" in item.lower() for item in result["limitations"])

    def test_rejects_missing_column(self, sales_frame):
        with pytest.raises(engine.StatsError):
            engine.pearson_correlation(sales_frame, "units_sold", "not_a_column")


class TestSpearman:
    def test_perfect_monotonic(self, tiny_frame):
        result = engine.spearman_correlation(tiny_frame, "x", "y")
        assert result["statistic"] == pytest.approx(1.0, abs=1e-9)

    def test_matches_scipy_directly(self, iris_frame):
        expected_rho, expected_p = scipy_stats.spearmanr(
            iris_frame["sepal_length"], iris_frame["sepal_width"]
        )
        result = engine.spearman_correlation(iris_frame, "sepal_length", "sepal_width")
        assert result["statistic"] == pytest.approx(expected_rho, abs=1e-6)
        assert result["p_value"] == pytest.approx(expected_p, rel=1e-4, abs=1e-12)

    def test_robust_to_nonlinear_monotonic(self):
        # y = x^3 is monotonic but not linear; Spearman = 1, Pearson < 1.
        x = np.arange(1, 30, dtype=float)
        frame = pd.DataFrame({"x": x, "y": x ** 3})
        spearman = engine.spearman_correlation(frame, "x", "y")
        pearson = engine.pearson_correlation(frame, "x", "y")
        assert spearman["statistic"] == pytest.approx(1.0, abs=1e-9)
        assert pearson["statistic"] < 1.0


class TestCorrelationMatrix:
    def test_matrix_is_symmetric_with_unit_diagonal(self, iris_frame):
        result = engine.correlation_matrix(iris_frame, "pearson")
        matrix = result["matrix"]
        for column in result["columns"]:
            assert matrix[column][column] == pytest.approx(1.0, abs=1e-6)
        assert result["matrix"]["sepal_length"]["sepal_width"] == pytest.approx(
            result["matrix"]["sepal_width"]["sepal_length"], abs=1e-9
        )

    def test_strongest_pair_identified(self, tiny_frame):
        result = engine.correlation_matrix(tiny_frame, "pearson")
        # x-y and x-z are both |r| = 1.0
        assert abs(result["strongest"]["r"]) == pytest.approx(1.0, abs=1e-9)

    def test_requires_two_numeric_columns(self):
        frame = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        with pytest.raises(engine.StatsError):
            engine.correlation_matrix(frame, "pearson")


class TestTTest:
    def test_matches_scipy_welch(self, iris_frame):
        setosa = iris_frame.loc[iris_frame["species"] == "setosa", "sepal_length"]
        virginica = iris_frame.loc[iris_frame["species"] == "virginica", "sepal_length"]
        expected_t, expected_p = scipy_stats.ttest_ind(
            setosa, virginica, equal_var=False
        )

        result = engine.independent_ttest(
            iris_frame, "sepal_length", "species", "setosa", "virginica"
        )
        assert result["statistic"] == pytest.approx(expected_t, rel=1e-6)
        assert result["p_value"] == pytest.approx(expected_p, rel=1e-6)
        assert result["significant"] is True
        assert result["groups"] == ["setosa", "virginica"]

    def test_group_means_are_correct(self, iris_frame):
        result = engine.independent_ttest(
            iris_frame, "sepal_length", "species", "setosa", "versicolor"
        )
        setosa_mean = float(
            iris_frame.loc[iris_frame["species"] == "setosa", "sepal_length"].mean()
        )
        assert result["group_stats"]["setosa"]["mean"] == pytest.approx(setosa_mean, rel=1e-6)
        assert result["n"]["a"] == 50

    def test_identical_groups_not_significant(self):
        frame = pd.DataFrame({
            "value": [1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
            "group": ["A"] * 5 + ["B"] * 5,
        })
        result = engine.independent_ttest(frame, "value", "group")
        assert result["significant"] is False
        assert result["mean_difference"] == pytest.approx(0.0)

    def test_levene_included(self, iris_frame):
        result = engine.independent_ttest(iris_frame, "sepal_length", "species")
        assert "levene" in result
        assert "equal_variances" in result["levene"]

    def test_rejects_single_group(self):
        frame = pd.DataFrame({"value": [1, 2, 3], "group": ["A", "A", "A"]})
        with pytest.raises(engine.StatsError):
            engine.independent_ttest(frame, "value", "group")


class TestPairedTTest:
    def test_matches_scipy(self):
        before = [10, 12, 14, 16, 18, 20]
        after = [11, 13, 15, 17, 19, 22]
        frame = pd.DataFrame({"before": before, "after": after})
        expected_t, expected_p = scipy_stats.ttest_rel(before, after)

        result = engine.paired_ttest(frame, "before", "after")
        assert result["statistic"] == pytest.approx(expected_t, abs=1e-6)
        # p-values keep 6 significant figures, so allow abs 1e-6 here.
        assert result["p_value"] == pytest.approx(expected_p, abs=1e-6)
        # mean_difference is rounded to 4 decimals.
        assert result["mean_difference"] == pytest.approx(
            float(np.mean(np.array(before) - np.array(after))), abs=1e-4
        )


class TestOneSampleTTest:
    def test_matches_scipy(self, tiny_frame):
        expected_t, expected_p = scipy_stats.ttest_1samp(tiny_frame["x"], 5.0)
        result = engine.one_sample_ttest(tiny_frame, "x", 5.0)
        assert result["statistic"] == pytest.approx(expected_t, rel=1e-6)
        assert result["p_value"] == pytest.approx(expected_p, rel=1e-6)
        assert result["sample_mean"] == pytest.approx(5.5)

    def test_popmean_far_from_mean_is_significant(self, tiny_frame):
        result = engine.one_sample_ttest(tiny_frame, "x", 50.0)
        assert result["significant"] is True


class TestChiSquare:
    def test_matches_scipy(self, iris_frame):
        # Cross-tabulate species against a binary split of sepal width.
        frame = iris_frame.copy()
        median_width = frame["sepal_width"].median()
        frame["wide"] = np.where(frame["sepal_width"] > median_width, "yes", "no")

        table = pd.crosstab(frame["species"], frame["wide"])
        expected_chi2, expected_p, expected_dof, _ = scipy_stats.chi2_contingency(table)

        result = engine.chi_square_test(frame, "species", "wide")
        assert result["statistic"] == pytest.approx(expected_chi2, rel=1e-6)
        assert result["p_value"] == pytest.approx(expected_p, rel=1e-6)
        assert result["degrees_of_freedom"] == expected_dof

    def test_cramers_v_formula(self, iris_frame):
        frame = iris_frame.copy()
        frame["wide"] = np.where(frame["sepal_width"] > 3.0, "yes", "no")
        result = engine.chi_square_test(frame, "species", "wide")

        n = result["n"]
        chi2 = result["statistic"]
        min_dim = min(result["table_shape"]) - 1
        expected_v = np.sqrt(chi2 / (n * min_dim))
        assert result["cramers_v"] == pytest.approx(expected_v, rel=1e-4)

    def test_independent_categories_not_significant(self):
        rng = np.random.default_rng(0)
        frame = pd.DataFrame({
            "a": rng.choice(["p", "q"], size=400),
            "b": rng.choice(["m", "n"], size=400),
        })
        result = engine.chi_square_test(frame, "a", "b")
        assert result["significant"] is False

    def test_low_expected_counts_warn(self):
        frame = pd.DataFrame({
            "a": ["x"] * 6 + ["y"] * 4,
            "b": ["p"] * 5 + ["q"] * 5,
        })
        result = engine.chi_square_test(frame, "a", "b")
        # Very small table should trigger the expected-count warning path.
        assert "expected_below_5" in result
        assert isinstance(result["warnings"], list)


class TestAnova:
    def test_matches_scipy_f_oneway(self, iris_frame):
        groups = [
            iris_frame.loc[iris_frame["species"] == s, "sepal_length"].to_numpy()
            for s in ("setosa", "versicolor", "virginica")
        ]
        expected_f, expected_p = scipy_stats.f_oneway(*groups)

        result = engine.one_way_anova(iris_frame, "sepal_length", "species")
        assert result["statistic"] == pytest.approx(expected_f, rel=1e-6)
        assert result["p_value"] == pytest.approx(expected_p, rel=1e-6)
        assert result["significant"] is True
        assert result["groups"] == 3

    def test_group_means_reported(self, iris_frame):
        result = engine.one_way_anova(iris_frame, "sepal_length", "species")
        assert result["group_means"]["setosa"] == pytest.approx(
            float(iris_frame.loc[iris_frame["species"] == "setosa", "sepal_length"].mean()),
            rel=1e-6,
        )


class TestConfidenceInterval:
    def test_interval_contains_mean(self, tiny_frame):
        result = engine.confidence_interval(tiny_frame, "x", 0.95)
        assert result["lower"] < result["mean"] < result["upper"]

    def test_matches_manual_t_interval(self, iris_frame):
        values = iris_frame["sepal_length"].to_numpy(dtype=float)
        n = len(values)
        mean = values.mean()
        se = values.std(ddof=1) / np.sqrt(n)
        t_crit = scipy_stats.t.ppf(0.975, df=n - 1)
        expected_lower = mean - t_crit * se
        expected_upper = mean + t_crit * se

        result = engine.confidence_interval(iris_frame, "sepal_length", 0.95)
        # Bounds are rounded to 4 decimals by contract.
        assert result["lower"] == pytest.approx(expected_lower, abs=1e-4)
        assert result["upper"] == pytest.approx(expected_upper, abs=1e-4)
        assert result["margin_of_error"] == pytest.approx(t_crit * se, abs=1e-4)

    def test_wider_interval_for_higher_confidence(self, iris_frame):
        ci_90 = engine.confidence_interval(iris_frame, "sepal_length", 0.90)
        ci_99 = engine.confidence_interval(iris_frame, "sepal_length", 0.99)
        width_90 = ci_90["upper"] - ci_90["lower"]
        width_99 = ci_99["upper"] - ci_99["lower"]
        assert width_99 > width_90

    def test_rejects_invalid_confidence(self, iris_frame):
        with pytest.raises(engine.StatsError):
            engine.confidence_interval(iris_frame, "sepal_length", 1.5)


class TestNormality:
    def test_skewed_data_not_normal(self):
        # An exponential sample is strongly right-skewed; Shapiro must reject it.
        rng = np.random.default_rng(3)
        frame = pd.DataFrame({"v": rng.exponential(2.0, 200)})
        result = engine.normality_test(frame, "v")
        assert result["normally_distributed"] is False

    def test_gaussian_data_passes(self):
        rng = np.random.default_rng(123)
        frame = pd.DataFrame({"v": rng.normal(0, 1, 500)})
        result = engine.normality_test(frame, "v")
        assert result["normally_distributed"] is True

    def test_matches_scipy_shapiro(self):
        rng = np.random.default_rng(7)
        values = rng.normal(5, 2, 60)
        frame = pd.DataFrame({"v": values})
        expected_w, expected_p = scipy_stats.shapiro(values)
        result = engine.normality_test(frame, "v")
        assert result["statistic"] == pytest.approx(expected_w, rel=1e-6)
        assert result["p_value"] == pytest.approx(expected_p, rel=1e-6)


class TestDescriptiveStatistics:
    def test_only_numeric_columns_included(self, sales_frame):
        result = engine.descriptive_statistics(sales_frame)
        names = [row["column"] for row in result["rows"]]
        assert "revenue" in names
        assert "region" not in names

    def test_values_match_pandas(self, iris_frame):
        result = engine.descriptive_statistics(iris_frame)
        row = next(r for r in result["rows"] if r["column"] == "sepal_width")
        series = iris_frame["sepal_width"]
        # Descriptive statistics are rounded to 4 decimals by contract.
        assert row["mean"] == pytest.approx(float(series.mean()), abs=1e-4)
        assert row["std"] == pytest.approx(float(series.std(ddof=1)), abs=1e-4)
        assert row["median"] == pytest.approx(float(series.median()), abs=1e-4)
