from __future__ import annotations

import duckdb

AI_CACHE_DDL = """
create schema if not exists ai;

create table if not exists ai.merchant_enrichment_cache (
    raw_description varchar primary key,
    suggested_merchant varchar,
    suggested_category varchar,
    suggested_merchant_group varchar,
    confidence double,
    reasoning varchar,
    model varchar,
    created_at timestamp
);

create table if not exists ai.spend_summary_cache (
    summary_key varchar primary key,
    model varchar,
    filters_json varchar,
    context_text varchar,
    response_text varchar,
    created_at timestamp
);

create table if not exists ai.transaction_embedding_cache (
    transaction_id varchar,
    embedding_model varchar,
    search_text varchar,
    embedding_json varchar,
    created_at timestamp,
    primary key (transaction_id, embedding_model)
);

create table if not exists ai.search_query_cache (
    query_key varchar primary key,
    query_text varchar,
    embedding_model varchar,
    embedding_json varchar,
    created_at timestamp
);

create table if not exists ai.search_rerank_cache (
    rerank_key varchar primary key,
    model varchar,
    query_text varchar,
    documents_json varchar,
    results_json varchar,
    created_at timestamp
);

create table if not exists ai.merchant_profile_cache (
    normalized_merchant varchar primary key,
    merchant_group varchar,
    final_category varchar,
    merchant_summary varchar,
    semantic_tags_json varchar,
    reasoning varchar,
    model varchar,
    created_at timestamp
);
"""


def ensure_ai_cache(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(AI_CACHE_DDL)
