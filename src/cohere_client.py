from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

import requests

import duckdb
from src.ai_cache import ensure_ai_cache
from src.config import DUCKDB_PATH

SUMMARY_PROMPT_VERSION = "v3"


def _summary_key(model: str, context_text: str, filters: dict[str, Any] | None) -> str:
    payload = {
        "model": model,
        "prompt_version": SUMMARY_PROMPT_VERSION,
        "context_text": context_text,
        "filters": filters or {},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _cached_summary(summary_key: str) -> str | None:
    with duckdb.connect(str(DUCKDB_PATH)) as con:
        ensure_ai_cache(con)
        row = con.execute(
            "select response_text from ai.spend_summary_cache where summary_key = ?",
            [summary_key],
        ).fetchone()
    return row[0] if row else None


def _store_summary(
    summary_key: str,
    model: str,
    filters: dict[str, Any] | None,
    context_text: str,
    response_text: str,
) -> None:
    with duckdb.connect(str(DUCKDB_PATH)) as con:
        ensure_ai_cache(con)
        con.execute(
            """
            insert or replace into ai.spend_summary_cache (
                summary_key,
                model,
                filters_json,
                context_text,
                response_text,
                created_at
            )
            values (?, ?, ?, ?, ?, ?)
            """,
            [
                summary_key,
                model,
                json.dumps(filters or {}, sort_keys=True),
                context_text,
                response_text,
                datetime.now(timezone.utc),
            ],
        )


def _cohere_text(payload: dict[str, Any]) -> str:
    content = payload.get("message", {}).get("content", [])
    text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
    return "\n".join(text_parts).strip()


def summarize_spend(context_text: str, filters: dict[str, Any] | None = None) -> str:
    api_key = os.getenv("COHERE_API_KEY")
    if not api_key:
        return "Cohere API key is not configured. Add COHERE_API_KEY to .env to enable AI summaries."

    model = os.getenv("COHERE_MODEL", "command-a-03-2025")
    summary_key = _summary_key(model, context_text, filters)
    cached = _cached_summary(summary_key)
    if cached:
        return cached

    prompt = f"""
You are a concise personal finance analytics assistant.
Write a grounded summary using only the context below.

Requirements:
- Use exactly these markdown section headings: ## What changed, ## What's notable, ## What to review.
- Use 2 to 3 bullets per section.
- Prioritize deltas, drivers, anomalies, recurring burden, and data quality caveats.
- The first bullet under ## What changed must mention the rolling 30-day spend delta.
- The second bullet under ## What changed must use the provided primary category shift cue.
- If relevant, mention the largest category decline separately.
- Keep the narrative aligned with the provided summary-card cues.
- Do not simply restate every top-line metric already visible in a dashboard.
- Use exact numbers from the context whenever possible.
- If evidence is limited, say that clearly.
- Do not invent numbers, causes, or advice beyond the provided data.
- Keep the total response under 170 words.

Grounded context:
{context_text}
""".strip()

    try:
        response = requests.post(
            "https://api.cohere.com/v2/chat",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}]},
            timeout=float(os.getenv("COHERE_TIMEOUT_SECONDS", "20")),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        detail = ""
        if getattr(exc, "response", None) is not None and exc.response is not None:
            detail = exc.response.text.strip()
        message = detail or str(exc)
        return f"Unable to generate Cohere summary right now: {message}"

    text = _cohere_text(response.json()) or "No summary returned from Cohere."
    _store_summary(summary_key, model, filters, context_text, text)
    return text
