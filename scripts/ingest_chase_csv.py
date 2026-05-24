from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import duckdb

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.ai_cache import ensure_ai_cache
from src.config import DATA_MODE, DUCKDB_PATH, input_csv_path

REQUIRED_COLUMNS = [
    "Transaction Date",
    "Post Date",
    "Description",
    "Category",
    "Type",
    "Amount",
    "Memo",
]


def row_hash(row: pd.Series) -> str:
    # Include source_row_number so exact duplicate charges remain separate transactions.
    payload = "|".join(str(row.get(col, "")) for col in ["source_row_number", *REQUIRED_COLUMNS])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main():
    csv_path = input_csv_path()
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Input CSV not found at {csv_path}. "
            "Use SPEND_DATA_MODE=demo and run scripts/generate_demo_data.py, "
            "or place your Chase CSV under data/private/."
        )

    df = pd.read_csv(csv_path)
    missing = sorted(set(REQUIRED_COLUMNS) - set(df.columns))
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")

    df = df[REQUIRED_COLUMNS].copy()
    df["source_row_number"] = range(1, len(df) + 1)
    df["source_file"] = csv_path.name
    df["source_mode"] = DATA_MODE
    df["ingested_at"] = datetime.now(timezone.utc).isoformat()
    df["row_hash"] = df.apply(row_hash, axis=1)

    DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(DUCKDB_PATH)) as con:
        ensure_ai_cache(con)
        con.execute("create schema if not exists raw")
        con.execute("drop table if exists raw.chase_transactions")
        con.register("raw_df", df)
        con.execute("create table raw.chase_transactions as select * from raw_df")

    print(f"Loaded {len(df)} rows from {csv_path} into {DUCKDB_PATH}: raw.chase_transactions")


if __name__ == "__main__":
    main()
