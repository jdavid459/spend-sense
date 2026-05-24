# Build Notes

## Project goal
Build a lightweight personal spend analytics app that uses a Chase credit card CSV as the local/private development input and a synthetic Chase-like CSV for hosted demos.

The app is intended to showcase:
- analytics engineering with dbt
- Python ingestion into DuckDB
- dashboarding with Dash/Plotly
- merchant/category modeling
- anomaly and recurring transaction detection
- Cohere-powered enrichment, semantic search, and insight generation

## Initial architecture

```text
Chase CSV / demo CSV
  -> Python ingestion script
  -> DuckDB raw table
  -> dbt staging/intermediate/mart models
  -> Dash app reads dbt marts
  -> Cohere utilities enrich and summarize modeled data
```

## Scaffold created

Created the initial project folders:

```text
app/
app/components/
data/demo/
data/private/
dbt/models/staging/
dbt/models/intermediate/
dbt/models/marts/
dbt/seeds/
scripts/
src/
duckdb/
tests/
```

Private data will live under `data/private/` and should not be committed. Demo data will live under `data/demo/` and can be committed/deployed.

## Environment/dependency files

Added:

- `requirements.txt` with Dash, DuckDB, dbt, Cohere, pandas, Plotly, sklearn, pytest, and ruff.
- `pyproject.toml` with basic project metadata and ruff config.
- `.env.example` documenting runtime configuration.
- `.gitignore` to exclude `.venv`, secrets, generated DuckDB/dbt artifacts, and private transaction CSVs.

## Core scaffolding

Added:

- `src/config.py` to centralize environment-driven paths and switch between `demo` and `private` data modes.
- `scripts/generate_demo_data.py` to create a synthetic Chase-like CSV with recurring charges, inconsistent merchant names, duplicate candidates, and spend anomalies.
- `scripts/ingest_chase_csv.py` to load either the demo or private Chase CSV into `raw.chase_transactions` in DuckDB.

## dbt scaffolding

Added a local dbt project under `dbt/` using `dbt-duckdb`:

- `dbt_project.yml`
- `profiles.yml`
- `seeds/merchant_rules.csv`
- staging model: `stg_chase_transactions`
- intermediate models:
  - `int_merchant_normalization`
  - `int_transaction_features`
  - `int_recurring_transactions`
- mart models:
  - `fct_transactions`
  - `mart_monthly_spend`
  - `mart_anomalies`
  - `mart_recurring_spend`

The dbt models currently use deterministic seed-based merchant normalization. Cohere enrichment will be layered in after the baseline pipeline is working.

## Dash app scaffold

Added `app/app.py`, a first-pass Dash app with tabs for:

- Overview
- Transactions
- Anomalies
- Recurring
- AI Summary

The app reads dbt mart tables from DuckDB. The AI summary tab uses Cohere only if `COHERE_API_KEY` is configured; otherwise it displays a setup message.

## First validation issue and fix

Initial pipeline validation exposed that scripts launched by file path (`python scripts/ingest_chase_csv.py`, `python app/app.py`) did not automatically include the project root on `sys.path`, so imports from `src` failed.

Fixes added:

- `src/__init__.py`
- project-root `sys.path` injection in `scripts/ingest_chase_csv.py`
- project-root `sys.path` injection in `app/app.py`

## Second validation issue and fix

Running dbt exposed two modeling issues:

1. DuckDB does not support `initcap`, so the unmapped merchant fallback in `int_merchant_normalization` now uses the raw description.
2. Exact duplicate transactions should remain separate financial events, but the original `row_hash` would collapse them into the same `transaction_id`. The ingestion script now adds `source_row_number` and includes it in the transaction hash.

## Validation status

Validated the scaffold with:

```bash
python -m compileall app scripts src
ruff check . --fix
ruff check .
python scripts/ingest_chase_csv.py
cd dbt && dbt run --profiles-dir . && dbt test --profiles-dir .
```

Current status:

- Python dependencies installed successfully in `.venv`.
- Demo CSV generation works.
- CSV ingestion to DuckDB works.
- dbt seed/run/test passes on the demo dataset.
- Python files compile.
- Ruff linting passes.

## Dash version compatibility fix

Dash 4 removed the old `app.run_server(...)` API. Updated `app/app.py` to use:

```python
app.run(debug=True)
```

## Private Chase CSV auto-detection

A real Chase export was added to `data/private/` using Chase's default filename. Updated `src/config.py` so `SPEND_DATA_MODE=private` works without renaming the file:

- If `PRIVATE_CHASE_CSV` exists, use that explicit path.
- Otherwise, auto-detect a single `.csv`/`.CSV` file in `data/private/`.
- If multiple private CSVs exist, raise a clear error asking the user to set `PRIVATE_CHASE_CSV`.

This keeps the app compatible with the default Chase export format while still allowing explicit overrides.

## Local mode switched to private

Updated the local, gitignored `.env` file to use:

```text
SPEND_DATA_MODE=private
```

This means local app runs now default to the private Chase export. The committed `.env.example` remains in demo mode for safe deployment defaults.

## Private CSV latest-file detection

Updated `src/config.py` so private mode now auto-detects the most recently modified CSV in `data/private/` when the explicit `PRIVATE_CHASE_CSV` path does not exist.

Behavior now:

1. If `PRIVATE_CHASE_CSV` exists, use it.
2. Otherwise, scan `data/private/` for `.csv`/`.CSV` files and use the latest modified file.
3. If no CSV exists, return the configured default path so ingestion raises the existing file-not-found message.

This allows dropping in a new Chase export and having the app ingest the latest file automatically.

## App showed no data after dbt run

The Dash app was querying `marts.fct_transactions`, but dbt's default schema naming had created tables under `main_marts` because dbt combines the target schema (`main`) with custom schemas (`marts`, `staging`, etc.).

Added `dbt/macros/generate_schema_name.sql` to make custom schemas render exactly as configured:

- `staging`
- `intermediate`
- `marts`
- `seeds`

This keeps dbt output aligned with the app queries and makes the DuckDB schema layout easier to explain.

## GitHub prep / privacy guardrails

Before creating the first git commit, verified that private/local artifacts are excluded from git:

- `.env` is ignored.
- `data/private/*` is ignored except `data/private/.gitkeep`.
- generated DuckDB files under `duckdb/*.duckdb` are ignored.
- dbt artifacts/logs are ignored.
- dbt's local `.user.yml` is ignored.

The repo is safe to publish with the synthetic demo CSV only.

## Initial git commit

Created the initial local git commit:

```text
Initial SpendSense scaffold
```

Attempted to push to `https://github.com/jdavid459/spend-sense.git`, but GitHub returned `Repository not found`, which means the remote repo has not been created yet or the local machine is not authenticated for it.
