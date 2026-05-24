# SpendSense

AI-assisted spend analytics from a Chase credit card CSV.

## Stack

- Python
- DuckDB
- dbt + dbt-duckdb
- Dash + Plotly
- Cohere API

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Data modes

- `demo`: uses `data/demo/chase_transactions_demo.csv`
- `private`: uses your local Chase CSV at `data/private/chase_transactions.csv`

Private data is gitignored.

## Pipeline

```bash
python scripts/generate_demo_data.py
python scripts/ingest_chase_csv.py
cd dbt && dbt deps --profiles-dir . && dbt run --profiles-dir . && dbt test --profiles-dir .
cd ..
python app/app.py
```
