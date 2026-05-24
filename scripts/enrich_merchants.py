from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

import duckdb

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.ai_cache import ensure_ai_cache
from src.config import DUCKDB_PATH

load_dotenv()

ALLOWED_CATEGORIES = [
    "Groceries",
    "Food & Drink",
    "Travel",
    "Bills & Utilities",
    "Entertainment",
    "Shopping",
    "Health & Wellness",
    "Personal",
    "Professional Services",
    "Fees & Adjustments",
    "Gifts & Donations",
    "Gas",
    "Home",
    "Other",
]


def extract_json(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found in Cohere response: {text[:500]}")
    return json.loads(text[start : end + 1])


def cohere_chat_json(raw_description: str, raw_category: str, model: str) -> dict[str, Any]:
    api_key = os.getenv("COHERE_API_KEY")
    if not api_key:
        raise RuntimeError("COHERE_API_KEY is not configured in .env")

    prompt = f"""
You normalize credit card transaction merchants for an analytics pipeline.
Return only a JSON object. No markdown.

Raw transaction description: {raw_description!r}
Bank-provided category: {raw_category!r}

Allowed categories:
{", ".join(ALLOWED_CATEGORIES)}

JSON schema:
{{
  "suggested_merchant": "clean merchant name",
  "suggested_category": "one allowed category",
  "suggested_merchant_group": "short group such as Transit, Restaurant, Healthcare, Streaming, Retail",
  "confidence": 0.0,
  "reasoning": "one concise sentence"
}}
""".strip()

    response = requests.post(
        "https://api.cohere.com/v2/chat",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        },
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload.get("message", {}).get("content", [])
    text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
    if not text_parts and "text" in payload:
        text_parts = [payload["text"]]
    return extract_json("\n".join(text_parts))


def get_candidates(con: duckdb.DuckDBPyConnection, limit: int):
    return con.execute(
        """
        select
            review.raw_description,
            review.raw_category,
            review.transaction_count,
            review.total_spend,
            review.review_priority_score
        from marts.mart_merchant_review as review
        left join ai.merchant_enrichment_cache as cache
            on review.raw_description = cache.raw_description
        where review.needs_review
          and cache.raw_description is null
        order by review.review_priority_score desc, review.total_spend desc
        limit ?
        """,
        [limit],
    ).fetchdf()


def main():
    limit = int(os.getenv("MERCHANT_ENRICHMENT_LIMIT", "25"))
    model = os.getenv("COHERE_MODEL", "command-a-03-2025")

    with duckdb.connect(str(DUCKDB_PATH)) as con:
        ensure_ai_cache(con)
        candidates = get_candidates(con, limit)
        if candidates.empty:
            print("No uncached merchant enrichment candidates found.")
            return

        print(f"Enriching {len(candidates)} merchant descriptions with Cohere model={model}")
        for row in candidates.itertuples(index=False):
            raw_description = row.raw_description
            try:
                result = cohere_chat_json(raw_description, row.raw_category, model)
                suggested_category = result.get("suggested_category") or row.raw_category or "Other"
                if suggested_category not in ALLOWED_CATEGORIES:
                    suggested_category = "Other"
                values = [
                    raw_description,
                    result.get("suggested_merchant") or raw_description,
                    suggested_category,
                    result.get("suggested_merchant_group") or "AI Suggested",
                    float(result.get("confidence") or 0),
                    result.get("reasoning") or "",
                    model,
                    datetime.now(timezone.utc),
                ]
                con.execute(
                    """
                    insert or replace into ai.merchant_enrichment_cache values (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                print(f"✓ {raw_description} -> {values[1]} / {values[2]} ({values[4]:.2f})")
            except Exception as exc:
                print(f"✗ Failed to enrich {raw_description!r}: {exc}")


if __name__ == "__main__":
    main()
