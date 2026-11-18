
"""Rule-based natural-language query parser.

This is the mandatory engine. It works without AI services or internet.
It converts a question into a structured operation (intent + columns + params).
It never computes a number; the executor does that with pandas/numpy/scipy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..type_inference import CATEGORICAL, DATETIME, NUMERIC, TEXT, classify_all
from .columns import (
    categorical_columns,
    datetime_columns,
    find_all_columns,
    find_column,
    normalise,
    numeric_columns,
)


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

AGGREGATIONS: list[tuple[str, str]] = [
    ("standard deviation", "std"),
    ("std dev", "std"),
    ("stddev", "std"),
    ("std", "std"),
    ("variance", "var"),
    ("average", "mean"),
    ("avg", "mean"),
    ("mean", "mean"),
    ("median", "median"),
    ("total", "sum"),
    ("sum", "sum"),
    ("maximum", "max"),
    ("max", "max"),
    ("minimum", "min"),
    ("min", "min"),
    ("count", "count"),
    ("number of", "count"),
    ("how many", "count"),
]

SUPERLATIVE_HIGH = (
    "highest", "largest", "biggest", "most", "maximum", "max",
    "top", "best", "greatest", "leading", "strongest",
)

SUPERLATIVE_LOW = (
    "lowest", "smallest", "least", "minimum", "min",
    "worst", "weakest", "bottom",
)

TIME_HINTS = (
    "trend", "over time", "monthly", "by month", "per month",
    "yearly", "by year", "annual", "over the years",
    "time series", "quarterly", "by quarter", "weekly",
    "daily", "progression", "growth over",
)

FREQ_PATTERNS: list[tuple[str, str]] = [
    ("daily", "D"),
    ("day", "D"),
    ("weekly", "W"),
    ("week", "W"),
    ("monthly", "M"),
    ("month", "M"),
    ("quarterly", "Q"),
    ("quarter", "Q"),
    ("yearly", "Y"),
    ("annual", "Y"),
    ("year", "Y"),
]

CORRELATION_HINTS = (
    "correlations", "correlation", "correlate", "correlated",
    "correlates", "relationship between", "relationships",
    "relationship", "related", "associate", "association",
    "associations",
)

BUSINESS_LOW_HINTS = (
    "not selling properly",
    "isn't selling properly",
    "is not selling properly",
    "selling the least",
    "performing badly",
    "performing poorly",
    "underperforming",
    "not performing well",
    "doing the worst",
    "least performing",
)

BUSINESS_HIGH_HINTS = (
    "selling the most",
    "sold the most",
    "best selling",
    "best performing",
    "performing the best",
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ParsedQuery:
    """A structured, validated analytical operation."""

    intent: str
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    matched_phrases: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class ParseFailure(Exception):
    """Raised when the question cannot be mapped to a supported operation."""

    def __init__(
        self,
        message: str,
        suggestions: list[str] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.suggestions = suggestions or []


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------

def _detect_aggregation(text: str) -> tuple[str | None, str | None]:
    """Return (aggregation, matched phrase). Longest phrase wins."""

    for phrase, agg in AGGREGATIONS:
        pattern = rf"(?<!\w){re.escape(phrase)}(?!\w)"
        if re.search(pattern, text):
            return agg, phrase

    return None, None


def _detect_number(
    text: str,
    default: int | None = None,
) -> int | None:
    """Extract top 5, first 10, five, etc."""

    word_numbers = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
        "fifteen": 15,
        "twenty": 20,
        "fifty": 50,
    }

    match = (
        re.search(r"\btop\s+(\d+)\b", text)
        or re.search(r"\b(\d+)\s+(?:top|most|highest|best)\b", text)
    )

    if match:
        return int(match.group(1))

    match = re.search(r"\b(?:first|bottom|last)\s+(\d+)\b", text)

    if match:
        return int(match.group(1))

    match = re.search(r"\btop\s+([a-z]+)\b", text)

    if match and match.group(1) in word_numbers:
        return word_numbers[match.group(1)]

    match = re.search(
        r"\b(\d+)\s+(?:categories|rows|groups|records|items|products|regions)\b",
        text,
    )

    if match:
        return int(match.group(1))

    return default


def _detect_frequency(text: str) -> str:
    for phrase, freq in FREQ_PATTERNS:
        pattern = rf"(?<!\w){re.escape(phrase)}(?!\w)"
        if re.search(pattern, text):
            return freq

    return "M"


def _has_any(
    text: str,
    phrases: tuple[str, ...] | list[str],
) -> str | None:
    for phrase in phrases:
        pattern = rf"(?<!\w){re.escape(phrase)}(?!\w)"

        if re.search(pattern, text):
            return phrase

    return None


def _is_identifier(column: Any) -> bool:
    """Identify columns that should not be mistaken for business metrics."""

    name = normalise(str(column))
    return bool(
        re.search(
            r"\b(id|uuid|guid|code|index|postal|zip|phone)\b",
            name,
        )
    )


# ---------------------------------------------------------------------------
# Column selection helpers
# ---------------------------------------------------------------------------

def _pick_group_column(
    df: pd.DataFrame,
    question: str,
    exclude: list[str] | None = None,
) -> str | None:
    """Choose a categorical column using business meaning and user wording."""

    kinds = classify_all(df)
    exclude = exclude or []

    candidates = [
        column
        for column in categorical_columns(df, kinds)
        if column not in exclude
    ]

    if not candidates:
        return None

    mentioned = find_all_columns(question, candidates)

    if mentioned:
        return mentioned[0]

    q = normalise(question)

    entity_hints = {
        "customer": ("customer", "client", "buyer", "account"),
        "product": ("product", "item", "sku", "goods"),
        "category": ("category", "type", "class", "segment"),
        "region": (
            "region", "territory", "location", "area", "city", "country"
        ),
        "employee": (
            "employee", "staff", "salesperson", "sales person",
            "sales rep", "representative", "seller", "agent",
        ),
        "supplier": ("supplier", "vendor"),
        "store": ("store", "shop", "branch", "outlet"),
    }

    requested_entities = []

    if re.search(
        r"\b(who|seller|sellers|salesperson|salespeople|employee|staff)\b",
        q,
    ):
        requested_entities.append("employee")

    for entity, words in entity_hints.items():
        if entity == "employee" and entity in requested_entities:
            continue

        if any(
            re.search(
                rf"(?<!\w){re.escape(word)}(?:s|es)?(?!\w)",
                q,
            )
            for word in words
        ):
            requested_entities.append(entity)

    for entity in requested_entities:
        matches = []

        for column in candidates:
            name = normalise(str(column))

            if any(
                re.search(
                    rf"(?<!\w){re.escape(word)}(?:s|es)?(?!\w)",
                    name,
                )
                for word in entity_hints[entity]
            ):
                score = 2 if any(
                    word in name.split()
                    for word in ("name", "title", "label")
                ) else 1

                if re.search(r"\b(id|code|number)\b", name):
                    score -= 1

                matches.append((score, column))

        if matches:
            matches.sort(key=lambda item: item[0], reverse=True)
            return matches[0][1]

    usable = [
        column
        for column in candidates
        if not _is_identifier(column)
        and not re.search(
            r"\b(email|phone|postal|zip)\b",
            normalise(str(column)),
        )
    ]

    if not usable:
        usable = candidates

    usable.sort(
        key=lambda column: (
            abs(df[column].nunique(dropna=True) - 8),
            -df[column].nunique(dropna=True),
        )
    )

    return usable[0]


def _pick_numeric_column(
    df: pd.DataFrame,
    question: str,
    exclude: list[str] | None = None,
) -> str | None:
    """Select a relevant business metric without defaulting to ID columns."""

    kinds = classify_all(df)
    exclude = exclude or []

    candidates = [
        column
        for column in numeric_columns(df, kinds)
        if column not in exclude
    ]

    if not candidates:
        return None

    mentioned = find_all_columns(question, candidates)

    if mentioned:
        return mentioned[0]

    q = normalise(question)

    metric_hints = {
        "sales": ("sales", "revenue", "turnover", "income"),
        "revenue": ("revenue", "sales", "turnover", "income"),
        "profit": ("profit", "margin", "earnings"),
        "quantity": ("quantity", "units", "volume", "amount sold"),
        "price": ("price", "cost", "rate"),
        "rating": ("rating", "review", "score"),
    }

    requested = []

    for metric, words in metric_hints.items():
        if any(
            re.search(
                rf"(?<!\w){re.escape(word)}(?:s|es)?(?!\w)",
                q,
            )
            for word in words
        ):
            requested.append(metric)

    for metric in requested:
        for column in candidates:
            name = normalise(str(column))

            if any(
                re.search(
                    rf"(?<!\w){re.escape(word)}(?:s|es)?(?!\w)",
                    name,
                )
                for word in metric_hints[metric]
            ):
                return column

    preferred = [
        column for column in candidates
        if not _is_identifier(column)
        and not re.search(
            r"\b(year|number)\b",
            normalise(str(column)),
        )
    ]

    if len(preferred) == 1:
        return preferred[0]

    business_terms = (
        "sales", "revenue", "profit", "quantity", "amount",
        "price", "total", "value", "rating",
    )

    ranked = sorted(
        preferred,
        key=lambda column: sum(
            term in normalise(str(column)).split()
            for term in business_terms
        ),
        reverse=True,
    )

    if ranked and any(
        term in normalise(str(ranked[0])).split()
        for term in business_terms
    ):
        return ranked[0]

    return preferred[0] if len(preferred) == 1 else None


# ---------------------------------------------------------------------------
# Business-language interpretation
# ---------------------------------------------------------------------------

def _business_question(
    df: pd.DataFrame,
    text: str,
    columns: list[str],
    cat_cols: list[str],
    num_cols: list[str],
) -> ParsedQuery | None:
    """Interpret everyday business questions using actual dataset columns."""

    q = normalise(text)

    # Explicit top-N requests must be handled by the ranking parser.
    if re.search(
        r"\btop\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b",
        q,
    ):
        return None

    high_phrase = _has_any(q, SUPERLATIVE_HIGH)
    low_phrase = _has_any(q, SUPERLATIVE_LOW)

    business_low = _has_any(q, BUSINESS_LOW_HINTS)
    business_high = _has_any(q, BUSINESS_HIGH_HINTS)

    is_low = bool(
        low_phrase
        or business_low
        or re.search(r"\b(cheapest|cheaper|least expensive)\b", q)
    )
    is_high = bool(high_phrase or business_high)

    has_entity_question = bool(
        re.search(
            r"\b(who|where|which|what)\b.*\b"
            r"(sold|selling|sales|revenue|price|profit|perform|product|customer)\b",
            q,
        )
    )

    if not (is_low or is_high or has_entity_question):
        return None

    group_target = None

    entity_rules = [
        (
            r"\b(who|seller|sellers|salesperson|salespeople|employee|staff|sales rep)\b",
            (
                "salesperson", "sales person", "sales rep",
                "employee", "staff", "seller", "representative", "agent",
            ),
        ),
        (
            r"\b(where|region|area|location|city|country)\b",
            ("region", "territory", "location", "area", "city", "country"),
        ),
        (
            r"\b(product|products|item|items)\b",
            ("product", "item", "sku"),
        ),
        (
            r"\b(customer|customers|client|clients|buyer|buyers)\b",
            ("customer", "client", "buyer", "account"),
        ),
        (
            r"\b(category|categories|segment)\b",
            ("category", "segment", "class", "type"),
        ),
        (
            r"\b(store|stores|branch|branches|outlet)\b",
            ("store", "branch", "outlet", "shop"),
        ),
    ]

    for pattern, aliases in entity_rules:
        if re.search(pattern, q):
            matches = []

            for column in cat_cols:
                name = normalise(str(column))

                if any(
                    re.search(
                        rf"(?<!\w){re.escape(alias)}(?!\w)",
                        name,
                    )
                    for alias in aliases
                ):
                    score = 2 if any(
                        word in name.split()
                        for word in ("name", "title", "label")
                    ) else 1

                    if _is_identifier(column):
                        score -= 1

                    matches.append((score, column))

            if matches:
                matches.sort(key=lambda item: item[0], reverse=True)
                group_target = matches[0][1]
            else:
                raise ParseFailure(
                    "I understood which type of entity you mean, but "
                    "could not find a matching column in your dataset."
                )

            break

    if group_target is None:
        group_target = _pick_group_column(df, q)

    if not group_target:
        return None

    mentioned = find_all_columns(q, columns)

    numeric_target = next(
        (
            column for column in mentioned
            if column in num_cols
        ),
        None,
    )

    metric_rules = [
    (("price", "cheapest"), ("price", "unit price")),
    (("cost",), ("cost",)),
    (("profit", "profitable"), ("profit", "margin", "earnings")),
    (("revenue", "turnover"), ("revenue", "turnover", "sales", "income", "total")),
    (("sales", "sold", "selling"), ("sales", "revenue", "turnover", "income", "total")),
    (("quantity", "units", "volume"), ("quantity", "units", "volume")),
    (("rating", "score"), ("rating", "score")),
]

    requested_metric = None

    for phrases, aliases in metric_rules:
        if any(
            re.search(
                rf"(?<!\w){re.escape(phrase)}(?!\w)",
                q,
            )
            for phrase in phrases
        ):
            requested_metric = aliases
            break

    if numeric_target is None and requested_metric:
        metric_matches = []

        for column in num_cols:
            name = normalise(str(column))

            if any(
                re.search(
                    rf"(?<!\w){re.escape(alias)}(?!\w)",
                    name,
                )
                for alias in requested_metric
            ):
                metric_matches.append(column)

        if len(metric_matches) == 1:
            numeric_target = metric_matches[0]
        elif len(metric_matches) > 1:
            # Prefer the most specific matching metric name.
            metric_matches.sort(
                key=lambda column: len(normalise(str(column))),
            )
            numeric_target = metric_matches[0]

        if numeric_target is None:
            raise ParseFailure(
                "I could not find a numeric column matching that metric "
                "in your dataset."
            )

    if numeric_target is None:
        numeric_target = _pick_numeric_column(
            df,
            q,
            exclude=[group_target],
        )

    if not numeric_target:
        raise ParseFailure(
            "I found the category to compare, but could not identify "
            "a suitable numeric metric."
        )

    explicit_agg, _ = _detect_aggregation(q)

    if explicit_agg:
        agg = explicit_agg
    elif requested_metric and any(
        alias in requested_metric
        for alias in ("price", "cost", "rating", "score")
    ):
        agg = "mean"
    else:
        agg = "sum"

    return ParsedQuery(
        intent="group_extreme",
        params={
            "group_column": group_target,
            "value_column": numeric_target,
            "agg": agg,
            "mode": "min" if is_low else "max",
        },
        confidence=0.95,
        matched_phrases=["business question"],
        notes=[
            f"Compared {group_target} using {agg} of {numeric_target}."
        ],
    )


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_question(
    question: str,
    df: pd.DataFrame,
) -> ParsedQuery:
    """Convert a natural-language question into a validated operation."""

    raw = question.strip()
    text = normalise(raw)

    if not text:
        raise ParseFailure("The question is empty.")

    if df is None or df.empty:
        raise ParseFailure("The dataset is empty. Upload data first.")

    kinds = classify_all(df)

    columns = list(df.columns)
    num_cols = numeric_columns(df, kinds)
    cat_cols = categorical_columns(df, kinds)
    date_cols = datetime_columns(kinds)

    # ---- 1. Explicit meta questions -------------------------------------

    if _has_any(
        text,
        (
            "how many rows",
            "row count",
            "number of rows",
            "how many records",
            "how many observations",
            "dataset size",
            "how many entries",
            "shape of",
        ),
    ):
        return ParsedQuery(
            intent="row_count",
            params={},
            confidence=0.95,
            matched_phrases=["row count"],
        )

    if _has_any(
        text,
        (
            "how many columns",
            "number of columns",
            "column count",
            "what columns",
            "which columns",
            "list columns",
            "show columns",
            "what fields",
            "what are the columns",
        ),
    ):
        return ParsedQuery(
            intent="column_list",
            params={"columns": columns},
            confidence=0.95,
            matched_phrases=["column listing"],
        )

    missing_phrase = _has_any(
        text,
        (
            "missing value",
            "missing values",
            "how many missing",
            "null value",
            "nulls",
            "nan",
            "blank cells",
            "empty cells",
            "incomplete",
            "missing data",
            "how much data is missing",
        ),
    )

    if missing_phrase:
        column_match = find_column(text, columns)
        target = column_match.column if column_match else None

        return ParsedQuery(
            intent="missing_values",
            params={"column": target},
            confidence=0.9 if target else 0.8,
            matched_phrases=[missing_phrase],
        )

    if _has_any(
        text,
        (
            "duplicate",
            "duplicates",
            "duplicated rows",
            "repeated rows",
        ),
    ):
        return ParsedQuery(
            intent="duplicate_rows",
            params={},
            confidence=0.9,
            matched_phrases=["duplicates"],
        )

    if _has_any(
        text,
        (
            "data quality",
            "quality score",
            "how clean",
            "data health",
        ),
    ):
        return ParsedQuery(
            intent="quality_score",
            params={},
            confidence=0.95,
            matched_phrases=["quality"],
        )

    # ---- Outliers -------------------------------------------------------

    outlier_phrase = _has_any(
        text,
        (
            "outlier",
            "outliers",
            "anomal",
            "extreme value",
            "unusual value",
        ),
    )

    if outlier_phrase:
        column_match = find_column(text, num_cols)

        return ParsedQuery(
            intent="outliers",
            params={
                "column": column_match.column if column_match else None
            },
            confidence=0.85,
            matched_phrases=[outlier_phrase],
        )

    # ---- Unique values --------------------------------------------------

    unique_phrase = _has_any(
        text,
        (
            "unique value",
            "distinct value",
            "how many unique",
            "number of unique",
            "distinct categories",
            "unique categories",
            "how many different",
        ),
    )

    if unique_phrase:
        column_match = find_column(text, columns)

        if not column_match:
            raise ParseFailure(
                "I could not tell which column you want unique values for. "
                "Try naming the column, e.g. "
                "'how many unique values are in region?'."
            )

        return ParsedQuery(
            intent="unique_count",
            params={"column": column_match.column},
            confidence=0.9,
            matched_phrases=[unique_phrase],
        )

    # ---- 2. Distribution / summary -------------------------------------

    if _has_any(
        text,
        (
            "distribution",
            "histogram",
            "spread of",
            "how is",
            "summarize",
            "summarise",
            "describe",
            "summary of",
            "summary statistics",
        ),
    ):
        column_match = find_column(text, columns)

        if column_match:
            return ParsedQuery(
                intent="describe_column",
                params={"column": column_match.column},
                confidence=0.85,
                matched_phrases=["distribution"],
            )

        return ParsedQuery(
            intent="dataset_summary",
            params={},
            confidence=0.85,
            matched_phrases=["summary"],
        )

    # ---- 3. Correlation -------------------------------------------------

    corr_phrase = _has_any(text, CORRELATION_HINTS)

    if corr_phrase:
        mentioned = [
            column
            for column in find_all_columns(text, columns)
            if kinds.get(column) == NUMERIC
        ]

        if len(mentioned) >= 2:
            return ParsedQuery(
                intent="correlation_pair",
                params={
                    "x": mentioned[0],
                    "y": mentioned[1],
                    "method": "pearson",
                },
                confidence=0.95,
                matched_phrases=[corr_phrase],
            )

        if len(num_cols) < 2:
            raise ParseFailure(
                "A correlation needs at least two numeric columns, "
                f"but this dataset has {len(num_cols)}."
            )

        return ParsedQuery(
            intent="correlation_matrix",
            params={"method": "pearson"},
            confidence=0.9,
            matched_phrases=[corr_phrase],
        )

    # ---- 4. Statistical tests ------------------------------------------

    if _has_any(
        text,
        (
            "t-test",
            "ttest",
            "t test",
            "significant difference",
            "statistically significant",
            "is there a difference",
            "difference between",
        ),
    ):
        mentioned = find_all_columns(text, columns)

        numeric_target = next(
            (
                column for column in mentioned
                if kinds.get(column) == NUMERIC
            ),
            None,
        )

        group_target = next(
            (
                column for column in mentioned
                if column in cat_cols and column != numeric_target
            ),
            None,
        )

        if numeric_target is None:
            numeric_target = _pick_numeric_column(df, text)

        if group_target is None:
            group_target = _pick_group_column(
                df,
                text,
                exclude=[numeric_target] if numeric_target else [],
            )

        if numeric_target and group_target:
            return ParsedQuery(
                intent="ttest",
                params={
                    "numeric_column": numeric_target,
                    "group_column": group_target,
                },
                confidence=0.85,
                matched_phrases=["t-test"],
            )

        raise ParseFailure(
            "A t-test needs a numeric column and a categorical "
            "column with two groups."
        )

    if _has_any(
        text,
        (
            "chi-square",
            "chi square",
            "chi2",
            "independence between",
            "association between",
        ),
    ):
        mentioned = [
            column
            for column in find_all_columns(text, columns)
            if column in cat_cols
        ]

        if len(mentioned) >= 2:
            return ParsedQuery(
                intent="chi_square",
                params={
                    "x": mentioned[0],
                    "y": mentioned[1],
                },
                confidence=0.9,
                matched_phrases=["chi-square"],
            )

        raise ParseFailure(
            "A chi-square test needs two categorical columns. "
            "Please mention both columns."
        )

    # ---- 5. Time trends -------------------------------------------------

    time_phrase = _has_any(text, TIME_HINTS)

    if time_phrase or (
        date_cols and _has_any(text, ("trend", "over time", "growth"))
    ):
        if not date_cols:
            raise ParseFailure(
                "I could not find a date/time column in this dataset, "
                "so a trend analysis is not possible."
            )

        date_match = find_column(text, date_cols)
        date_column = date_match.column if date_match else date_cols[0]

        value_column = _pick_numeric_column(
            df,
            text,
            exclude=[date_column],
        )

        return ParsedQuery(
            intent="time_trend",
            params={
                "date_column": date_column,
                "value_column": value_column,
                "freq": _detect_frequency(text),
            },
            confidence=0.9 if value_column else 0.8,
            matched_phrases=[time_phrase or "trend"],
        )

    # ---- 6. Business-language questions --------------------------------

       # ---- 6. Business-language questions --------------------------------

    business_query = _business_question(
        df,
        text,
        columns,
        cat_cols,
        num_cols,
    )

    if business_query is not None:
        return business_query
    # ---- 7. Ranking / top-N --------------------------------------------

    agg, agg_phrase = _detect_aggregation(text)
    top_n = _detect_number(text)

    superlative_high = _has_any(text, SUPERLATIVE_HIGH)
    superlative_low = _has_any(text, SUPERLATIVE_LOW)

    ranking_words = _has_any(
        text,
        (
            "top",
            "ranking",
            "rank",
            "compare",
            "breakdown",
            "by",
            "per",
            "group by",
            "across",
        ),
    )

    if superlative_high or superlative_low or (
        top_n and ranking_words
    ):
        mentioned = find_all_columns(text, columns)

        numeric_target = next(
            (
                column for column in mentioned
                if kinds.get(column) == NUMERIC
            ),
            None,
        )

        group_target = next(
            (
                column for column in mentioned
                if column in cat_cols and column != numeric_target
            ),
            None,
        )

        if numeric_target is None:
            numeric_target = _pick_numeric_column(df, text)

        if group_target is None:
            group_target = _pick_group_column(
                df,
                text,
                exclude=[numeric_target] if numeric_target else [],
            )

        if numeric_target and group_target:
            direction = "asc" if superlative_low else "desc"

            if top_n and top_n > 1:
                return ParsedQuery(
                    intent="top_n",
                    params={
                        "group_column": group_target,
                        "value_column": numeric_target,
                        "agg": agg or "sum",
                        "n": top_n,
                        "order": direction,
                        "chart_type": (
                            "pie"
                            if _has_any(text, ("pie chart", "pie graph", "as a pie"))
                            else "bar"
                        ),
                    },
                    confidence=0.95,
                    matched_phrases=[
                        phrase
                        for phrase in (
                            superlative_high,
                            superlative_low,
                            agg_phrase,
                        )
                        if phrase
                    ],
                )

            return ParsedQuery(
                intent="group_extreme",
                params={
                    "group_column": group_target,
                    "value_column": numeric_target,
                    "agg": agg or "sum",
                    "mode": "min" if superlative_low else "max",
                },
                confidence=0.95,
                matched_phrases=[
                    phrase
                    for phrase in (
                        superlative_high,
                        superlative_low,
                        agg_phrase,
                    )
                    if phrase
                ],
            )

        if numeric_target:
            return ParsedQuery(
                intent="aggregate",
                params={
                    "column": numeric_target,
                    "agg": agg or (
                        "min" if superlative_low else "max"
                    ),
                },
                confidence=0.7,
                matched_phrases=[
                    phrase
                    for phrase in (superlative_high, superlative_low, agg_phrase)
                    if phrase
                ],
                notes=[
                    "No suitable categorical column was found to group by."
                ],
            )

    # ---- 8. Group comparison -------------------------------------------

    compare_phrase = _has_any(
        text,
        (
            "compare",
            "comparison",
            "versus",
            "vs",
            "breakdown",
            "split by",
            "grouped by",
            "by category",
            "per category",
        ),
    )

    if compare_phrase and (agg or ranking_words):
        mentioned = find_all_columns(text, columns)

        numeric_target = next(
            (
                column for column in mentioned
                if kinds.get(column) == NUMERIC
            ),
            None,
        )

        group_target = next(
            (
                column for column in mentioned
                if column in cat_cols and column != numeric_target
            ),
            None,
        )

        if numeric_target is None:
            numeric_target = _pick_numeric_column(df, text)

        if group_target is None:
            group_target = _pick_group_column(
                df,
                text,
                exclude=[numeric_target] if numeric_target else [],
            )

        if numeric_target and group_target:
            return ParsedQuery(
                intent="grouped_aggregate",
                params={
                    "group_column": group_target,
                    "value_column": numeric_target,
                    "agg": agg or "mean",
                    "n": top_n or 10,
                },
                confidence=0.9,
                matched_phrases=[compare_phrase],
            )

    # ---- 9. Plain scalar / grouped aggregate ---------------------------

    if agg:
        mentioned = find_all_columns(text, columns)

        explicit_numeric = next(
            (
                column for column in mentioned
                if kinds.get(column) == NUMERIC
            ),
            None,
        )

        explicit_group = next(
            (
                column for column in mentioned
                if column in cat_cols
            ),
            None,
        )

        if (
            agg != "count"
            and explicit_group
            and (explicit_numeric or _pick_numeric_column(df, text))
        ):
            numeric_target = (
                explicit_numeric
                or _pick_numeric_column(df, text)
            )

            if numeric_target:
                return ParsedQuery(
                    intent="grouped_aggregate",
                    params={
                        "group_column": explicit_group,
                        "value_column": numeric_target,
                        "agg": agg,
                        "n": top_n or 10,
                    },
                    confidence=0.9,
                    matched_phrases=[agg_phrase or agg],
                )

        column_match = find_column(text, columns)

        if column_match:
            column = column_match.column
            kind = kinds.get(column)

            if agg in ("mean", "median", "std", "var", "sum") and (
                kind != NUMERIC
            ):
                group_target = _pick_group_column(
                    df,
                    text,
                    exclude=[column],
                )

                numeric_target = _pick_numeric_column(
                    df,
                    text,
                    exclude=[column],
                )

                if numeric_target and group_target:
                    return ParsedQuery(
                        intent="grouped_aggregate",
                        params={
                            "group_column": group_target,
                            "value_column": numeric_target,
                            "agg": agg,
                            "n": top_n or 10,
                        },
                        confidence=0.75,
                        matched_phrases=[agg_phrase or agg],
                    )

                raise ParseFailure(
                    f"'{column}' is not a numeric column, so a {agg} "
                    "cannot be computed on it."
                )

            if agg == "count":
                return ParsedQuery(
                    intent="value_counts",
                    params={
                        "column": column,
                        "n": top_n or 10,
                    },
                    confidence=0.85,
                    matched_phrases=[agg_phrase or "count"],
                )

            return ParsedQuery(
                intent="aggregate",
                params={
                    "column": column,
                    "agg": agg,
                },
                confidence=0.95,
                matched_phrases=[agg_phrase or agg],
            )

        # No explicit column: infer a numeric business metric.
        # Do not silently substitute another column when the user
        # explicitly requested a column that does not exist.

        explicit_target_match = re.search(
            r"\b(?:of|for|in|on)\s+(.+?)(?:\s+by\s+|\s+per\s+|$)",
            text,
        )

        if explicit_target_match:
            requested_target = explicit_target_match.group(1).strip()

            known_generic_terms = {
                "it",
                "this",
                "that",
                "all",
                "everything",
                "the data",
                "data",
                "records",
                "values",
            }

            if requested_target not in known_generic_terms:
                raise ParseFailure(
                    f"I couldn't find a column matching "
                    f"'{requested_target}'. Please check the column name."
                )

        numeric_target = _pick_numeric_column(df, text)

        if numeric_target:
            return ParsedQuery(
                intent="aggregate",
                params={
                    "column": numeric_target,
                    "agg": agg,
                },
                confidence=0.75,
                matched_phrases=[agg_phrase or agg],
                notes=[
                    f"No column was named; inferred '{numeric_target}' "
                    "from the question."
                ],
            )

        raise ParseFailure(
            f"I understood the {agg} operation but could not identify "
            "a suitable numeric column.",
            suggestions=[
                f"What is the {agg} of {column}?"
                for column in num_cols[:3]
            ],
        )

    # ---- 10. Bare categorical question ---------------------------------

    column_match = find_column(text, cat_cols)

    if column_match and _has_any(
        text,
        (
            "show",
            "list",
            "what",
            "which",
            "distribution of",
        ),
    ):
        return ParsedQuery(
            intent="value_counts",
            params={
                "column": column_match.column,
                "n": top_n or 10,
            },
            confidence=0.7,
            matched_phrases=["value counts"],
        )

    # ---- Unsupported question ------------------------------------------

    raise ParseFailure(
        "I could not map that question to a supported operation. "
        "I only answer questions I can compute from your actual data â€” "
        "I will not guess.",
        suggestions=build_suggestions(df),
    )


# ---------------------------------------------------------------------------
# Suggested questions
# ---------------------------------------------------------------------------

def build_suggestions(df: pd.DataFrame) -> list[str]:
    """Generate useful example questions using meaningful dataset columns."""

    kinds = classify_all(df)
    all_numeric = numeric_columns(df, kinds)

    num_cols = [
        column for column in all_numeric
        if not _is_identifier(column)
        and not re.search(
            r"\b(year|number)\b",
            normalise(str(column)),
        )
    ]

    cat_cols = [
        column for column in categorical_columns(df, kinds)
        if not _is_identifier(column)
    ]

    date_cols = datetime_columns(kinds)

    suggestions: list[str] = []

    if num_cols:
        suggestions.append(f"What is the average {num_cols[0]}?")

    if num_cols and cat_cols:
        suggestions.append(
            f"Which {cat_cols[0]} has the highest {num_cols[0]}?"
        )
        suggestions.append(
            f"Compare the average {num_cols[0]} by {cat_cols[0]}."
        )

    if cat_cols:
        suggestions.append(f"Find the top 5 {cat_cols[0]} by count.")

    if len(num_cols) >= 2:
        suggestions.append(
            f"Is there a correlation between {num_cols[0]} and {num_cols[1]}?"
        )

    if date_cols:
        if num_cols:
            suggestions.append(
                f"Show the monthly trend of {num_cols[0]} over {date_cols[0]}."
            )
        else:
            suggestions.append(
                f"Show monthly trends over {date_cols[0]}."
            )

    suggestions.append("How many missing values are there?")
    suggestions.append("How many rows are in this dataset?")

    if num_cols:
        suggestions.append(f"Are there outliers in {num_cols[0]}?")

    return suggestions[:8]
