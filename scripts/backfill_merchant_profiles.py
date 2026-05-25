from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.merchant_profiles import backfill_merchant_profiles


def main() -> None:
    limit_env = os.getenv("MERCHANT_PROFILE_LIMIT", "")
    limit = int(limit_env) if limit_env.strip() else None
    summary = backfill_merchant_profiles(limit=limit)
    print(
        "Merchant profiles backfilled "
        f"inserted={summary['inserted']} skipped={summary['skipped']} failed={summary['failed']} "
        f"batch_calls={summary['batch_calls']} fallback_calls={summary['fallback_calls']}"
    )


if __name__ == "__main__":
    main()
