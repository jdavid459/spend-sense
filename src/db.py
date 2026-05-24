from __future__ import annotations

import pandas as pd

import duckdb
from src.config import DUCKDB_PATH


def query_df(sql: str, params: list | tuple | None = None) -> pd.DataFrame:
    with duckdb.connect(str(DUCKDB_PATH), read_only=True) as con:
        return con.execute(sql, params or []).fetchdf()
