"""Column resolution for natural-language queries, including typo tolerance."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from dataclasses import dataclass

import pandas as pd


def normalise(text: str) -> str:
    lowered = str(text).lower()
    lowered = re.sub(r"[_\-/]+", " ", lowered)
    lowered = re.sub(r"[^\w\s%]", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _tokens(text: str) -> set[str]:
    return {token for token in normalise(text).split() if token}


def _stem(token: str) -> str:
    if len(token) > 3 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith(("sses", "shes", "ches", "xes")):
        return token[:-2]
    if len(token) > 2 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _stem_tokens(text: str) -> set[str]:
    return {_stem(token) for token in _tokens(text)}


def _fuzzy_phrase_score(question: str, column: str) -> float:
    """Match individual words to tolerate small spelling mistakes."""
    question_words = normalise(question).split()
    column_words = normalise(column).split()

    best = 0.0
    for target in column_words:
        if len(target) < 4:
            continue
        for word in question_words:
            if len(word) < 4:
                continue
            best = max(best, SequenceMatcher(None, word, target).ratio())

    return best

@dataclass
class ColumnMatch:
    column: str
    score: float
    matched_on: str


def find_column(question: str, columns: list[str]) -> ColumnMatch | None:
    """Find a confidently mentioned column, including minor spelling errors."""
    question_norm = normalise(question)
    question_tokens = _tokens(question)
    question_stems = _stem_tokens(question)

    best: ColumnMatch | None = None

    for column in columns:
        column_norm = normalise(column)
        column_tokens = _tokens(column)

        if not column_tokens:
            continue

        score = 0.0
        matched_on = "exact"

        if re.search(rf"(?<!\w){re.escape(column_norm)}(?!\w)", question_norm):
            score = 100.0 + len(column_norm)

        else:
            overlap = column_tokens & question_tokens

            if overlap:
                coverage = len(overlap) / len(column_tokens)
                score = 50.0 * coverage + sum(len(t) for t in overlap) * 0.5
                matched_on = "token"

            else:
                stem_overlap = {_stem(t) for t in column_tokens} & question_stems

                if stem_overlap:
                    coverage = len(stem_overlap) / len(column_tokens)
                    score = 50.0 * coverage + sum(len(t) for t in stem_overlap) * 0.5
                    matched_on = "plural"

                else:
                    # Avoid fuzzy matching very short names such as ID, age or no.
                    if len(column_norm) >= 4:
                        similarity = _fuzzy_phrase_score(question_norm, column_norm)

                        if similarity >= 0.84:
                            score = 30.0 + similarity * 10
                            matched_on = "fuzzy"

        if score > 0 and (best is None or score > best.score):
            best = ColumnMatch(
                column=column,
                score=score,
                matched_on=matched_on,
            )

    if best is None or best.score < 25.0:
        return None

    return best


def find_all_columns(question: str, columns: list[str]) -> list[str]:
    """Return explicitly mentioned columns, ordered by confidence."""
    question_norm = normalise(question)
    question_stems = _stem_tokens(question)
    matches: list[tuple[str, float]] = []

    for column in columns:
        column_norm = normalise(column)

        if not column_norm:
            continue

        compact_question = re.sub(r"[^a-z0-9]", "", question_norm)
        compact_column = re.sub(r"[^a-z0-9]", "", column_norm)

        if (
            re.search(rf"(?<!\w){re.escape(column_norm)}(?!\w)", question_norm)
            or (
                compact_column
                and compact_column in compact_question
            )
        ):
            matches.append((column, 110.0 + len(column_norm)))
        else:
            column_stems = {_stem(t) for t in _tokens(column)}

            if column_stems and column_stems <= question_stems:
                matches.append((column, 40.0 + len(column_norm)))

    matches.sort(key=lambda item: item[1], reverse=True)
    return [column for column, _ in matches]


def numeric_columns(df: pd.DataFrame, kinds: dict[str, str]) -> list[str]:
    from ..type_inference import NUMERIC
    return [c for c, k in kinds.items() if k == NUMERIC]


def categorical_columns(df: pd.DataFrame, kinds: dict[str, str]) -> list[str]:
    from ..type_inference import CATEGORICAL, TEXT

    return [
        c for c, k in kinds.items()
        if k in (CATEGORICAL, TEXT) and 1 < df[c].nunique(dropna=True) <= 200
    ]


def datetime_columns(kinds: dict[str, str]) -> list[str]:
    from ..type_inference import DATETIME
    return [c for c, k in kinds.items() if k == DATETIME]


