from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

OUTPUT = Path("data/demo/chase_transactions_demo.csv")
random.seed(42)

MERCHANT_PATTERNS = [
    ("WHOLE FOODS MARKET", "Groceries", -95, 35, 9),
    ("TRADER JOE'S", "Groceries", -72, 24, 10),
    ("SQ *BLUE BOTTLE COFFEE", "Food & Drink", -7, 2, 30),
    ("TST* SWEETGREEN 1234", "Food & Drink", -18, 5, 18),
    ("DOORDASH*BURGER PALACE", "Food & Drink", -34, 14, 8),
    ("UBER TRIP HELP.UBER.COM", "Travel", -21, 9, 10),
    ("UBER EATS", "Food & Drink", -29, 11, 5),
    ("AMZN MKTP US*8D2K3", "Shopping", -46, 25, 12),
    ("TARGET 00012345", "Shopping", -58, 20, 8),
]

SUBSCRIPTIONS = [
    ("NETFLIX.COM", "Entertainment", -22.99),
    ("SPOTIFY USA", "Entertainment", -10.99),
    ("APPLE.COM/BILL", "Bills & Utilities", -2.99),
    ("OPENAI *CHATGPT SUBSCR", "Professional Services", -20.00),
]


def money(value: float) -> str:
    return f"{value:.2f}"


def add_row(rows: list[dict[str, str]], txn_date: date, description: str, category: str, amount: float):
    rows.append(
        {
            "Transaction Date": txn_date.strftime("%m/%d/%Y"),
            "Post Date": (txn_date + timedelta(days=random.choice([1, 1, 2]))).strftime("%m/%d/%Y"),
            "Description": description,
            "Category": category,
            "Type": "Sale" if amount < 0 else "Payment",
            "Amount": money(amount),
            "Memo": "",
        }
    )


def main():
    rows: list[dict[str, str]] = []
    start = date(2025, 1, 1)
    end = date(2025, 6, 30)
    days = (end - start).days + 1

    for month in range(1, 7):
        for description, category, amount in SUBSCRIPTIONS:
            add_row(rows, date(2025, month, random.randint(2, 6)), description, category, amount)

    for description, category, mean_amount, stddev, count in MERCHANT_PATTERNS:
        for _ in range(count):
            txn_date = start + timedelta(days=random.randrange(days))
            amount = random.gauss(mean_amount, stddev)
            add_row(rows, txn_date, description, category, min(amount, -1.25))

    # Intentional anomalies and duplicate candidates.
    add_row(rows, date(2025, 5, 17), "DOORDASH*BURGER PALACE", "Food & Drink", -148.22)
    add_row(rows, date(2025, 4, 12), "AMZN MKTP US*8D2K3", "Shopping", -389.84)
    add_row(rows, date(2025, 6, 4), "SQ *BLUE BOTTLE COFFEE", "Food & Drink", -7.15)
    add_row(rows, date(2025, 6, 4), "SQ *BLUE BOTTLE COFFEE", "Food & Drink", -7.15)
    add_row(rows, date(2025, 6, 15), "Payment Thank You-Mobile", "Payment", 1800.00)

    rows.sort(key=lambda row: row["Transaction Date"])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "Transaction Date",
                "Post Date",
                "Description",
                "Category",
                "Type",
                "Amount",
                "Memo",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} demo transactions to {OUTPUT}")


if __name__ == "__main__":
    main()
