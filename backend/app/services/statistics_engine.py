"""Statistical analysis engine built on SciPy / NumPy.

Every result is computed from the actual dataframe. Each test returns the raw
statistic, p-value, a plain-language interpretation, the assumptions that must
hold, and the limitations of the test so results are never presented as more
certain than they are.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from ..utils.serialize import round_number, round_p_value, to_jsonable
from .type_inference import CATEGORICAL, NUMERIC, classify_all


class StatsError(Exception):
    """Raised when a requested test cannot be computed on the given columns."""


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").dropna()


def _significance(p_value: float, alpha: float) -> tuple[bool, str]:
    significant = bool(p_value < alpha)
    return significant, (
        f"p = {p_value:.6g} which is {'below' if significant else 'above'} "
        f"the alpha threshold of {alpha}. The result is "
        f"{'statistically significant' if significant else 'not statistically significant'}."
    )


def _correlation_strength(r: float) -> str:
    magnitude = abs(r)
    if magnitude < 0.1:
        label = "negligible"
    elif magnitude < 0.3:
        label = "weak"
    elif magnitude < 0.5:
        label = "moderate"
    elif magnitude < 0.7:
        label = "moderately strong"
    else:
        label = "strong"
    direction = "positive" if r >= 0 else "negative"
    return f"{label} {direction}"


def _resolve_pair(df: pd.DataFrame, x: str, y: str) -> tuple[pd.Series, pd.Series]:
    for column in (x, y):
        if column not in df.columns:
            raise StatsError(f"Column '{column}' does not exist in this dataset.")
    paired = df[[x, y]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(paired) < 3:
        raise StatsError(
            f"'{x}' and '{y}' only share {len(paired)} complete numeric rows; "
            "at least 3 are required."
        )
    return paired[x], paired[y]


def pearson_correlation(df: pd.DataFrame, x: str, y: str, alpha: float = 0.05) -> dict:
    a, b = _resolve_pair(df, x, y)
    r, p = stats.pearsonr(a, b)
    significant, sentence = _significance(float(p), alpha)
    return to_jsonable({
        "test": "pearson",
        "label": "Pearson correlation",
        "columns": [x, y],
        "n": int(len(a)),
        "statistic_name": "r",
        "statistic": round_number(r, 6),
        "p_value": round_p_value(p),
        "alpha": alpha,
        "significant": significant,
        "strength": _correlation_strength(float(r)),
        "r_squared": round_number(float(r) ** 2, 6),
        "interpretation": (
            f"Pearson r = {r:.4f} indicates a {_correlation_strength(float(r))} "
            f"linear relationship between '{x}' and '{y}' over {len(a)} observations. "
            f"The coefficient of determination (r²) is {float(r) ** 2:.4f}, meaning "
            f"{100 * float(r) ** 2:.1f}% of the variance is linearly shared. {sentence}"
        ),
        "assumptions": [
            "Both variables are continuous and measured on an interval/ratio scale.",
            "The relationship is linear.",
            "Observations are independent.",
            "Variables are approximately bivariate normal (Pearson is sensitive to outliers).",
        ],
        "limitations": [
            "Correlation does not imply causation.",
            "Pearson only detects linear association; a strong non-linear "
            "relationship can yield r ≈ 0.",
            "A single extreme outlier can substantially change r.",
        ],
    })


def spearman_correlation(df: pd.DataFrame, x: str, y: str, alpha: float = 0.05) -> dict:
    a, b = _resolve_pair(df, x, y)
    rho, p = stats.spearmanr(a, b)
    significant, sentence = _significance(float(p), alpha)
    return to_jsonable({
        "test": "spearman",
        "label": "Spearman rank correlation",
        "columns": [x, y],
        "n": int(len(a)),
        "statistic_name": "rho",
        "statistic": round_number(rho, 6),
        "p_value": round_p_value(p),
        "alpha": alpha,
        "significant": significant,
        "strength": _correlation_strength(float(rho)),
        "interpretation": (
            f"Spearman ρ = {rho:.4f} indicates a {_correlation_strength(float(rho))} "
            f"monotonic relationship between '{x}' and '{y}' over {len(a)} observations. "
            f"{sentence}"
        ),
        "assumptions": [
            "Variables are at least ordinal.",
            "Observations are independent.",
            "The relationship is monotonic (not necessarily linear).",
        ],
        "limitations": [
            "Rank-based, so it ignores the magnitude of differences between values.",
            "Correlation does not imply causation.",
            "Ties are handled by average ranking, which slightly reduces precision.",
        ],
    })


def correlation_matrix(df: pd.DataFrame, method: str = "pearson",
                       columns: list[str] | None = None) -> dict:
    kinds = classify_all(df)
    if columns:
        numeric_columns = [c for c in columns if c in df.columns and kinds.get(c) == NUMERIC]
        missing = [c for c in columns if c not in df.columns]
        if missing:
            raise StatsError(f"Unknown column(s): {missing}")
    else:
        numeric_columns = [c for c, k in kinds.items() if k == NUMERIC]

    if len(numeric_columns) < 2:
        raise StatsError(
            "A correlation matrix needs at least two numeric columns; "
            f"this dataset has {len(numeric_columns)}."
        )

    numeric_df = df[numeric_columns].apply(pd.to_numeric, errors="coerce")
    corr = numeric_df.corr(method=method)
    matrix = corr.round(4).fillna(0.0)

    pairs: list[dict[str, Any]] = []
    for i, col_a in enumerate(numeric_columns):
        for col_b in numeric_columns[i + 1:]:
            value = float(matrix.loc[col_a, col_b])
            pairs.append({
                "a": col_a,
                "b": col_b,
                "r": round_number(value, 4),
                "strength": _correlation_strength(value),
            })
    pairs.sort(key=lambda item: abs(item["r"] or 0), reverse=True)

    return to_jsonable({
        "method": method,
        "columns": numeric_columns,
        "matrix": matrix.to_dict(orient="index"),
        "pairs": pairs,
        "strongest": pairs[0] if pairs else None,
        "interpretation": (
            f"Computed pairwise {method} correlations across {len(numeric_columns)} "
            f"numeric columns using {int(numeric_df.notna().all(axis=1).sum())} "
            "complete rows."
        ),
        "limitations": [
            "Pairwise deletion means each cell uses a different subset of rows.",
            "Correlation measures linear (Pearson) or monotonic (Spearman) association only.",
            "Correlation does not imply causation.",
        ],
    })


def independent_ttest(df: pd.DataFrame, numeric_col: str, group_col: str,
                      group_a: str | None = None, group_b: str | None = None,
                      alpha: float = 0.05) -> dict:
    for column in (numeric_col, group_col):
        if column not in df.columns:
            raise StatsError(f"Column '{column}' does not exist in this dataset.")

    values = pd.to_numeric(df[numeric_col], errors="coerce")
    groups_series = df[group_col].astype(str)
    working = pd.DataFrame({"value": values, "group": groups_series}).dropna()

    unique_groups = list(working["group"].unique())
    if len(unique_groups) < 2:
        raise StatsError(
            f"Column '{group_col}' needs at least two distinct groups; found {len(unique_groups)}."
        )

    if group_a and group_b:
        if group_a not in unique_groups or group_b not in unique_groups:
            raise StatsError(
                f"Groups must be among {unique_groups[:20]}."
            )
        pair = (group_a, group_b)
    else:
        pair = (unique_groups[0], unique_groups[1])

    sample_a = working.loc[working["group"] == pair[0], "value"]
    sample_b = working.loc[working["group"] == pair[1], "value"]

    if len(sample_a) < 2 or len(sample_b) < 2:
        raise StatsError(
            f"Each group needs at least 2 observations; got {len(sample_a)} and {len(sample_b)}."
        )

    # Welch's t-test (does not assume equal variances) plus Levene for equality.
    t_stat, p_value = stats.ttest_ind(sample_a, sample_b, equal_var=False)
    levene_stat, levene_p = stats.levene(sample_a, sample_b)
    mean_a, mean_b = float(sample_a.mean()), float(sample_b.mean())
    significant, sentence = _significance(float(p_value), alpha)

    return to_jsonable({
        "test": "ttest_ind",
        "label": "Welch's independent two-sample t-test",
        "columns": [numeric_col, group_col],
        "groups": list(pair),
        "n": {"a": int(len(sample_a)), "b": int(len(sample_b))},
        "group_stats": {
            pair[0]: {
                "mean": round_number(mean_a),
                "std": round_number(sample_a.std(ddof=1)),
                "n": int(len(sample_a)),
            },
            pair[1]: {
                "mean": round_number(mean_b),
                "std": round_number(sample_b.std(ddof=1)),
                "n": int(len(sample_b)),
            },
        },
        "mean_difference": round_number(mean_a - mean_b),
        "statistic_name": "t",
        "statistic": round_number(t_stat, 6),
        "p_value": round_p_value(p_value),
        "alpha": alpha,
        "significant": significant,
        "levene": {
            "statistic": round_number(levene_stat, 6),
            "p_value": round_number(levene_p, 10),
            "equal_variances": bool(levene_p >= alpha),
        },
        "interpretation": (
            f"Mean of '{numeric_col}' for group '{pair[0]}' is {mean_a:.4f} "
            f"(n={len(sample_a)}) versus {mean_b:.4f} for '{pair[1]}' (n={len(sample_b)}). "
            f"Welch's t = {t_stat:.4f}, {sentence}"
        ),
        "assumptions": [
            "Observations are independent within and between groups.",
            "The numeric variable is continuous.",
            "Welch's variant relaxes the equal-variance assumption (Levene's test "
            "reported above shows whether variances differ).",
        ],
        "limitations": [
            "Groups are compared as two means only; additional groups are ignored.",
            "Sensitive to extreme outliers in small samples.",
            "A significant result indicates a difference in means, not its practical importance.",
        ],
    })


def paired_ttest(df: pd.DataFrame, col_a: str, col_b: str, alpha: float = 0.05) -> dict:
    for column in (col_a, col_b):
        if column not in df.columns:
            raise StatsError(f"Column '{column}' does not exist in this dataset.")

    paired = df[[col_a, col_b]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(paired) < 2:
        raise StatsError("Paired t-test needs at least 2 complete pairs.")

    t_stat, p_value = stats.ttest_rel(paired[col_a], paired[col_b])
    differences = paired[col_a] - paired[col_b]
    significant, sentence = _significance(float(p_value), alpha)

    return to_jsonable({
        "test": "ttest_rel",
        "label": "Paired two-sample t-test",
        "columns": [col_a, col_b],
        "n": int(len(paired)),
        "statistic_name": "t",
        "statistic": round_number(t_stat, 6),
        "p_value": round_p_value(p_value),
        "alpha": alpha,
        "significant": significant,
        "mean_difference": round_number(differences.mean()),
        "std_difference": round_number(differences.std(ddof=1)),
        "interpretation": (
            f"The mean paired difference ('{col_a}' − '{col_b}') is "
            f"{differences.mean():.4f} across {len(paired)} pairs. "
            f"t = {t_stat:.4f}, {sentence}"
        ),
        "assumptions": [
            "Each row pairs a measurement from the same subject/unit.",
            "The differences are approximately normally distributed.",
            "Observations are independent.",
        ],
        "limitations": [
            "Requires genuinely paired data; mispairing invalidates the test.",
            "Assumes the same measurement scale for both columns.",
        ],
    })


def one_sample_ttest(df: pd.DataFrame, column: str, popmean: float,
                     alpha: float = 0.05) -> dict:
    if column not in df.columns:
        raise StatsError(f"Column '{column}' does not exist in this dataset.")
    values = _numeric(df[column])
    if len(values) < 2:
        raise StatsError("One-sample t-test needs at least 2 observations.")

    t_stat, p_value = stats.ttest_1samp(values, popmean)
    significant, sentence = _significance(float(p_value), alpha)
    mean = float(values.mean())

    return to_jsonable({
        "test": "ttest_1samp",
        "label": "One-sample t-test",
        "columns": [column],
        "popmean": popmean,
        "n": int(len(values)),
        "sample_mean": round_number(mean),
        "statistic_name": "t",
        "statistic": round_number(t_stat, 6),
        "p_value": round_p_value(p_value),
        "alpha": alpha,
        "significant": significant,
        "interpretation": (
            f"Sample mean of '{column}' is {mean:.4f} (n={len(values)}), compared "
            f"with a hypothesised population mean of {popmean}. t = {t_stat:.4f}, {sentence}"
        ),
        "assumptions": [
            "Observations are independent.",
            "The variable is approximately normally distributed, or n is large (CLT).",
        ],
        "limitations": [
            "The hypothesised mean must be meaningful a priori.",
            "Sensitive to outliers when n is small.",
        ],
    })


def chi_square_test(df: pd.DataFrame, col_a: str, col_b: str,
                    alpha: float = 0.05) -> dict:
    for column in (col_a, col_b):
        if column not in df.columns:
            raise StatsError(f"Column '{column}' does not exist in this dataset.")

    working = df[[col_a, col_b]].dropna()
    if len(working) < 5:
        raise StatsError("Chi-square test needs at least 5 complete rows.")

    if col_a == col_b:
        raise StatsError(
            "A chi-square test of independence needs two different columns. "
            "Comparing a column with itself is always perfectly associated."
        )

    table = pd.crosstab(working[col_a], working[col_b])
    if table.shape[0] < 2 or table.shape[1] < 2:
        raise StatsError(
            "Each variable needs at least two categories to build a contingency table."
        )

    try:
        chi2, p_value, dof, expected = stats.chi2_contingency(table)
    except ValueError as exc:
        # SciPy raises when the table is degenerate (e.g. a perfect diagonal).
        raise StatsError(
            f"The contingency table is degenerate and chi-square is undefined "
            f"({exc}). The two columns are likely perfectly dependent."
        ) from exc
    significant, sentence = _significance(float(p_value), alpha)
    n = int(table.values.sum())
    min_dim = min(table.shape) - 1

    cramers_v = (
        float(np.sqrt(chi2 / (n * min_dim))) if n * min_dim > 0 else 0.0
    )
    low_expected = int((expected < 5).sum())
    total_cells = int(expected.size)

    warnings: list[str] = []
    if low_expected:
        warnings.append(
            f"{low_expected} of {total_cells} expected cell counts are below 5; "
            "the chi-square approximation may be unreliable."
        )

    return to_jsonable({
        "test": "chi_square",
        "label": "Chi-square test of independence",
        "columns": [col_a, col_b],
        "n": n,
        "degrees_of_freedom": int(dof),
        "table_shape": list(table.shape),
        "contingency_table": table.to_dict(orient="index"),
        "statistic_name": "chi2",
        "statistic": round_number(chi2, 6),
        "p_value": round_p_value(p_value),
        "alpha": alpha,
        "significant": significant,
        "cramers_v": round_number(cramers_v, 6),
        "association_strength": _correlation_strength(cramers_v),
        "expected_below_5": low_expected,
        "warnings": warnings,
        "interpretation": (
            f"Chi-square test of independence between '{col_a}' and '{col_b}' over "
            f"{n} observations: χ² = {chi2:.4f}, df = {dof}, {sentence} "
            f"Cramér's V = {cramers_v:.4f} indicates a "
            f"{_correlation_strength(cramers_v)} association."
        ),
        "assumptions": [
            "Observations are independent (each row counted once).",
            "Expected frequency in each cell should be ≥ 5 for the approximation.",
            "Categories are mutually exclusive and exhaustive.",
        ],
        "limitations": [
            "Detects any deviation from independence, not the direction of association.",
            "Chi-square is sensitive to large sample sizes: trivial differences can be significant.",
            "Cramér's V is a measure of association strength, not causation.",
        ],
    })


def one_way_anova(df: pd.DataFrame, numeric_col: str, group_col: str,
                  alpha: float = 0.05) -> dict:
    for column in (numeric_col, group_col):
        if column not in df.columns:
            raise StatsError(f"Column '{column}' does not exist in this dataset.")

    working = pd.DataFrame({
        "value": pd.to_numeric(df[numeric_col], errors="coerce"),
        "group": df[group_col].astype(str),
    }).dropna()

    grouped = [series.values for _, series in working.groupby("group")["value"]]
    grouped = [values for values in grouped if len(values) >= 2]
    if len(grouped) < 2:
        raise StatsError(
            "ANOVA needs at least two groups, each with at least 2 observations."
        )

    f_stat, p_value = stats.f_oneway(*grouped)
    significant, sentence = _significance(float(p_value), alpha)
    group_means = {
        str(name): round_number(values.mean())
        for name, values in working.groupby("group")["value"]
    }

    return to_jsonable({
        "test": "anova",
        "label": "One-way ANOVA",
        "columns": [numeric_col, group_col],
        "groups": len(grouped),
        "n": int(len(working)),
        "statistic_name": "F",
        "statistic": round_number(f_stat, 6),
        "p_value": round_p_value(p_value),
        "alpha": alpha,
        "significant": significant,
        "group_means": group_means,
        "interpretation": (
            f"One-way ANOVA comparing the mean of '{numeric_col}' across "
            f"{len(grouped)} groups of '{group_col}': F = {f_stat:.4f}, {sentence}"
        ),
        "assumptions": [
            "Observations are independent.",
            "The numeric variable is approximately normally distributed within groups.",
            "Groups have approximately equal variances (homoscedasticity).",
        ],
        "limitations": [
            "A significant F only says at least one mean differs — use post-hoc tests to find which.",
            "Sensitive to unequal variances when group sizes differ strongly.",
        ],
    })


def confidence_interval(df: pd.DataFrame, column: str, confidence: float = 0.95) -> dict:
    if column not in df.columns:
        raise StatsError(f"Column '{column}' does not exist in this dataset.")
    if not 0 < confidence < 1:
        raise StatsError("Confidence level must be between 0 and 1 (e.g. 0.95).")

    values = _numeric(df[column])
    n = len(values)
    if n < 2:
        raise StatsError("A confidence interval needs at least 2 observations.")

    mean = float(values.mean())
    std_err = float(values.std(ddof=1) / np.sqrt(n))
    # t-based interval is correct for unknown population variance.
    t_crit = float(stats.t.ppf((1 + confidence) / 2, df=n - 1))
    margin = t_crit * std_err
    lower, upper = mean - margin, mean + margin

    return to_jsonable({
        "label": f"{int(confidence * 100)}% confidence interval for the mean",
        "column": column,
        "confidence": confidence,
        "n": n,
        "mean": round_number(mean),
        "std": round_number(values.std(ddof=1)),
        "std_error": round_number(std_err),
        "t_critical": round_number(t_crit, 6),
        "margin_of_error": round_number(margin),
        "lower": round_number(lower),
        "upper": round_number(upper),
        "interpretation": (
            f"The mean of '{column}' is {mean:.4f} with a {int(confidence * 100)}% "
            f"confidence interval of [{lower:.4f}, {upper:.4f}] based on {n} "
            f"observations. If this sampling process were repeated, approximately "
            f"{int(confidence * 100)}% of the intervals constructed this way would "
            "contain the true population mean."
        ),
        "assumptions": [
            "Observations are independent and randomly sampled.",
            "The sampling distribution of the mean is approximately normal "
            "(guaranteed asymptotically by the Central Limit Theorem for large n).",
        ],
        "limitations": [
            "Describes the population mean only, not individual values.",
            "A 95% interval does not mean a 95% probability that this specific "
            "interval contains the true mean.",
        ],
    })


def descriptive_statistics(df: pd.DataFrame) -> dict:
    kinds = classify_all(df)
    rows = []
    for column, kind in kinds.items():
        if kind != NUMERIC:
            continue
        values = _numeric(df[column])
        if values.empty:
            continue
        rows.append({
            "column": column,
            "n": int(values.count()),
            "mean": round_number(values.mean()),
            "median": round_number(values.median()),
            "std": round_number(values.std(ddof=1)) if len(values) > 1 else None,
            "min": round_number(values.min()),
            "max": round_number(values.max()),
            "q1": round_number(values.quantile(0.25)),
            "q3": round_number(values.quantile(0.75)),
            "skewness": round_number(values.skew()) if len(values) > 2 else None,
        })
    return to_jsonable({
        "rows": rows,
        "numeric_columns": len(rows),
        "note": "Standard deviation uses the sample estimator (ddof=1).",
    })


def normality_test(df: pd.DataFrame, column: str) -> dict:
    """Shapiro-Wilk on a capped sample (the test degrades above ~5000 rows)."""
    if column not in df.columns:
        raise StatsError(f"Column '{column}' does not exist in this dataset.")
    values = _numeric(df[column])
    if len(values) < 3:
        raise StatsError("Normality testing needs at least 3 observations.")

    sample = values.sample(n=min(len(values), 5000), random_state=42) if len(values) > 5000 else values
    stat, p_value = stats.shapiro(sample)
    significant, sentence = _significance(float(p_value), 0.05)

    return to_jsonable({
        "test": "shapiro_wilk",
        "label": "Shapiro-Wilk normality test",
        "column": column,
        "n": int(len(sample)),
        "sampled": bool(len(values) > 5000),
        "statistic_name": "W",
        "statistic": round_number(stat, 6),
        "p_value": round_p_value(p_value),
        "normally_distributed": bool(p_value >= 0.05),
        "interpretation": (
            f"Shapiro-Wilk W = {stat:.4f}. {sentence} "
            + (
                "There is insufficient evidence to reject normality."
                if p_value >= 0.05
                else "The data deviate significantly from a normal distribution."
            )
        ),
        "assumptions": ["Observations are independent."],
        "limitations": [
            "With very large samples the test flags trivial deviations as significant.",
            "Failure to reject normality is not proof of normality.",
        ],
    })
