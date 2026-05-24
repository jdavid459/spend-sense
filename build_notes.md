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

## GitHub repo created and pushed

Created the public GitHub repository:

```text
https://github.com/jdavid459/spend-sense
```

Pushed local `main` to `origin/main`. Private spend data remains excluded by `.gitignore`; only the synthetic demo CSV is committed.

## Dashboard UX iteration

Reworked `app/app.py` from a proof-of-plumbing UI into a more useful analytics dashboard:

- Added a polished header and consistent card styling.
- Added global filters for date range, category, merchant, and view mode.
- Added KPI cards that respond to filters.
- Rebuilt the Overview tab with monthly spend, category spend, top merchants, and daily spend charts.
- Replaced static Bootstrap tables with sortable/filterable Dash DataTables.
- Added explainable anomaly cards plus anomaly details table.
- Improved the recurring spend tab with a chart and table.
- Added a Merchant Cleanup tab to review normalized merchants and raw description examples, which can drive future seed-rule improvements.
- Updated AI Summary to summarize the filtered dbt mart data rather than the full static dataset.

## Local Dash port configurability

The default Dash port `8050` was already in use during validation, so `app/app.py` now supports overriding the port with an environment variable:

```bash
PORT=8051 python app/app.py
```

Default remains `8050`.

## Dashboard visual cleanup after screenshot review

After reviewing the updated dashboard screenshot, made quick visual refinements:

- Reduced KPI value font sizes so long category/date values do not dominate the cards.
- Formatted the Date Window card as a compact human-readable range.
- Added clearer Plotly axis/legend labels instead of raw column names like `amount_abs` and `final_category`.
- Added currency formatting to spend axes.
- Rotated category labels to improve readability.

## Current state / handoff notes

The project is now committed and pushed to GitHub:

```text
https://github.com/jdavid459/spend-sense
```

Current working app state:

- Local `.env` is set to `SPEND_DATA_MODE=private` and is ignored by git.
- `.env.example` remains safe for public/demo use with `SPEND_DATA_MODE=demo`.
- Private Chase CSVs live in `data/private/` and are ignored by git.
- Private mode uses the explicitly configured `PRIVATE_CHASE_CSV` if it exists; otherwise it auto-detects the most recently modified `.csv`/`.CSV` file in `data/private/`.
- Demo mode uses `data/demo/chase_transactions_demo.csv`, which is synthetic and committed.
- dbt now writes clean schemas named `staging`, `intermediate`, `marts`, and `seeds` via `dbt/macros/generate_schema_name.sql`.
- The Dash app reads from the `marts` schema.
- The app supports `PORT`, e.g. `PORT=8051 python app/app.py`.

Validated commands used during development:

```bash
source .venv/bin/activate
python scripts/generate_demo_data.py
python scripts/ingest_chase_csv.py
cd dbt
 dbt seed --profiles-dir .
 dbt run --profiles-dir .
 dbt test --profiles-dir .
cd ..
python app/app.py
```

For private/local data, ensure `.env` contains:

```text
SPEND_DATA_MODE=private
```

For demo/deployable data, use:

```text
SPEND_DATA_MODE=demo
```

Current dashboard features:

- Global date/category/merchant/view filters.
- KPI cards for spend, credits, top category, anomalies, transaction count, average transaction, recurring spend, and date window.
- Overview charts for monthly spend, category spend, top merchants, and daily spend.
- Transactions tab with sortable/filterable Dash DataTable.
- Anomalies tab with explanation cards and details table.
- Recurring tab with recurring spend chart/table.
- Merchant Cleanup tab for reviewing normalized merchants and raw description examples.
- AI Summary tab calls Cohere only if `COHERE_API_KEY` is configured.

Important caveats:

- `dbt/seeds/merchant_rules.csv` is still a generic starter seed, not yet fully derived from the user's actual private data.
- Merchant normalization is currently deterministic/rule-based. Cohere enrichment has not yet been implemented beyond the summary helper.
- Anomaly detection is simple z-score logic in dbt models; it is explainable but not yet sophisticated.
- Recurring detection is heuristic and should be improved after merchant normalization improves.
- The UI is acceptable for now but not final; future work should focus on data/product depth before visual polish.

Recommended next development priorities:

1. Use the real/private transaction data to improve merchant normalization rules.
2. Add a dbt model/mart for unmapped or poorly normalized merchants.
3. Add Cohere-powered merchant/category enrichment with a local DuckDB cache table.
4. Add semantic search over transactions/merchants using Cohere embeddings.
5. Improve anomaly detection and duplicate charge detection.
6. Generate a stronger synthetic demo dataset after learning from the real data patterns.
7. Add deployment support using demo data only.

## Merchant review mart

Added a dbt mart for merchant cleanup prioritization:

```text
dbt/models/marts/mart_merchant_review.sql
```

Purpose:

- move merchant-review aggregation out of the Dash app and into dbt
- identify raw descriptions that still fall back to unmapped/raw merchant names
- prioritize cleanup candidates using transaction count, spend, and unmapped status
- provide a governed table that can later feed either manual seed updates or Cohere enrichment

Columns include:

- `raw_description`
- `normalized_merchant`
- `merchant_group`
- `raw_category`
- `final_category`
- `transaction_count`
- `total_spend`
- `avg_debit_amount`
- `first_seen`
- `last_seen`
- `anomaly_count`
- `has_recurring_flag`
- `needs_review`
- `review_reason`
- `review_priority_score`

Updated `app/app.py` so the Merchant Cleanup tab reads from `marts.mart_merchant_review` instead of aggregating directly in Python.

Privacy note: did not commit merchant rules derived from the user's private Chase data. The public `merchant_rules.csv` remains generic for now. If we add private-data-derived rules later, use a local/private ignored override or only add non-sensitive generic patterns.

## Cohere merchant enrichment cache

Added the first governed Cohere enrichment path.

New files/models:

- `src/ai_cache.py`
  - central DDL/helper for creating `ai.merchant_enrichment_cache`
- `scripts/enrich_merchants.py`
  - reads high-priority `needs_review` rows from `marts.mart_merchant_review`
  - calls Cohere Chat API directly via HTTPS
  - requests structured JSON merchant/category suggestions
  - writes results to `ai.merchant_enrichment_cache`
  - skips already cached raw descriptions
- `dbt/models/staging/stg_ai_merchant_enrichments.sql`
  - dbt view over the enrichment cache

Updated pipeline behavior:

- `scripts/ingest_chase_csv.py` now ensures the empty `ai.merchant_enrichment_cache` table exists, so dbt can run even before any Cohere enrichment has happened.
- `int_merchant_normalization` now applies merchant/category precedence:

```text
seed rule > Cohere cache with confidence >= 0.70 > raw fallback
```

- Added provenance fields:

```text
merchant_source = seed_rule | cohere_cache | fallback
category_source = seed_rule | cohere_cache | chase_raw
ai_confidence
ai_reasoning
```

- `fct_transactions` and `mart_merchant_review` now expose these provenance fields.
- Merchant Cleanup tab now shows provenance columns so it is clear what came from deterministic rules vs AI cache vs fallback.

Important implementation note:

- The installed `cohere` Python package imports `fastavro`, which failed locally because this Python build is missing `_lzma`. To avoid blocking the project, Cohere API calls are made directly with `requests` against `https://api.cohere.com/v2/chat`.
- This still uses Cohere product APIs, but avoids the local package import issue.

How to run enrichment after setting `COHERE_API_KEY` in `.env`:

```bash
source .venv/bin/activate
python scripts/ingest_chase_csv.py
cd dbt && dbt run --profiles-dir . && cd ..
MERCHANT_ENRICHMENT_LIMIT=25 python scripts/enrich_merchants.py
cd dbt && dbt run --profiles-dir . && dbt test --profiles-dir . && cd ..
python app/app.py
```

The second dbt run is needed so cached AI suggestions are incorporated into `int_merchant_normalization`, `fct_transactions`, and downstream marts.

## Cohere model deprecation fix

The first enrichment run failed with HTTP 404s because `.env` and code defaults used `command-r-plus`, which Cohere removed on September 15, 2025.

Updated model defaults to:

```text
COHERE_MODEL=command-a-03-2025
```

Changed in:

- `.env.example`
- local `.env` (ignored by git)
- `scripts/enrich_merchants.py`
- `src/cohere_client.py`

The Cohere endpoint was reachable; the issue was the deprecated model name, not the URL.

## Merchant Cleanup tab review sections + rate-limit safety

Updated the Merchant Cleanup tab to make enrichment status clearer:

- Default nested tab: `Needs Review`
- `Cohere Enriched`
- `Seed Mapped`
- `All`

This avoids confusion where Cohere-enriched merchants still appeared at the top due to historical review-priority scores.

Also updated `scripts/enrich_merchants.py` for trial-key safety:

- default `COHERE_REQUEST_SLEEP_SECONDS=3.1`, which stays under the documented ~20 chat requests/min trial limit
- handles HTTP 429 by sleeping and retrying
- still skips already cached descriptions

To enrich all current uncached review candidates safely, use a high limit with the default sleep:

```bash
MERCHANT_ENRICHMENT_LIMIT=1000 python scripts/enrich_merchants.py
cd dbt && dbt build --profiles-dir . && cd ..
```

Trial keys are documented as limited to about 1,000 API calls/month and 20 chat requests/min for relevant chat models. Since enrichment is cached, repeated runs only process uncached descriptions.

## Planned next step: metric design / analytics engineering layer

The next major development slice should showcase analytics engineering and metric design, not just AI enrichment or dashboarding.

Current app already has:

- Chase CSV ingestion into DuckDB
- dbt staging/intermediate/mart models
- deterministic merchant seed rules
- Cohere merchant/category enrichment cache
- provenance fields (`merchant_source`, `category_source`, `ai_confidence`, `ai_reasoning`)
- Dash dashboard with Overview, Transactions, Anomalies, Recurring, Merchant Cleanup, and AI Summary tabs

Recommended next work is to add a proper metrics layer in dbt and surface it in the frontend.

### Why this matters

This project should demonstrate:

- clear metric definitions
- correct denominator choices
- exclusion of payments/credits from spend metrics
- modeled marts that can be reused outside the dashboard
- data quality / AI coverage observability
- concentration, volatility, run-rate, anomaly, and recurring-spend metrics

This is especially valuable for interviews because it shows analytics engineering judgment, not just chart-building.

### Proposed dbt marts

#### `mart_spend_kpis`

One-row summary table for global spend KPIs.

Suggested fields:

```text
total_spend
credit_amount
transaction_count
debit_transaction_count
avg_transaction_amount
median_transaction_amount
top_category
top_category_spend
top_category_spend_share
top_merchant
top_merchant_spend
top_merchant_spend_share
top_5_merchant_spend
top_5_merchant_spend_share
estimated_monthly_recurring_spend
recurring_spend_share
anomaly_count
anomaly_spend
anomaly_transaction_rate
anomaly_spend_share
fallback_transaction_count
fallback_spend
fallback_transaction_share
fallback_spend_share
cohere_transaction_count
cohere_spend
cohere_transaction_share
cohere_spend_share
seed_rule_transaction_count
seed_rule_spend
seed_rule_transaction_share
seed_rule_spend_share
```

Important definitions:

```text
total_spend = sum(amount_abs) where is_debit = true
credit_amount = sum(amount_abs) where is_credit = true
*_spend_share = numerator spend / total_spend
*_transaction_share = numerator transaction count / transaction_count
```

Payments and credits must not be included in spend denominators.

#### `mart_monthly_kpis`

One row per month.

Suggested fields:

```text
month
total_spend
transaction_count
avg_transaction_amount
median_transaction_amount
top_category
top_category_spend
top_merchant
top_merchant_spend
recurring_spend
recurring_spend_share
anomaly_count
anomaly_spend
mom_spend_change_amount
mom_spend_change_pct
```

Guardrail for percent changes:

```text
Only expose/use mom_spend_change_pct when previous_month_spend >= 50.
```

This prevents misleading percentage changes from tiny baselines.

#### `mart_category_metrics`

One row per category.

Suggested fields:

```text
final_category
total_spend
spend_share
monthly_avg_spend
monthly_spend_stddev
monthly_spend_volatility
transaction_count
avg_transaction_amount
largest_transaction_amount
top_merchant
top_merchant_spend
latest_month_spend
prior_month_spend
latest_mom_change_amount
latest_mom_change_pct
```

Volatility definition:

```text
monthly_spend_volatility = monthly_spend_stddev / monthly_avg_spend
```

#### `mart_data_quality`

One row per merchant/category source combination or per merchant_source.

Suggested fields:

```text
merchant_source
category_source
transaction_count
total_spend
transaction_share
spend_share
unique_raw_descriptions
unique_normalized_merchants
```

This is important because the app now has AI provenance. We should be able to answer:

```text
How much spend was seed-rule mapped?
How much was Cohere-enriched?
How much still falls back to raw Chase descriptions?
```

This is a strong enterprise AI governance story.

### Suggested frontend addition

Add a new tab:

```text
Metrics
```

The tab should show:

- metric cards for concentration / volatility / data quality
- definitions or small explanatory text for each metric
- data quality coverage chart by merchant_source/category_source
- category metric table
- monthly KPI trend table/chart

Suggested cards:

```text
Top Category Share
Top Merchant Share
Top 5 Merchant Share
Recurring Spend Share
Fallback Spend Share
Cohere-Enriched Spend Share
Anomaly Spend Share
Monthly Spend Volatility
```

Example metric explanation copy:

```text
Fallback Spend Share = spend from debit transactions where merchant_source = fallback divided by total debit spend.
```

### Interview framing

For Cohere:

> I track AI coverage and fallback rates as first-class data quality metrics. Cohere enrichments are cached and auditable, deterministic seed rules take priority, and downstream marts preserve provenance.

For Netflix / analytics engineering:

> Transactions are modeled like events. Merchants and categories are dimensions. The metrics layer defines spend, concentration, volatility, anomaly rates, and data quality coverage with explicit denominator choices and dbt tests.

### Recommended implementation order after session restart

1. Add `mart_spend_kpis.sql`.
2. Add `mart_monthly_kpis.sql`.
3. Add `mart_category_metrics.sql`.
4. Add `mart_data_quality.sql`.
5. Add schema.yml docs/tests for these marts.
6. Run `dbt build --profiles-dir .`.
7. Update Dash app to load the new marts.
8. Add a `Metrics` tab.
9. Surface metric definitions in the UI.
10. Update README and build notes.

### Current Cohere enrichment status / reminder

Cohere enrichment is currently one-request-per-merchant-description. It caches successful results in `ai.merchant_enrichment_cache`, so reruns skip already enriched descriptions.

Current script has:

- `MERCHANT_ENRICHMENT_LIMIT`
- `COHERE_REQUEST_SLEEP_SECONDS` defaulting to 3.1 seconds
- retry handling for HTTP 429
- no batching yet

Future improvement:

```text
MERCHANT_ENRICHMENT_BATCH_SIZE=10 or 25
```

Potentially 50 per batch may work, but start with 10–25 for easier JSON parsing/retry behavior. A batch implementation should still cache each merchant row independently and fall back to smaller batches or individual retries if a batch fails.
