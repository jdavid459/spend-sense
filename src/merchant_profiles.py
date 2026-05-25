from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests

import duckdb
from src.ai_cache import ensure_ai_cache
from src.config import DUCKDB_PATH
from src.db import query_df

ALLOWED_TAGS = [
    "air_travel",
    "bar",
    "bookstore",
    "cafe",
    "coffee_shop",
    "delivery",
    "entertainment",
    "fitness",
    "gas_station",
    "grocery_store",
    "healthcare",
    "hotel",
    "live_events",
    "medical_services",
    "movie_theater",
    "music_audio",
    "news_media",
    "online_retail",
    "personal_care",
    "pharmacy",
    "professional_services",
    "public_transit",
    "restaurant",
    "rideshare",
    "saas_subscription",
    "shopping",
    "streaming_subscription",
    "subscription_service",
    "telecom",
    "travel",
    "utilities",
]


def _extract_json(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found in Cohere response: {text[:500]}")
    return json.loads(text[start : end + 1])


def _cohere_chat_json(prompt: str, *, model: str, max_retries: int = 3) -> dict[str, Any]:
    api_key = os.getenv("COHERE_API_KEY")
    if not api_key:
        raise RuntimeError("COHERE_API_KEY is not configured in .env")

    response = None
    for attempt in range(max_retries + 1):
        response = requests.post(
            "https://api.cohere.com/v2/chat",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
            },
            timeout=float(os.getenv("COHERE_TIMEOUT_SECONDS", "20")),
        )
        if response.status_code != 429 or attempt == max_retries:
            break
        retry_after = int(response.headers.get("retry-after", "10"))
        time.sleep(max(retry_after, 5 * (attempt + 1)))

    assert response is not None
    response.raise_for_status()
    payload = response.json()
    content = payload.get("message", {}).get("content", [])
    text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
    return _extract_json("\n".join(text_parts))


def merchant_profile_candidates() -> pd.DataFrame:
    return query_df(
        """
        select
            normalized_merchant,
            any_value(merchant_group) as merchant_group,
            any_value(final_category) as final_category,
            count(*) as transaction_count,
            sum(case when is_debit then amount_abs else 0 end) as debit_spend,
            string_agg(distinct raw_description, ' || ' order by raw_description) as raw_descriptions
        from marts.fct_transactions
        group by 1
        order by transaction_count desc, debit_spend desc, normalized_merchant
        """
    )


def _merchant_examples(row: pd.Series) -> str:
    examples = (row.get("raw_descriptions") or "")
    sample_examples = examples.split(" || ")[:6]
    return "\n".join(f"- {value}" for value in sample_examples)


def _merchant_profile_prompt(row: pd.Series) -> str:
    return f"""
You are creating a governed merchant semantic profile for transaction search.
Return only JSON. No markdown.

Merchant name: {row['normalized_merchant']!r}
Merchant group: {row['merchant_group']!r}
Current category: {row['final_category']!r}
Transaction count: {int(row['transaction_count'])}
Observed debit spend: {float(row['debit_spend'] or 0):.2f}
Example raw descriptions:
{_merchant_examples(row)}

Task:
- infer what kind of merchant this most likely is
- create a short reusable summary for retrieval/search
- choose 3 to 6 tags from the allowed list only
- prefer broad, user-query-friendly tags over brand-specific details
- if evidence is limited, keep the summary cautious

Allowed tags:
{', '.join(ALLOWED_TAGS)}

JSON schema:
{{
  "merchant_summary": "one concise sentence",
  "semantic_tags": ["lower_snake_case_tag"],
  "reasoning": "one concise sentence"
}}
""".strip()


def _merchant_profile_batch_prompt(batch: pd.DataFrame) -> str:
    merchant_blocks = []
    for idx, row in enumerate(batch.itertuples(index=False), start=1):
        merchant_blocks.append(
            f"""
Merchant {idx}
- normalized_merchant: {row.normalized_merchant!r}
- merchant_group: {row.merchant_group!r}
- final_category: {row.final_category!r}
- transaction_count: {int(row.transaction_count)}
- debit_spend: {float(row.debit_spend or 0):.2f}
- example_raw_descriptions:
{_merchant_examples(pd.Series(row._asdict()))}
""".strip()
        )

    merchant_text = "\n\n".join(merchant_blocks)
    return f"""
You are creating governed merchant semantic profiles for transaction search.
Return only JSON. No markdown.

For each merchant below:
- infer what kind of merchant it most likely is
- create a short reusable summary for retrieval/search
- choose 3 to 6 tags from the allowed list only
- prefer broad, user-query-friendly tags over brand-specific details
- if evidence is limited, keep the summary cautious
- include every input merchant exactly once and do not add extra merchants

Allowed tags:
{', '.join(ALLOWED_TAGS)}

Return this exact JSON shape:
{{
  "profiles": [
    {{
      "normalized_merchant": "merchant name from input",
      "merchant_summary": "one concise sentence",
      "semantic_tags": ["lower_snake_case_tag"],
      "reasoning": "one concise sentence"
    }}
  ]
}}

Merchants:

{merchant_text}
""".strip()


def _normalize_profile(payload: dict[str, Any], *, final_category: str | None) -> dict[str, Any]:
    tags = [
        str(tag).strip().lower()
        for tag in (payload.get("semantic_tags") or [])
        if str(tag).strip().lower() in ALLOWED_TAGS
    ]
    deduped_tags = list(dict.fromkeys(tags))[:6]
    if not deduped_tags:
        deduped_tags = ["shopping"] if final_category == "Shopping" else ["entertainment"]
    return {
        "merchant_summary": (payload.get("merchant_summary") or "").strip(),
        "semantic_tags": deduped_tags,
        "reasoning": (payload.get("reasoning") or "").strip(),
    }


def generate_merchant_profile(row: pd.Series, *, model: str) -> dict[str, Any]:
    payload = _cohere_chat_json(_merchant_profile_prompt(row), model=model)
    return _normalize_profile(payload, final_category=row.get("final_category"))


def generate_merchant_profiles_batch(batch: pd.DataFrame, *, model: str) -> dict[str, dict[str, Any]]:
    payload = _cohere_chat_json(_merchant_profile_batch_prompt(batch), model=model)
    profiles = payload.get("profiles") or []
    if not isinstance(profiles, list):
        raise ValueError(f"Unexpected batch profile response: {payload}")

    final_category_lookup = dict(zip(batch["normalized_merchant"], batch["final_category"], strict=False))
    normalized: dict[str, dict[str, Any]] = {}
    for item in profiles:
        if not isinstance(item, dict):
            continue
        merchant = str(item.get("normalized_merchant") or "").strip()
        if not merchant or merchant not in final_category_lookup:
            continue
        normalized[merchant] = _normalize_profile(item, final_category=final_category_lookup[merchant])
    return normalized


def _store_profile(con: duckdb.DuckDBPyConnection, row: pd.Series, profile: dict[str, Any], model: str) -> None:
    con.execute(
        """
        insert or replace into ai.merchant_profile_cache (
            normalized_merchant,
            merchant_group,
            final_category,
            merchant_summary,
            semantic_tags_json,
            reasoning,
            model,
            created_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            row.get("normalized_merchant"),
            row.get("merchant_group"),
            row.get("final_category"),
            profile["merchant_summary"],
            json.dumps(profile["semantic_tags"]),
            profile["reasoning"],
            model,
            datetime.now(timezone.utc),
        ],
    )


def backfill_merchant_profiles(*, limit: int | None = None, sleep_seconds: float | None = None) -> dict[str, int]:
    model = os.getenv("COHERE_MODEL", "command-a-03-2025")
    batch_size = int(os.getenv("MERCHANT_PROFILE_BATCH_SIZE", "10"))
    if sleep_seconds is None:
        sleep_seconds = float(os.getenv("COHERE_REQUEST_SLEEP_SECONDS", "1.5"))
    candidates = merchant_profile_candidates()
    if limit:
        candidates = candidates.head(limit).copy()

    inserted = 0
    skipped = 0
    failed = 0
    batch_calls = 0
    fallback_calls = 0

    with duckdb.connect(str(DUCKDB_PATH)) as con:
        ensure_ai_cache(con)
        cached_rows = con.execute(
            "select normalized_merchant from ai.merchant_profile_cache where model = ?",
            [model],
        ).fetchall()
        cached = {row[0] for row in cached_rows}

        uncached = candidates[~candidates["normalized_merchant"].isin(cached)].copy()
        skipped = len(candidates) - len(uncached)

        for start_idx in range(0, len(uncached), batch_size):
            batch = uncached.iloc[start_idx : start_idx + batch_size].copy()
            if batch.empty:
                continue

            batch_calls += 1
            batch_profiles: dict[str, dict[str, Any]] = {}
            try:
                batch_profiles = generate_merchant_profiles_batch(batch, model=model)
            except Exception:
                batch_profiles = {}

            for _, row in batch.iterrows():
                merchant = row["normalized_merchant"]
                profile = batch_profiles.get(merchant)
                if profile is None:
                    try:
                        fallback_calls += 1
                        profile = generate_merchant_profile(row, model=model)
                    except Exception:
                        failed += 1
                        continue
                _store_profile(con, row, profile, model)
                inserted += 1

            time.sleep(sleep_seconds)

    return {
        "inserted": inserted,
        "skipped": skipped,
        "failed": failed,
        "batch_calls": batch_calls,
        "fallback_calls": fallback_calls,
    }


def merchant_profile_lookup(model: str | None = None) -> dict[str, str]:
    model = model or os.getenv("COHERE_MODEL", "command-a-03-2025")
    with duckdb.connect(str(DUCKDB_PATH), read_only=True) as con:
        rows = con.execute(
            """
            select normalized_merchant, merchant_summary, semantic_tags_json
            from ai.merchant_profile_cache
            where model = ?
            """,
            [model],
        ).fetchall()
    return {
        merchant: (
            f"merchant_summary: {summary or ''}. semantic_tags: {', '.join(json.loads(tags_json or '[]'))}."
        ).strip()
        for merchant, summary, tags_json in rows
    }
