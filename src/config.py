from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def project_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


DATA_MODE = os.getenv("SPEND_DATA_MODE", "demo").lower()
DUCKDB_PATH = project_path(os.getenv("DUCKDB_PATH", "duckdb/spend_sense.duckdb"))
DEMO_CHASE_CSV = project_path(os.getenv("DEMO_CHASE_CSV", "data/demo/chase_transactions_demo.csv"))
PRIVATE_CHASE_CSV = project_path(os.getenv("PRIVATE_CHASE_CSV", "data/private/chase_transactions.csv"))


def private_csv_path() -> Path:
    """Resolve the private Chase CSV.

    If PRIVATE_CHASE_CSV exists, use it. Otherwise, auto-detect the latest
    modified CSV in data/private/ so new Chase exports are picked up without
    renaming.
    """
    if PRIVATE_CHASE_CSV.exists():
        return PRIVATE_CHASE_CSV

    private_dir = PROJECT_ROOT / "data/private"
    csvs = sorted(path for path in private_dir.glob("*") if path.is_file() and path.suffix.lower() == ".csv")
    if csvs:
        return max(csvs, key=lambda path: path.stat().st_mtime)
    return PRIVATE_CHASE_CSV


def input_csv_path() -> Path:
    if DATA_MODE == "private":
        return private_csv_path()
    if DATA_MODE == "demo":
        return DEMO_CHASE_CSV
    raise ValueError(f"Unsupported SPEND_DATA_MODE={DATA_MODE!r}; expected 'demo' or 'private'.")
