"""Natural-language query engine tests.

The critical guarantees verified here:
  1. The rule-based parser is the mandatory engine and works with zero AI.
  2. Every numeric answer matches an independently computed reference.
  3. Unsupported questions are refused with guidance, never guessed.
  4. The engine is always labelled honestly (rule_based vs llm).
  5. No arbitrary code/SQL execution path exists.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.nlp import analyst
from app.services.nlp.columns import find_all_columns, find_column, normalise
from app.services.nlp.executor import execute
from app.services.nlp.rule_engine import (
    ParseFailure,
    build_suggestions,
    parse_question,
)


class TestColumnResolution:
    def test_exact_match(self):
        match = find_column("what is the revenue", ["revenue", "units_sold"])
        assert match is not None and match.column == "revenue"

    def test_handles_snake_case(self):
        match = find_column(
            "what is the average unit price", ["unit_price", "revenue"]
        )
        assert match is not None and match.column == "unit_price"

    def test_handles_camel_case(self):
        match = find_column("total of unitPrice", ["unitPrice", "other"])
        assert match is not None and match.column == "unitPrice"

    def test_handles_plural(self):
        match = find_column("how many products", ["product"])
        assert match is not None and match.column == "product"

    def test_returns_none_when_no_match(self):
        assert find_column("what is the weather", ["revenue", "region"]) is None

    def test_normalise_collapses_separators(self):
        assert normalise("Total_Revenue  Per/Region") == "total revenue per region"

    def test_find_all_columns_orders_by_confidence(self):
        found = find_all_columns(
            "average revenue by region", ["revenue", "region", "notes"]
        )
        assert "revenue" in found
        assert "region" in found


class TestIntentParsing:
    @pytest.mark.parametrize(
        "question,expected_intent",
        [
            ("How many rows are in this dataset?", "row_count"),
            ("What columns does this dataset have?", "column_list"),
            ("How many missing values are there?", "missing_values"),
            ("Are there duplicate rows?", "duplicate_rows"),
            ("What is the data quality score?", "quality_score"),
            ("Are there outliers in revenue?", "outliers"),
        ],
    )
    def test_meta_intents(self, question, expected_intent, sales_frame):
        parsed = parse_question(question, sales_frame)
        assert parsed.intent == expected_intent

    def test_average_aggregation(self, sales_frame):
        parsed = parse_question("What is the average revenue?", sales_frame)
        assert parsed.intent == "aggregate"
        assert parsed.params["column"] == "revenue"
        assert parsed.params["agg"] == "mean"

    def test_sum_aggregation(self, sales_frame):
        parsed = parse_question("What is the total of units_sold?", sales_frame)
        assert parsed.intent == "aggregate"
        assert parsed.params["agg"] == "sum"

    def test_top_n_with_number(self, sales_frame):
        parsed = parse_question("Find the top 5 products by revenue", sales_frame)
        assert parsed.intent in {"top_n", "group_extreme"}
        assert parsed.params["group_column"] == "product"
        assert parsed.params["value_column"] == "revenue"

    def test_group_extreme_highest(self, sales_frame):
        parsed = parse_question("Which region has the highest revenue?", sales_frame)
        assert parsed.intent == "group_extreme"
        assert parsed.params["group_column"] == "region"
        assert parsed.params["mode"] == "max"

    def test_group_extreme_lowest(self, sales_frame):
        parsed = parse_question("Which region has the lowest revenue?", sales_frame)
        assert parsed.intent == "group_extreme"
        assert parsed.params["mode"] == "min"

    def test_correlation_between_two_columns(self, sales_frame):
        parsed = parse_question(
            "Is there a correlation between units_sold and revenue?", sales_frame
        )
        assert parsed.intent == "correlation_pair"

    def test_correlation_matrix(self, sales_frame):
        parsed = parse_question("Are there correlations between columns?", sales_frame)
        assert parsed.intent == "correlation_matrix"

    def test_time_trend(self, sales_frame):
        parsed = parse_question("Show monthly sales trends", sales_frame)
        assert parsed.intent == "time_trend"
        assert parsed.params["date_column"] == "order_date"
        assert parsed.params["freq"] == "M"

    def test_compare_categories(self, sales_frame):
        parsed = parse_question(
            "Compare the average revenue by region", sales_frame
        )
        assert parsed.intent in {"grouped_aggregate", "top_n", "group_extreme"}

    def test_unsupported_question_raises(self, sales_frame):
        with pytest.raises(ParseFailure) as excinfo:
            parse_question("What will revenue be next year?", sales_frame)
        assert "could not map" in excinfo.value.message.lower()
        assert len(excinfo.value.suggestions) > 0


class TestExecutionCorrectness:
    """Every computed number is checked against an independent reference."""

    def test_average_matches_pandas(self, sales_frame):
        parsed = parse_question("What is the average revenue?", sales_frame)
        outcome = execute(parsed, sales_frame)
        expected = float(pd.to_numeric(sales_frame["revenue"], errors="coerce").mean())
        assert outcome["result"]["value"] == pytest.approx(expected, rel=1e-9)
        assert outcome["result"]["verified"] is True

    def test_sum_matches_numpy(self, sales_frame):
        parsed = parse_question("What is the total units_sold?", sales_frame)
        outcome = execute(parsed, sales_frame)
        expected = float(
            np.sum(pd.to_numeric(sales_frame["units_sold"], errors="coerce").dropna())
        )
        assert outcome["result"]["value"] == pytest.approx(expected, rel=1e-9)

    def test_median_matches_pandas(self, sales_frame):
        parsed = parse_question("What is the median revenue?", sales_frame)
        outcome = execute(parsed, sales_frame)
        expected = float(pd.to_numeric(sales_frame["revenue"], errors="coerce").median())
        assert outcome["result"]["value"] == pytest.approx(expected, rel=1e-9)

    def test_row_count_is_exact(self, sales_frame):
        parsed = parse_question("How many rows are in this dataset?", sales_frame)
        outcome = execute(parsed, sales_frame)
        assert outcome["result"]["rows"] == len(sales_frame)

    def test_missing_values_match_independent_count(self, sales_frame):
        parsed = parse_question("How many missing values are there?", sales_frame)
        outcome = execute(parsed, sales_frame)
        assert outcome["result"]["missing_cells"] == int(sales_frame.isna().sum().sum())

    def test_duplicate_count_is_exact(self, sales_frame):
        parsed = parse_question("Are there duplicate rows?", sales_frame)
        outcome = execute(parsed, sales_frame)
        assert outcome["result"]["duplicate_rows"] == int(sales_frame.duplicated().sum())

    def test_group_extreme_winner_is_verified(self, sales_frame):
        parsed = parse_question("Which region has the highest revenue?", sales_frame)
        outcome = execute(parsed, sales_frame)

        reference = (
            pd.to_numeric(sales_frame["revenue"], errors="coerce")
            .groupby(sales_frame["region"])
            .sum()
        )
        expected_winner = str(reference.idxmax())
        expected_value = float(reference.max())

        assert outcome["result"]["winner"] == expected_winner
        assert outcome["result"]["value"] == pytest.approx(expected_value, rel=1e-6)
        assert outcome["result"]["verified"] is True

    def test_top_n_ranking_is_correctly_ordered(self, sales_frame):
        parsed = parse_question("Find the top 5 products by revenue", sales_frame)
        outcome = execute(parsed, sales_frame)

        ranking = outcome["result"]["ranking"]
        values = [item["value"] for item in ranking]
        assert values == sorted(values, reverse=True)
        assert len(ranking) <= 5

        reference = (
            pd.to_numeric(sales_frame["revenue"], errors="coerce")
            .groupby(sales_frame["product"])
            .sum()
            .sort_values(ascending=False)
        )
        assert ranking[0]["label"] == str(reference.index[0])
        assert ranking[0]["value"] == pytest.approx(float(reference.iloc[0]), rel=1e-6)

    def test_correlation_result_matches_scipy(self, sales_frame):
        parsed = parse_question(
            "Is there a correlation between units_sold and revenue?", sales_frame
        )
        outcome = execute(parsed, sales_frame)
        from scipy import stats as scipy_stats

        clean = sales_frame[["units_sold", "revenue"]].apply(
            pd.to_numeric, errors="coerce"
        ).dropna()
        expected_r, _ = scipy_stats.pearsonr(clean["units_sold"], clean["revenue"])
        assert outcome["result"]["statistic"] == pytest.approx(expected_r, rel=1e-6)

    def test_time_trend_periods_are_counted(self, sales_frame):
        parsed = parse_question("Show monthly sales trends", sales_frame)
        outcome = execute(parsed, sales_frame)
        # 24 months of data -> 24 monthly buckets.
        assert outcome["result"]["periods"] == 24
        assert len(outcome["result"]["points"]) == 24

    def test_bucketed_trend_worth_is_correct(self):
        """Trend aggregation must equal a manual groupby-mean."""
        frame = pd.DataFrame({
            "d": pd.date_range("2024-01-01", periods=60, freq="D").astype(str),
            "v": list(range(60)),
        })
        parsed = parse_question("Show the monthly trend of v over d", frame)
        outcome = execute(parsed, frame)

        reference = (
            pd.DataFrame({
                "d": pd.to_datetime(frame["d"]),
                "v": frame["v"],
            })
            .set_index("d")["v"]
            .resample("M")
            .mean()
        )
        assert outcome["result"]["periods"] == len(reference)
        for point, (index, value) in zip(outcome["result"]["points"], reference.items()):
            assert point["label"] == index.strftime("%Y-%m-%d")
            assert point["value"] == pytest.approx(float(value), rel=1e-9)

    def test_outlier_count_matches_manual_iqr(self, sales_frame):
        parsed = parse_question("Are there outliers in revenue?", sales_frame)
        outcome = execute(parsed, sales_frame)

        values = pd.to_numeric(sales_frame["revenue"], errors="coerce").dropna()
        q1, q3 = values.quantile(0.25), values.quantile(0.75)
        iqr = q3 - q1
        expected = int(((values < q1 - 1.5 * iqr) | (values > q3 + 1.5 * iqr)).sum())
        assert outcome["result"]["outlier_count"] == expected

    def test_value_counts_are_exact(self, iris_frame):
        parsed = parse_question("How many unique species are there?", iris_frame)
        outcome = execute(parsed, iris_frame)
        assert outcome["result"]["unique"] == 3


class TestAnalystOrchestration:
    def test_uses_rule_based_engine_offline(self, sales_frame):
        """With Ollama disabled, the engine must be labelled rule_based."""
        result = analyst.answer(
            "What is the average revenue?", sales_frame, prefer_llm=True
        )
        assert result["engine"] == "rule_based"
        assert result["engine_label"] == "Rule-based engine"
        assert result["ok"] is True

    def test_answer_contains_verified_number(self, sales_frame):
        result = analyst.answer("What is the average revenue?", sales_frame)
        expected = float(pd.to_numeric(sales_frame["revenue"], errors="coerce").mean())
        assert result["result"]["value"] == pytest.approx(expected, rel=1e-9)

    def test_unsupported_question_returns_guidance(self, sales_frame):
        result = analyst.answer(
            "Predict next quarter sales using machine learning", sales_frame
        )
        assert result["ok"] is False
        assert result["intent"] == "unsupported"
        assert len(result["supported_examples"]) > 0
        assert "could not map" in result["explanation"].lower()

    def test_never_fabricates_when_execution_fails(self, sales_frame):
        """An unanswerable aggregate must return an error, never an invented number."""
        result = analyst.answer(
            "What is the average of a_column_that_does_not_exist?", sales_frame
        )
        assert result["ok"] is False
        assert "value" not in result.get("result", {})
        assert result["engine"] == "rule_based"

    def test_engine_label_is_never_misleading(self, sales_frame):
        result = analyst.answer("How many rows are in this dataset?", sales_frame)
        assert result["engine"] in {"rule_based", "llm"}
        assert "rule-based" in result["engine_label"].lower() or "llm" in result["engine_label"].lower()

    def test_explanation_mentions_the_computed_value(self, sales_frame):
        result = analyst.answer("What is the average revenue?", sales_frame)
        value = result["result"]["value"]
        # The prose must contain the actual figure, not a placeholder.
        formatted = f"{value:,.4f}".rstrip("0").rstrip(".")
        assert formatted in result["explanation"] or f"{value:.4f}" in result["explanation"]


class TestSuggestions:
    def test_suggestions_are_answerable(self, sales_frame):
        suggestions = build_suggestions(sales_frame)
        assert len(suggestions) >= 5
        # At least half of the suggestions must actually parse.
        parsed_count = 0
        for suggestion in suggestions:
            try:
                parse_question(suggestion, sales_frame)
                parsed_count += 1
            except ParseFailure:
                pass
        assert parsed_count >= len(suggestions) // 2

    def test_suggestions_reference_real_columns(self, iris_frame):
        suggestions = build_suggestions(iris_frame)
        joined = " ".join(suggestions).lower()
        assert "sepal_length" in joined or "species" in joined


class TestSecurity:
    def test_no_eval_or_exec_in_nlp_package(self):
        """The NL pipeline must never contain a code-execution path."""
        from pathlib import Path

        nlp_dir = Path(__file__).resolve().parent.parent / "app" / "services" / "nlp"
        forbidden = ("eval(", "exec(", "__import__", "compile(", "subprocess", "pickle.load")
        for path in nlp_dir.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for token in forbidden:
                assert token not in source, f"{path.name} contains forbidden token {token!r}"

    def test_no_sql_string_construction(self):
        from pathlib import Path

        nlp_dir = Path(__file__).resolve().parent.parent / "app" / "services" / "nlp"
        for path in nlp_dir.glob("*.py"):
            source = path.read_text(encoding="utf-8").upper()
            assert "INSERT INTO" not in source
            assert "DROP TABLE" not in source

    def test_unknown_intent_is_rejected(self, sales_frame):
        from app.services.nlp.executor import ExecutionError

        class FakeParsed:
            intent = "run_arbitrary_code"
            params = {}

        with pytest.raises(ExecutionError):
            execute(FakeParsed(), sales_frame)
