"""Optional local LLM integration via Ollama.

Design constraints from the project brief:
  * Ollama is entirely optional; everything works without it.
  * The model NEVER computes numbers. It only maps a question to a structured
    intent + column names, which are then validated against the real schema and
    executed by pandas/SciPy.
  * If Ollama is unreachable, we fall back to the rule-based parser — the
    response always states which engine produced it.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from ...config import settings


def _base() -> str:
    return settings.OLLAMA_BASE_URL.rstrip("/")


def list_models(timeout: float = 3.0) -> list[str]:
    """Return installed Ollama model names, or an empty list if unreachable."""
    if not settings.OLLAMA_ENABLED:
        return []
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{_base()}/api/tags")
            response.raise_for_status()
            payload = response.json()
        return [model.get("name", "") for model in payload.get("models", []) if model.get("name")]
    except (httpx.HTTPError, ValueError, KeyError):
        return []


def is_available() -> bool:
    return bool(list_models())


def status() -> dict[str, Any]:
    if not settings.OLLAMA_ENABLED:
        return {
            "enabled": False,
            "available": False,
            "base_url": _base(),
            "model": settings.OLLAMA_MODEL,
            "models": [],
            "message": "Ollama integration is disabled by configuration. "
                       "The rule-based engine will handle all questions.",
        }
    models = list_models()
    if not models:
        return {
            "enabled": True,
            "available": False,
            "base_url": _base(),
            "model": settings.OLLAMA_MODEL,
            "models": [],
            "message": (
                "Ollama is not reachable at "
                f"{_base()}. The rule-based engine will handle all questions. "
                "To enable LLM intent parsing, install Ollama and run "
                f"'ollama pull {settings.OLLAMA_MODEL}'."
            ),
        }
    model_present = any(
        m == settings.OLLAMA_MODEL or m.split(":")[0] == settings.OLLAMA_MODEL.split(":")[0]
        for m in models
    )
    return {
        "enabled": True,
        "available": True,
        "base_url": _base(),
        "model": settings.OLLAMA_MODEL,
        "models": models,
        "message": (
            f"Ollama is running with {len(models)} model(s). Using "
            f"'{settings.OLLAMA_MODEL}' for intent parsing."
            if model_present
            else f"Ollama is running but '{settings.OLLAMA_MODEL}' is not installed. "
                 f"Available: {', '.join(models[:5])}."
        ),
    }


INTENT_SCHEMA_PROMPT = """You convert a business question about a dataset into a JSON operation.

You MUST reply with ONLY a JSON object, no prose, no markdown fences.

Dataset columns and their detected semantic types:
{columns}

Supported intents and their parameters:
- aggregate: {{"intent":"aggregate","column":<numeric column>,"agg":"mean|sum|median|min|max|std|count"}}
- grouped_aggregate: {{"intent":"grouped_aggregate","group_column":<categorical column>,"value_column":<numeric column>,"agg":"mean|sum|median|count","n":<int>}}
- group_extreme: {{"intent":"group_extreme","group_column":<categorical>,"value_column":<numeric>,"agg":"sum|mean|max|min","mode":"max|min"}}
- top_n: {{"intent":"top_n","group_column":<categorical>,"value_column":<numeric>,"agg":"sum|mean|count","n":<int>,"order":"desc|asc"}}
- value_counts: {{"intent":"value_counts","column":<categorical>,"n":<int>}}
- correlation_pair: {{"intent":"correlation_pair","x":<numeric>,"y":<numeric>,"method":"pearson"}}
- correlation_matrix: {{"intent":"correlation_matrix","method":"pearson"}}
- describe_column: {{"intent":"describe_column","column":<any column>}}
- missing_values: {{"intent":"missing_values","column":<column or null>}}
- duplicate_rows: {{"intent":"duplicate_rows"}}
- row_count: {{"intent":"row_count"}}
- column_list: {{"intent":"column_list"}}
- quality_score: {{"intent":"quality_score"}}
- outliers: {{"intent":"outliers","column":<numeric column or null>}}
- unique_count: {{"intent":"unique_count","column":<column>}}
- time_trend: {{"intent":"time_trend","date_column":<datetime column>,"value_column":<numeric or null>,"freq":"D|W|M|Q|Y"}}
- ttest: {{"intent":"ttest","numeric_column":<numeric>,"group_column":<categorical>}}
- chi_square: {{"intent":"chi_square","x":<categorical>,"y":<categorical>}}
- dataset_summary: {{"intent":"dataset_summary"}}

Rules:
1. Use ONLY column names that appear exactly in the list above. Never invent a column.
2. Never compute or include any numeric answer. Only the operation.
3. If the question cannot be expressed with these intents, reply:
   {{"intent":"unsupported","reason":"<short reason>"}}
4. Output must be valid JSON on a single line.

Question: {question}"""


def propose_operation(question: str, columns: list[dict[str, str]],
                      model: str | None = None) -> dict[str, Any] | None:
    """Ask the local model for a structured operation. Returns None on any failure."""
    if not settings.OLLAMA_ENABLED:
        return None

    column_text = "\n".join(
        f"  - {col['name']} ({col['kind']})" for col in columns
    )
    prompt = INTENT_SCHEMA_PROMPT.format(columns=column_text, question=question)
    model = model or settings.OLLAMA_MODEL

    try:
        with httpx.Client(timeout=settings.OLLAMA_TIMEOUT_SECONDS) as client:
            response = client.post(
                f"{_base()}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.0, "num_predict": 300},
                },
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    raw = (payload.get("response") or "").strip()
    if not raw:
        return None

    parsed = _extract_json(raw)
    if parsed is None:
        return None
    parsed["_model"] = model
    return parsed


def _extract_json(text: str) -> dict[str, Any] | None:
    """Pull the first JSON object out of a model reply."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def explain_result(question: str, computed: dict[str, Any],
                   model: str | None = None) -> str | None:
    """Ask the model to paraphrase an ALREADY-COMPUTED result.

    The model receives the verified numbers as fixed facts; it is explicitly
    forbidden from altering them. Returns None if Ollama is unavailable.
    """
    if not settings.OLLAMA_ENABLED:
        return None

    model = model or settings.OLLAMA_MODEL
    facts = json.dumps(computed, indent=2, default=str)[:3000]
    prompt = (
        "You are explaining an analytics result to a non-technical user.\n"
        "The numbers below were computed by the analytics engine and are FACTS.\n"
        "Rules:\n"
        "- Do NOT change, round differently, or invent any number.\n"
        "- Do NOT add figures that are not present in the facts.\n"
        "- Answer in 2-4 plain sentences.\n\n"
        f"Question: {question}\n\nVerified facts:\n{facts}\n\nExplanation:"
    )

    try:
        with httpx.Client(timeout=settings.OLLAMA_TIMEOUT_SECONDS) as client:
            response = client.post(
                f"{_base()}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 200},
                },
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    text = (payload.get("response") or "").strip()
    if not text:
        return None
    # Guard: reject an explanation that introduces numbers not present in facts.
    if _introduces_unknown_numbers(text, facts):
        return None
    return text


def _introduces_unknown_numbers(text: str, facts: str) -> bool:
    """Detect hallucinated figures by comparing numeric tokens."""
    def numbers(source: str) -> set[str]:
        tokens = re.findall(r"\d+(?:\.\d+)?", source.replace(",", ""))
        out: set[str] = set()
        for token in tokens:
            try:
                value = float(token)
            except ValueError:
                continue
            # Compare with sensible rounding tolerance.
            out.add(f"{value:.4g}")
        return out

    fact_numbers = numbers(facts)
    for token in numbers(text):
        if token in fact_numbers:
            continue
        # Allow near-matches after rounding (e.g. 1234 vs 1234.0).
        value = float(token)
        if any(
            abs(value - float(existing)) <= max(abs(float(existing)) * 0.01, 0.01)
            for existing in fact_numbers
        ):
            continue
        return True
    return False
