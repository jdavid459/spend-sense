from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.db import query_df
from src.semantic_search import build_search_documents, ensure_transaction_embeddings


def main() -> None:
    limit = int(os.getenv("TRANSACTION_EMBEDDING_LIMIT", "0"))
    sql = "select * from marts.fct_transactions order by transaction_date desc"
    if limit > 0:
        sql += f" limit {limit}"

    transactions = query_df(sql)
    if transactions.empty:
        print("No modeled transactions found in marts.fct_transactions.")
        return

    documents = build_search_documents(transactions)
    _, meta = ensure_transaction_embeddings(documents)
    print(
        "Embedded transactions "
        f"document_count={meta['document_count']} "
        f"cache_hits={meta['cache_hits']} "
        f"embedded_now={meta['embedded_now']} "
        f"stale_rows={meta['stale_rows']} "
        f"model={meta['embedding_model']}"
    )


if __name__ == "__main__":
    main()
