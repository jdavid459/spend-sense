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
"""


def ensure_ai_cache(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(AI_CACHE_DDL)
