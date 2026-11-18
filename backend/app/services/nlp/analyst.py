"""Natural-language analytics orchestrator.

Pipeline (identical for both engines):

    question
      -> intent identification   (Ollama first if available, else rule-based)
      -> column identification   (validated against the real schema)
      -> validated operation     (whitelist of supported intents only)
      -> pandas / numpy / scipy computation
      -> verified numerical result
      -> plain-language explanation

The LLM never calculates. No generated code or SQL is ever executed.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from ...utils.serialize import to_jsonable
from ..type_inference import classify_all
from . import ollama_client
from .executor import ExecutionError, execute
from .rule_engine import ParseFailure, ParsedQuery, build_suggestions, parse_question

# Intents the executor can run. Anything outside this set is rejected, which
# means no model output can reach arbitrary code paths.
ALLOWED_INTENTS = {
    "row_count", "column_list", "missing_values", "duplicate_rows",
    "quality_score", "outliers", "unique_count", "describe_column",
    "dataset_summary", "correlation_pair", "correlation_matrix", "ttest",
    "chi_square", "time_trend", "top_n", "group_extreme", "grouped_aggregate",
    "value_counts", "aggregate",
}

_ENGINE_LABELS = {
    "llm": "Local LLM (Ollama)",
    "rule_based": "Rule-based engine",
    "system": "System",
}


def _schema(df: pd.DataFrame) -> list[dict[str, str]]:
    kinds = classify_all(df)
    return [{"name": str(c), "kind": kinds[c]} for c in df.columns]


def _validate_llm_operation(operation: dict[str, Any], df: pd.DataFrame) -> ParsedQuery | None:
    """Accept a model-proposed operation only if it is fully valid for this data."""
    if not isinstance(operation, dict):
        return None

    intent = operation.get("intent")
    if intent == "unsupported" or intent not in ALLOWED_INTENTS:
        return None

    columns = set(str(c) for c in df.columns)
    kinds = classify_all(df)
    numeric = {c for c, k in kinds.items() if k == "numeric"}
    params: dict[str, Any] = {}

    def column_param(key: str, required: bool = True,
                     must_be_numeric: bool = False) -> bool:
        value = operation.get(key)
        if value in (None, "", "null"):
            return not required
        if str(value) not in columns:
            return False
        if must_be_numeric and str(value) not in numeric:
            return False
        params[key] = str(value)
        return True

    try:
        if intent == "aggregate":
            if not column_param("column", must_be_numeric=True):
                return None
            agg = str(operation.get("agg", "mean")).lower()
            if agg not in {"mean", "sum", "median", "min", "max", "std", "count"}:
                return None
            params["agg"] = agg
        elif intent in {"grouped_aggregate", "group_extreme", "top_n"}:
            if not column_param("group_column"):
                return None
            if not column_param("value_column", must_be_numeric=True):
                return None
            agg = str(operation.get("agg", "mean")).lower()
            if agg not in {"mean", "sum", "median", "count", "min", "max"}:
                return None
            params["agg"] = agg
            if intent in {"grouped_aggregate", "top_n"}:
                try:
                    params["n"] = max(1, min(int(operation.get("n", 10)), 50))
                except (TypeError, ValueError):
                    params["n"] = 10
            if intent == "top_n":
                params["order"] = "asc" if str(operation.get("order", "desc")).lower() == "asc" else "desc"
            if intent == "group_extreme":
                params["mode"] = "min" if str(operation.get("mode", "max")).lower() == "min" else "max"
        elif intent == "value_counts":
            if not column_param("column"):
                return None
            try:
                params["n"] = max(1, min(int(operation.get("n", 10)), 50))
            except (TypeError, ValueError):
                params["n"] = 10
        elif intent in {"correlation_pair", "chi_square"}:
            if intent == "correlation_pair":
                if not column_param("x", must_be_numeric=True):
                    return None
                if not column_param("y", must_be_numeric=True):
                    return None
                params["method"] = "pearson"
            else:
                if not column_param("x") or not column_param("y"):
                    return None
        elif intent == "ttest":
            if not column_param("numeric_column", must_be_numeric=True):
                return None
            if not column_param("group_column"):
                return None
        elif intent == "time_trend":
            if not column_param("date_column"):
                return None
            if not column_param("value_column", required=False, must_be_numeric=True):
                return None
            freq = str(operation.get("freq", "M")).upper()
            params["freq"] = freq if freq in {"D", "W", "M", "Q", "Y"} else "M"
        elif intent in {"describe_column", "unique_count", "outliers"}:
            if not column_param("column", required=(intent != "outliers"),
                                must_be_numeric=(intent == "outliers")):
                return None
        elif intent == "missing_values":
            if not column_param("column", required=False):
                return None
        elif intent == "correlation_matrix":
            params["method"] = "pearson"
        # The remaining zero-parameter intents need nothing further.
    except (TypeError, ValueError):
        return None

    return ParsedQuery(
        intent=intent,
        params=params,
        confidence=0.9,
        matched_phrases=["local LLM intent"],
        notes=[f"Interpreted by {operation.get('_model', 'Ollama')}; "
               "numbers computed by the analytics engine."],
    )


def answer(question: str, df: pd.DataFrame, *, prefer_llm: bool = True) -> dict[str, Any]:
    """Answer a natural-language question, returning the full audit trail."""
    warnings: list[str] = []
    parsed: ParsedQuery | None = None
    engine = "rule_based"
    model_name: str | None = None

    # ---- Stage 1: LLM intent proposal (optional) ------------------------
    if prefer_llm:
        llm_status = ollama_client.status()
        if llm_status["available"]:
            proposal = ollama_client.propose_operation(question, _schema(df))
            if proposal:
                validated = _validate_llm_operation(proposal, df)
                if validated is not None:
                    parsed = validated
                    engine = "llm"
                    model_name = proposal.get("_model")
                else:
                    warnings.append(
                        "The local model proposed an operation that did not pass "
                        "schema validation; the rule-based parser was used instead."
                    )
                    warnings.append(
                        f"Rejected proposal: {str(proposal)[:200]}"
                    )
        elif prefer_llm:
            warnings.append(
                "Ollama is not available, so the rule-based engine was used. "
                "This is fully functional — the LLM is an optional enhancement."
            )

    # ---- Stage 2: Rule-based fallback (always available) ----------------
    if parsed is None:
        try:
            parsed = parse_question(question, df)
            engine = "rule_based"
        except ParseFailure as failure:
            return to_jsonable({
                "ok": False,
                "engine": "rule_based",
                "engine_label": _ENGINE_LABELS["rule_based"],
                "intent": "unsupported",
                "operation": {},
                "result": {"error": failure.message},
                "explanation": failure.message,
                "answer": failure.message,
                "supported_examples": failure.suggestions or build_suggestions(df),
                "warnings": warnings,
                "verified": False,
            })

    # ---- Stage 3: Execute against real data -----------------------------
    try:
        outcome = execute(parsed, df)
    except ExecutionError as error:
        return to_jsonable({
            "ok": False,
            "engine": engine,
            "engine_label": _ENGINE_LABELS.get(engine, engine),
            "intent": parsed.intent,
            "operation": parsed.params,
            "result": {"error": str(error)},
            "explanation": str(error),
            "answer": str(error),
            "supported_examples": build_suggestions(df),
            "warnings": warnings + parsed.notes,
            "verified": False,
        })

    base_explanation = outcome["explanation"]
    final_explanation = base_explanation
    llm_used = False

    # ---- Stage 4: Optional LLM paraphrase of verified numbers -----------
    if engine == "llm" and model_name:
        paraphrase = ollama_client.explain_result(
            question,
            {"explanation": base_explanation, "result": outcome["result"]},
            model=model_name,
        )
        if paraphrase:
            final_explanation = paraphrase
            llm_used = True

    verified = bool(
        outcome["result"].get("verified", parsed.intent in {
            "row_count", "column_list", "missing_values", "duplicate_rows",
            "quality_score", "unique_count", "describe_column", "dataset_summary",
        })
    )

    return to_jsonable({
        "ok": True,
        "engine": engine,
        "engine_label": _ENGINE_LABELS.get(engine, engine),
        "model_name": model_name if llm_used else None,
        "intent": parsed.intent,
        "operation": parsed.params,
        "result": outcome["result"],
        "chart": outcome.get("chart"),
        "explanation": final_explanation,
        "computed_explanation": base_explanation,
        "answer": final_explanation,
        "supported_examples": build_suggestions(df),
        "warnings": warnings + parsed.notes,
        "verified": verified,
    })
