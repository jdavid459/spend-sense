from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests

import duckdb
from src.ai_cache import ensure_ai_cache
from src.config import DUCKDB_PATH
from src.merchant_profiles import merchant_profile_lookup

MIN_QUERY_LENGTH = 3
DEFAULT_RESULT_LIMIT = 25
DEFAULT_SEMANTIC_CANDIDATE_COUNT = 60

INTENT_EXPANSIONS = {
    "cafe": ["cafe", "café", "coffee", "espresso", "latte", "starbucks"],
    "coffee": ["coffee", "cafe", "café", "espresso", "latte", "starbucks"],
    "commute": ["commute", "train", "subway", "metro", "uber", "lyft", "transit", "amtrak"],
    "groceries": ["groceries", "grocery", "market", "foods", "whole", "trader", "fresh"],
    "health": ["health", "medical", "wellness", "therapy", "physical", "pharmacy", "doctor"],
    "movie": ["movie", "movies", "film", "cinema", "theater", "theatre"],
    "movies": ["movie", "movies", "film", "cinema", "theater", "theatre"],
    "cinema": ["movie", "movies", "film", "cinema", "theater", "theatre"],
    "theater": ["movie", "movies", "film", "cinema", "theater", "theatre"],
    "theatre": ["movie", "movies", "film", "cinema", "theater", "theatre"],
    "restaurants": ["restaurant", "restaurants", "food", "dining", "eatery", "cafe"],
    "streaming": ["streaming", "subscription", "premium", "netflix", "youtube", "spotify"],
    "subscription": ["subscription", "subscriptions", "premium", "membership", "recurring", "monthly"],
    "subscriptions": ["subscription", "subscriptions", "premium", "membership", "recurring", "monthly"],
    "travel": ["travel", "flight", "hotel", "airline", "uber", "lyft", "transit", "amtrak"],
}
STOPWORDS = {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"}


def _cohere_api_key() -> str | None:
    return os.getenv("COHERE_API_KEY")


def _embed_model() -> str:
    return os.getenv("COHERE_EMBED_MODEL", "embed-english-v3.0")


def _rerank_model() -> str:
    return os.getenv("COHERE_RERANK_MODEL", "rerank-v3.5")


def _timeout_seconds() -> float:
    return float(os.getenv("COHERE_TIMEOUT_SECONDS", "20"))


def _embed_batch_size() -> int:
    return int(os.getenv("COHERE_EMBED_BATCH_SIZE", "96"))


def _hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _query_key(model: str, query_text: str) -> str:
    return _hash_payload({"model": model, "query_text": query_text.strip()})


def _rerank_key(model: str, query_text: str, documents: list[str]) -> str:
    return _hash_payload({"model": model, "query_text": query_text.strip(), "documents": documents})


def _chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[idx : idx + size] for idx in range(0, len(items), size)]


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _expanded_query_terms(query_text: str) -> list[str]:
    clean_query = query_text.strip().lower()
    terms = {token for token in _tokenize(clean_query) if len(token) >= 2 and token not in STOPWORDS}
    if clean_query in INTENT_EXPANSIONS:
        terms.update(INTENT_EXPANSIONS[clean_query])
    for token in list(terms):
        terms.update(INTENT_EXPANSIONS.get(token, []))
    return sorted(terms)


def _lexical_match_score(query_text: str, document_text: str) -> float:
    clean_query = query_text.strip().lower()
    document = (document_text or "").lower()
    document_tokens = set(_tokenize(document))
    score = 0.0

    if clean_query and clean_query in document:
        score += 3.0

    for term in _expanded_query_terms(clean_query):
        if " " in term:
            if term in document:
                score += 1.5
        elif term in document_tokens:
            score += 1.0
        elif term in document:
            score += 0.5

    return score


def _cohere_post(endpoint: str, payload: dict[str, Any], *, max_retries: int = 3) -> dict[str, Any]:
    api_key = _cohere_api_key()
    if not api_key:
        raise RuntimeError("COHERE_API_KEY is not configured. Add it to .env to enable semantic search.")

    response = None
    for attempt in range(max_retries + 1):
        response = requests.post(
            f"https://api.cohere.com/v2/{endpoint}",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=_timeout_seconds(),
        )
        if response.status_code != 429 or attempt == max_retries:
            break
        retry_after = int(response.headers.get("retry-after", "10"))
        time.sleep(max(retry_after, 5 * (attempt + 1)))

    assert response is not None
    response.raise_for_status()
    return response.json()


def _extract_embeddings(payload: dict[str, Any]) -> list[list[float]]:
    embeddings = payload.get("embeddings")
    if isinstance(embeddings, dict):
        vectors = embeddings.get("float") or embeddings.get("int8") or embeddings.get("uint8") or []
        return [[float(value) for value in vector] for vector in vectors]
    if isinstance(embeddings, list):
        return [[float(value) for value in vector] for vector in embeddings]
    if isinstance(payload.get("texts"), list) and isinstance(payload.get("embeddings_float"), list):
        return [[float(value) for value in vector] for vector in payload["embeddings_float"]]
    raise ValueError(f"Unexpected embedding response shape: {payload}")


def _embed_texts(texts: list[str], *, model: str, input_type: str) -> list[list[float]]:
    if not texts:
        return []
    payload = {
        "model": model,
        "input_type": input_type,
        "embedding_types": ["float"],
        "texts": texts,
    }
    return _extract_embeddings(_cohere_post("embed", payload))


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def _search_text(row: pd.Series) -> str:
    date_text = ""
    if pd.notna(row.get("transaction_date")):
        date_text = pd.to_datetime(row["transaction_date"]).strftime("%Y-%m-%d")
    amount_abs = float(row.get("amount_abs") or 0)
    direction = "debit" if bool(row.get("is_debit")) else "credit"
    flags = []
    if bool(row.get("is_recurring")):
        flags.append("recurring")
    if bool(row.get("is_anomaly")):
        flags.append("anomaly")
    flag_text = ", ".join(flags) if flags else "standard"
    return (
        f"merchant: {row.get('normalized_merchant') or 'Unknown'}. "
        f"merchant_group: {row.get('merchant_group') or 'Unknown'}. "
        f"category: {row.get('final_category') or row.get('raw_category') or 'Unknown'}. "
        f"raw_description: {row.get('raw_description') or ''}. "
        f"transaction_type: {row.get('transaction_type') or 'Unknown'}. "
        f"amount: ${amount_abs:,.2f} {direction}. "
        f"date: {date_text or 'Unknown'}. "
        f"signals: {flag_text}. "
        f"merchant_source: {row.get('merchant_source') or 'Unknown'}."
    )


def build_search_documents(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=[
                "transaction_id",
                "transaction_date",
                "normalized_merchant",
                "merchant_group",
                "final_category",
                "amount_abs",
                "raw_description",
                "merchant_source",
                "is_recurring",
                "is_anomaly",
                "search_text",
            ]
        )

    documents = df[
        [
            "transaction_id",
            "transaction_date",
            "normalized_merchant",
            "merchant_group",
            "final_category",
            "amount_abs",
            "raw_description",
            "merchant_source",
            "is_recurring",
            "is_anomaly",
            "is_debit",
            "transaction_type",
            "raw_category",
        ]
    ].copy()
    profile_lookup = merchant_profile_lookup()
    documents["merchant_profile_text"] = documents["normalized_merchant"].map(profile_lookup).fillna("")
    documents["search_text"] = documents.apply(_search_text, axis=1) + " " + documents["merchant_profile_text"]
    return documents.drop(columns=["is_debit", "transaction_type", "raw_category", "merchant_profile_text"])


def _load_transaction_embedding_rows(
    con: duckdb.DuckDBPyConnection,
    transaction_ids: list[str],
    model: str,
) -> dict[str, tuple[str, list[float]]]:
    if not transaction_ids:
        return {}
    placeholders = ", ".join(["?"] * len(transaction_ids))
    rows = con.execute(
        f"""
        select transaction_id, search_text, embedding_json
        from ai.transaction_embedding_cache
        where embedding_model = ?
          and transaction_id in ({placeholders})
        """,
        [model, *transaction_ids],
    ).fetchall()
    return {
        str(transaction_id): (cached_text, json.loads(embedding_json))
        for transaction_id, cached_text, embedding_json in rows
    }


def ensure_transaction_embeddings(
    documents: pd.DataFrame,
    model: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    model = model or _embed_model()
    if documents.empty:
        return documents.copy(), {"document_count": 0, "cache_hits": 0, "embedded_now": 0, "stale_rows": 0}

    prepared = documents.copy()
    transaction_ids = prepared["transaction_id"].astype(str).tolist()

    with duckdb.connect(str(DUCKDB_PATH)) as con:
        ensure_ai_cache(con)
        cached_rows = _load_transaction_embedding_rows(con, transaction_ids, model)

        cached_embeddings: dict[str, list[float]] = {}
        missing_docs: list[dict[str, Any]] = []
        cache_hits = 0
        stale_rows = 0

        for row in prepared[["transaction_id", "search_text"]].itertuples(index=False):
            transaction_id = str(row.transaction_id)
            cached = cached_rows.get(transaction_id)
            if cached and cached[0] == row.search_text:
                cached_embeddings[transaction_id] = [float(value) for value in cached[1]]
                cache_hits += 1
            else:
                if cached:
                    stale_rows += 1
                missing_docs.append({"transaction_id": transaction_id, "search_text": row.search_text})

        embedded_now = 0
        for batch in _chunks(missing_docs, _embed_batch_size()):
            vectors = _embed_texts(
                [item["search_text"] for item in batch],
                model=model,
                input_type="search_document",
            )
            embedded_now += len(vectors)
            now = datetime.now(timezone.utc)
            for item, vector in zip(batch, vectors, strict=False):
                cached_embeddings[item["transaction_id"]] = vector
                con.execute(
                    """
                    insert or replace into ai.transaction_embedding_cache (
                        transaction_id,
                        embedding_model,
                        search_text,
                        embedding_json,
                        created_at
                    ) values (?, ?, ?, ?, ?)
                    """,
                    [
                        item["transaction_id"],
                        model,
                        item["search_text"],
                        json.dumps(vector),
                        now,
                    ],
                )

    prepared["embedding"] = prepared["transaction_id"].astype(str).map(cached_embeddings)
    return prepared, {
        "document_count": len(prepared),
        "cache_hits": cache_hits,
        "embedded_now": embedded_now,
        "stale_rows": stale_rows,
        "embedding_model": model,
    }


def get_query_embedding(query_text: str, model: str | None = None) -> tuple[list[float], dict[str, Any]]:
    clean_query = query_text.strip()
    if not clean_query:
        raise ValueError("Enter a search query.")

    model = model or _embed_model()
    query_key = _query_key(model, clean_query)

    with duckdb.connect(str(DUCKDB_PATH)) as con:
        ensure_ai_cache(con)
        cached = con.execute(
            """
            select embedding_json
            from ai.search_query_cache
            where query_key = ?
            """,
            [query_key],
        ).fetchone()
        if cached:
            return [float(value) for value in json.loads(cached[0])], {
                "query_cached": True,
                "embedding_model": model,
            }

        vector = _embed_texts([clean_query], model=model, input_type="search_query")[0]
        con.execute(
            """
            insert or replace into ai.search_query_cache (
                query_key,
                query_text,
                embedding_model,
                embedding_json,
                created_at
            ) values (?, ?, ?, ?, ?)
            """,
            [query_key, clean_query, model, json.dumps(vector), datetime.now(timezone.utc)],
        )
    return vector, {"query_cached": False, "embedding_model": model}


def rerank_candidates(
    query_text: str,
    candidates: pd.DataFrame,
    model: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if candidates.empty:
        return candidates.copy(), {"used_rerank": False, "rerank_cached": False}

    model = model or _rerank_model()
    documents = candidates["search_text"].tolist()
    rerank_key = _rerank_key(model, query_text, documents)

    with duckdb.connect(str(DUCKDB_PATH)) as con:
        ensure_ai_cache(con)
        cached = con.execute(
            """
            select results_json
            from ai.search_rerank_cache
            where rerank_key = ?
            """,
            [rerank_key],
        ).fetchone()
        if cached:
            results = json.loads(cached[0])
            reranked = _apply_rerank_results(candidates, results)
            return reranked, {"used_rerank": True, "rerank_cached": True, "rerank_model": model}

        try:
            payload = {
                "model": model,
                "query": query_text.strip(),
                "documents": documents,
                "top_n": len(documents),
            }
            response = _cohere_post("rerank", payload)
        except Exception as exc:
            fallback = candidates.copy()
            fallback["rerank_score"] = pd.NA
            fallback["rank_source"] = "hybrid_semantic"
            return fallback, {
                "used_rerank": False,
                "rerank_cached": False,
                "rerank_error": str(exc),
                "rerank_model": model,
            }

        results = response.get("results", [])
        con.execute(
            """
            insert or replace into ai.search_rerank_cache (
                rerank_key,
                model,
                query_text,
                documents_json,
                results_json,
                created_at
            ) values (?, ?, ?, ?, ?, ?)
            """,
            [
                rerank_key,
                model,
                query_text.strip(),
                json.dumps(documents),
                json.dumps(results),
                datetime.now(timezone.utc),
            ],
        )

    reranked = _apply_rerank_results(candidates, results)
    return reranked, {"used_rerank": True, "rerank_cached": False, "rerank_model": model}


def _apply_rerank_results(candidates: pd.DataFrame, results: list[dict[str, Any]]) -> pd.DataFrame:
    rerank_frame = pd.DataFrame(
        [
            {
                "candidate_index": int(item.get("index", 0)),
                "rerank_score": float(item.get("relevance_score", 0.0)),
            }
            for item in results
        ]
    )
    ranked = candidates.reset_index(drop=True).copy()
    ranked["candidate_index"] = ranked.index
    if rerank_frame.empty:
        ranked["rerank_score"] = pd.NA
        ranked["rank_source"] = "hybrid_semantic"
        return ranked.drop(columns=["candidate_index"])

    ranked = ranked.merge(rerank_frame, on="candidate_index", how="left")
    ranked["rank_source"] = "cohere_rerank"
    ranked = ranked.sort_values(
        ["rerank_score", "hybrid_score", "semantic_score"],
        ascending=False,
        na_position="last",
    )
    return ranked.drop(columns=["candidate_index"])


def _confidence_label(row: pd.Series) -> str:
    rerank_score = float(row.get("rerank_score") or 0)
    semantic_score = float(row.get("semantic_score") or 0)
    lexical_score = float(row.get("lexical_score") or 0)
    if rerank_score >= 0.15 or semantic_score >= 0.38 or lexical_score >= 4:
        return "high"
    if rerank_score >= 0.08 or semantic_score >= 0.30 or lexical_score >= 2:
        return "medium"
    return "low"


def _is_confident_match(row: pd.Series) -> bool:
    rerank_score = float(row.get("rerank_score") or 0)
    semantic_score = float(row.get("semantic_score") or 0)
    lexical_score = float(row.get("lexical_score") or 0)
    return bool(
        rerank_score >= 0.08
        or semantic_score >= 0.33
        or (lexical_score >= 1 and semantic_score >= 0.20)
        or (lexical_score >= 2 and rerank_score >= 0.04)
    )


def search_transactions(
    df: pd.DataFrame,
    query_text: str,
    *,
    result_limit: int = DEFAULT_RESULT_LIMIT,
    semantic_candidate_count: int = DEFAULT_SEMANTIC_CANDIDATE_COUNT,
    use_rerank: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    clean_query = query_text.strip()
    if len(clean_query) < MIN_QUERY_LENGTH:
        raise ValueError(f"Enter at least {MIN_QUERY_LENGTH} characters.")
    if df.empty:
        raise ValueError("No transactions match the current filters.")

    documents = build_search_documents(df)
    documents_with_embeddings, embedding_meta = ensure_transaction_embeddings(documents)
    query_embedding, query_meta = get_query_embedding(clean_query)

    scored = documents_with_embeddings.copy()
    scored["semantic_score"] = scored["embedding"].map(lambda vector: _cosine_similarity(query_embedding, vector))
    scored["lexical_score"] = scored["search_text"].map(lambda text: _lexical_match_score(clean_query, text))
    scored["hybrid_score"] = scored["semantic_score"] + (scored["lexical_score"] * 0.08)
    scored = scored.sort_values(
        ["hybrid_score", "semantic_score", "transaction_date"],
        ascending=[False, False, False],
    )

    semantic_candidates = scored.head(max(result_limit, semantic_candidate_count)).copy()
    rerank_meta: dict[str, Any] = {"used_rerank": False, "rerank_cached": False}
    ranked = semantic_candidates.copy()
    ranked["rank_source"] = "hybrid_semantic"
    ranked["rerank_score"] = pd.NA

    if use_rerank:
        ranked, rerank_meta = rerank_candidates(clean_query, semantic_candidates.head(semantic_candidate_count))

    ranked["match_confidence"] = ranked.apply(_confidence_label, axis=1)
    confident_results = ranked[ranked.apply(_is_confident_match, axis=1)].copy()
    confident_results = confident_results.head(result_limit).copy()

    confident_results = confident_results.drop(columns=["embedding"], errors="ignore").reset_index(drop=True)
    semantic_candidates = semantic_candidates.drop(columns=["embedding"], errors="ignore").reset_index(drop=True)
    confident_results.insert(0, "rank", range(1, len(confident_results) + 1))

    meta = {
        **embedding_meta,
        **query_meta,
        **rerank_meta,
        "query_text": clean_query,
        "result_limit": result_limit,
        "semantic_candidate_count": semantic_candidate_count,
        "result_count": len(confident_results),
        "min_query_length": MIN_QUERY_LENGTH,
    }
    return confident_results, semantic_candidates, meta
