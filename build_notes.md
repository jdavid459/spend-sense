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

## Remaining Cohere roadmap

The planned metrics layer is the next analytics-engineering slice, but it does not replace the Cohere roadmap. Remaining Cohere-focused features to add:

1. Semantic transaction search using Cohere embeddings.
   - Build searchable transaction text from modeled marts.
   - Cache embeddings locally in DuckDB.
   - Embed user query and use vector similarity to return relevant transactions.
   - Example queries: `coffee shops`, `subscriptions`, `health expenses`, `transportation`, `large work-related purchases`.

2. Cohere Rerank on top of semantic search.
   - Retrieve top N candidates via embeddings.
   - Rerank candidates with Cohere Rerank.
   - Show the final ranked results in the app.

3. Stronger grounded AI spend summary.
   - Use the upcoming dbt metric marts rather than raw tables.
   - Include category deltas, anomaly metrics, recurring burden, and data quality/AI coverage.

4. Natural-language spend Q&A.
   - Answer questions like `Why was March high?` or `Which subscriptions could I cut?`
   - Ground responses in dbt marts, not raw model guesses.

5. Batched merchant enrichment.
   - Current enrichment is one merchant description per Cohere call.
   - Future version should support `MERCHANT_ENRICHMENT_BATCH_SIZE=10` or `25`.
   - Potentially 50 per batch may work, but start smaller for reliable JSON parsing.

Recommended order remains:

1. Metrics layer.
2. Improve AI Summary using metrics.
3. Semantic search with embeddings.
4. Rerank.
5. Batched enrichment.

## Test failure investigation: duplicate `fct_transactions.transaction_id`

A dbt build failed on:

```text
unique_fct_transactions_transaction_id
```

Observed 6 duplicate `transaction_id` values in `marts.fct_transactions`.

Investigation notes:

- `raw.chase_transactions` had no duplicate `row_hash` values.
- `staging.stg_chase_transactions` had no duplicate `transaction_id` values.
- `intermediate.int_merchant_normalization` had 587 rows / 587 distinct transaction IDs.
- `intermediate.int_transaction_features` had 587 rows / 587 distinct transaction IDs.
- `intermediate.int_recurring_transactions` had duplicate `normalized_merchant` values because it is grouped by both `normalized_merchant` and `final_category`.

Root cause:

`fct_transactions` joined recurring data only by `normalized_merchant`. If the same merchant appeared in multiple categories, that join could duplicate transaction rows.

Fix:

Updated `dbt/models/marts/fct_transactions.sql` so the recurring CTE includes `final_category` and joins on both:

```sql
on features.normalized_merchant = recurring.normalized_merchant
and features.final_category = recurring.final_category
```

This preserves one row per transaction and should fix the failing unique test.

## Modeling improvement note: merchant identity vs transaction category

Current model caveat:

The current pipeline can allow a single `normalized_merchant` to appear with multiple `final_category` values. This is realistic in some cases, but the current model makes the semantics slightly confusing.

Examples:

```text
Amazon -> Shopping
Amazon -> Groceries
Costco -> Shopping
Costco -> Groceries
```

This happens because merchant identity and transaction category are different concepts:

```text
merchant identity = who was paid
transaction category = what kind of spend this transaction represents
```

The recent fix to `fct_transactions` joined recurring data on both `normalized_merchant` and `final_category` to avoid duplicate transaction rows. That fix is technically correct for the current grain, but it reveals a modeling improvement opportunity.

Recommended future refactor:

### `dim_merchant`

One row per merchant entity.

Suggested fields:

```text
merchant_id
normalized_merchant
merchant_group
merchant_source
default_category
first_seen
last_seen
transaction_count
total_spend
```

### `fct_transactions`

One row per transaction.

Suggested fields:

```text
transaction_id
transaction_date
merchant_id
transaction_category
raw_category
amount
is_debit
is_credit
is_anomaly
```

### `mart_recurring_charges`

One row per recurring pattern, not necessarily one row per merchant.

Suggested grain:

```text
merchant_id + transaction_category + cadence/amount pattern
```

Suggested fields:

```text
recurring_charge_id
merchant_id
transaction_category
avg_amount
amount_stddev
cadence
first_seen
last_seen
is_recurring
```

Better conceptual model:

```text
merchant = entity
category = transaction classification
recurring charge = merchant/category/amount pattern
```

This would make the project easier to explain and would prevent confusion around whether a merchant can have multiple categories. Yes, a merchant can have multiple transaction categories, but it should have a single merchant identity.

## Interview job links

- Netflix: https://explore.jobs.netflix.net/careers/job/790314349156
- Cohere: https://jobs.ashbyhq.com/cohere/9baccd88-c051-474f-bfe8-6867fca54cee

## Interview job descriptions loaded

### Netflix — Analytics Engineer 5 - Ad Ranking

Link: https://explore.jobs.netflix.net/careers/job/790314349156

Role focus/context:

- Senior analytics engineering role on Netflix Ads Ranking, a 0-to-1 ads business area.
- Team powers ad personalization and ads marketplace intelligence.
- Responsibilities emphasize metrics design, deep-dive analysis, product experiment evaluation, self-service analytics products, data models/pipelines, executive/business-critical dashboards, ad delivery/performance/revenue recommendations, ML model observability/anomaly or drift detection, A/B testing/experiment tracking, innovation with GenAI, and clear stakeholder communication.
- Qualifications emphasize 5+ years in data engineering/data science/analytics engineering, strong SQL, Python preferred, modern warehouses such as Redshift/BigQuery/Snowflake, data modeling, ETL frameworks, analytics tools, ambiguity tolerance, communication, and ad tech/streaming/consumer-product experience as a plus.

Project relevance:

- SpendSense should emphasize modeled event facts, dimensional merchant/category modeling, metric definitions, denominator rigor, reusable dbt marts, data quality tests, anomaly detection, recurring behavior, dashboarding, and explainable insights.
- Strong interview framing: “I built the project as an analytics product, not just a dashboard: explicit grain, metric semantics, quality checks, data products, and stakeholder-ready interpretation.”

### Cohere — Data Engineer, Data Foundations

Link: https://jobs.ashbyhq.com/cohere/9baccd88-c051-474f-bfe8-6867fca54cee

Role focus/context:

- Data Engineer role on Cohere's Analytics & Data Insights / Data Foundations area.
- Cohere builds frontier AI systems for developers and enterprises powering content generation, semantic search, RAG, and agents.
- Responsibilities emphasize working on new customer experiences built on advanced AI systems, collaborating with researchers/engineers, running implementations end-to-end, and partnering across research, marketing, sales, and finance to influence products and strategy.
- Qualifications emphasize 5+ years production-grade data processing systems, strong Python and SQL, distributed data processing frameworks such as Apache Beam/Spark/Flink, large-scale data system design, transforming unstructured data into performant datasets in relational DBs and blob storage, modern analytics stack tooling such as BigQuery/Airflow/dbt, Java/Go and Kubernetes as nice-to-haves, genuine AI interest, and comfort operating at the edge of known systems.

Project relevance:

- SpendSense should emphasize production-style Python ingestion, robust SQL/dbt models, AI enrichment cache/provenance, semantic search/RAG-like transaction retrieval, cached embeddings/rerank, unstructured-to-structured transformation, and end-to-end ownership.
- Strong interview framing: “I treated AI outputs as governed data products: cached, auditable, confidence-scored, precedence-controlled, and measured via coverage/fallback metrics.”

### Pi tutor extension idea

Goal: create a Pi extension that observes development activity and teaches role-relevant Python, data engineering, analytics engineering, and AI/data-governance concepts while coding.

Desired behavior:

- Lightweight “key learnings” or “did you know?” tutoring while building in Pi.
- Connect concrete code changes/tool activity to interview-relevant concepts for Netflix Analytics Engineering and Cohere Data Foundations.
- Prioritize Python programming skill development, including idioms, data structures, algorithmic patterns, testing, error handling, performance, and maintainability.
- Also teach DE/AE concepts: ingestion, idempotency, schema design, dbt model grain, metric definitions, data quality tests, observability, lineage, API retries/rate limits, caching, governance, batch vs streaming, distributed processing analogies, and system design tradeoffs.

Initial implementation direction:

- Build a personal/global Pi extension under `~/.pi/agent/extensions/role-tutor.ts` so it is available while coding without being committed into the SpendSense repo.
- Use Pi event hooks such as `tool_call`, `tool_result`, `turn_end`, and maybe `before_agent_start`.
- Use `ctx.ui.setWidget()` for a persistent colored tutor box above or below the editor; use `ctx.ui.notify()` sparingly; optionally use an overlay for `/tutor` deep dives.
- Register commands such as `/tutor`, `/tutor on`, `/tutor off`, `/tutor focus python|analytics|data-eng|cohere|netflix`, `/tutor recap`, and `/tutor quiz`.
- Start with deterministic rule-based detection from filenames, commands, and diffs rather than making an LLM call after every action.
- Later add optional LLM-powered synthesis using current model for richer recaps/quiz questions.
- Persist lightweight state with `pi.appendEntry()` so the extension remembers concepts surfaced during a session.

## Role Tutor Pi extension MVP

Implemented a personal/global Pi extension outside the SpendSense repo:

```text
~/.pi/agent/extensions/role-tutor.ts
```

Repo privacy/organization note: `.pi/` is ignored in this repo so personal Pi extensions/state do not get committed into SpendSense.

Purpose:

- provide ambient interview-oriented tutoring while developing in Pi
- connect concrete coding activity to Python, data engineering, analytics engineering, Netflix AE, and Cohere DE concepts
- keep default behavior non-disruptive via a small persistent widget rather than frequent popups

Current features:

- persistent `Role Tutor` widget below the editor via `ctx.ui.setWidget()`
- footer status indicator showing active tutor focus
- watches `tool_call` and `tool_result` events for reads/edits/writes/bash commands
- detects Python edits, dbt/SQL edits, dbt builds/tests, pytest/ruff/compileall, API/retry-related code, dict/loop patterns, docs edits, and search/navigation behavior
- stores learning events with `pi.appendEntry("role-tutor-learning", ...)`
- restores recent learning history on session start
- custom rendered recap messages via `pi.registerMessageRenderer("role-tutor-recap", ...)`

Commands:

```text
/tutor
/tutor on
/tutor off
/tutor focus balanced
/tutor focus python
/tutor focus analytics
/tutor focus data-eng
/tutor focus cohere
/tutor focus netflix
/tutor recap
/tutor quiz
```

Design choices:

- rule-based detection first, to avoid expensive/noisy LLM calls after every action
- focus modes filter surfaced lessons to match the current interview-prep goal
- `/tutor recap` and `/tutor quiz` create intentional study moments without interrupting normal coding flow

Next improvements:

- validate the extension in Pi with `/reload`
- tune widget placement/color after seeing it in the TUI
- add richer pattern detection from actual edit diffs, not just tool inputs
- add optional LLM-powered `/tutor deepdive` for a turn-level explanation and role-specific interview answer
- add spaced repetition / concept frequency tracking

## Metrics layer implementation

Added the first analytics-engineering metrics layer in dbt and surfaced it in Dash.

New marts:

- `dbt/models/marts/mart_spend_kpis.sql`
  - one-row global spend KPI table
  - uses debit spend as the denominator for spend shares
  - excludes payments/credits from spend metrics
  - includes concentration, recurring, anomaly, and AI/provenance coverage metrics
- `dbt/models/marts/mart_monthly_kpis.sql`
  - one row per month
  - includes spend, transaction count, average/median transaction amount, top category/merchant, recurring/anomaly metrics, and MoM spend changes
  - only exposes MoM percent change when prior-month spend is at least `$50`
- `dbt/models/marts/mart_category_metrics.sql`
  - one row per category
  - includes spend share, monthly average/stddev/volatility, top merchant, latest/prior month spend, and guarded latest MoM percent change
- `dbt/models/marts/mart_data_quality.sql`
  - provenance coverage by `merchant_source` and `category_source`
  - measures transaction/spend share, unique raw descriptions, and unique normalized merchants

Updated `dbt/models/marts/schema.yml` with docs and basic not-null/unique tests for the new marts.

Updated `app/app.py`:

- loads the new metric marts
- adds a `Metrics` tab
- shows metric cards for concentration, recurring burden, anomaly exposure, fallback coverage, Cohere coverage, and monthly volatility
- adds a data-quality coverage chart
- adds monthly KPI and category metric tables
- includes explanatory denominator copy, especially that payments/credits are excluded from spend denominators

Validation passed:

```bash
source .venv/bin/activate
cd dbt && dbt build --profiles-dir .
python -m compileall app scripts src
ruff check .
```

## Metrics tab refactor: unified metric grain

After reviewing the first metrics page, changed direction to a more standardized metric registry pattern.

Added:

- `dbt/models/marts/mart_metric_summary.sql`

Grain:

```text
one row per metric for the latest 30-day period, with comparison to the previous 30-day period
```

Core columns:

```text
as_of_date
current_period_start
current_period_end
comparison_period_start
comparison_period_end
metric_key
metric_label
metric_group
metric_value
comparison_value
delta_value
delta_pct
unit
favorable_direction
definition
```

This makes heterogeneous metrics easier to display together because every metric shares the same shape:

```text
metric | current value | prior 30d value | delta vs prior 30d | definition
```

Updated the Dash `Metrics` tab to use `marts.mart_metric_summary` as the primary page source instead of separately visualizing several differently-grained marts. The page now shows standardized cards and a metric registry table.

Kept the earlier supporting marts (`mart_spend_kpis`, `mart_monthly_kpis`, `mart_category_metrics`, `mart_data_quality`) because they remain useful analytical building blocks, but the user-facing Metrics tab now uses the unified metric grain.

Validation passed:

```bash
cd dbt && dbt build --profiles-dir .
python -m compileall app scripts src
ruff check .
```

## Project modeling philosophy: dbt-first logic

Established a general project rule:

- Put as much business logic as possible in dbt/SQL.
- Python should stay simple and primarily handle ingestion, API calls, and presentation callbacks.
- Metric definitions, grains, denominators, rolling windows, and testable transformations should live in dbt for observability, documentation, lineage, and testing.
- For non-additive metrics, dbt should expose additive numerator/denominator components where possible, and the app can compute filtered ratios from those modeled components.

No major concern with this philosophy. The main caveat is that Python remains appropriate for CSV ingestion, Cohere API interaction/retries, embedding calls, and Dash interactivity. But the app should not become the source of truth for metric definitions.

## Daily additive metric fact

Added:

```text
dbt/models/marts/mart_daily_metric_values.sql
```

Grain:

```text
metric_date
metric_key / metric_name / metric_group
final_category
normalized_merchant
merchant_source
category_source
```

Measures:

```text
metric_value
metric_value_l30d
metric_value_prior_l30d
unit
```

This model is intentionally limited to additive metrics so it can respond cleanly to dashboard filters. It currently includes spend, transaction count, credit, anomaly, recurring, fallback, Cohere, and seed-rule coverage metrics.

Implementation details:

- pulls modeled transaction grain from `marts.fct_transactions`
- unions metric events into a common shape
- aggregates to daily metric grain
- densifies with a date spine so rolling 30-day windows are stable
- computes rolling 30-day and prior rolling 30-day values in SQL

Updated `app/app.py` Metrics tab:

- reads `marts.mart_daily_metric_values`
- category, merchant, date, and view filters now apply to metrics
- metric cards show rolling 30-day values and prior-30-day deltas
- trend chart uses `metric_value_l30d`
- table shows standardized metric rollups

Validation passed:

```bash
cd dbt && dbt build --profiles-dir .
python -m compileall app scripts src
ruff check .
```

## Metrics tab UX refactor: one row per metric

Refactored the Metrics tab layout based on screenshot review.

Previous version had separate metric cards and a combined trend chart, which repeated the same metrics in multiple places and was harder to scan.

New layout:

```text
metric group / metric name | large rolling-30-day value + prior-period delta | individual trend line
```

Each metric is now displayed once in a horizontal row, making it easier to read top-to-bottom and left-to-right. The page still uses `marts.mart_daily_metric_values` as the source, so date/category/merchant/view filters apply before the rolling value, delta, and trend are displayed.

Validation passed:

```bash
python -m compileall app scripts src
ruff check .
```

## Metrics group filter

Added a `Metric groups` multi-select to the filter bar. It is populated from `marts.mart_daily_metric_values.metric_group` and applies to the Metrics tab only.

This allows narrowing the metric list to groups such as:

- Spend
- Behavior
- Risk
- Data Quality
- Credits

Validation passed:

```bash
python -m compileall app scripts src
ruff check .
```

## Metrics group filter placement fix

Moved the `Metric groups` selector out of the global dashboard filter bar and into the Metrics tab section itself.

Implementation details:

- `render_tab` now renders the Metrics page shell with the in-section dropdown and a `metrics-content` container.
- Added a dedicated `render_metrics_content` callback so the in-section metric group dropdown can update only the metrics list.
- Enabled Dash `suppress_callback_exceptions=True` because the metric group dropdown is created dynamically only when the Metrics tab is rendered.
- Global filters remain focused on transaction-level filtering; the metric group filter is now contextual to the Metrics page.

Validation passed:

```bash
python -m compileall app scripts src
ruff check .
```

## Session handoff: metrics layer stabilized

Current state after metrics iteration:

- App is running locally on:

```text
http://127.0.0.1:8051/
```

- Metrics work moved strongly toward a dbt-first architecture.
- Project rule established: most business logic should live in dbt/SQL, not Python.
- Python/Dash should stay thin and focus on presentation, callbacks, ingestion, and API calls where unavoidable.
- dbt should own metric definitions, grains, rolling windows, denominator choices, lineage, tests, and reusable modeled outputs.

### New/updated dbt metrics models

Added `dbt/models/marts/mart_daily_metric_values.sql`.

Grain:

```text
metric_date
metric_key
metric_name
metric_group
final_category
normalized_merchant
merchant_source
category_source
```

Measures:

```text
metric_value
metric_value_l30d
metric_value_prior_l30d
unit
```

Design notes:

- This model intentionally focuses on additive metrics.
- It pulls from `marts.fct_transactions`.
- It unions transaction-derived metric events into a common shape.
- It aggregates to daily metric grain.
- It densifies dates with a date spine.
- It calculates rolling 30-day and prior rolling 30-day values in SQL.
- This lets the frontend apply filters while still relying on dbt-modeled metric fields.

Current additive metrics include:

```text
total_spend
debit_transaction_count
credit_amount
credit_transaction_count
anomaly_spend
anomaly_transaction_count
recurring_spend
recurring_transaction_count
fallback_spend
fallback_transaction_count
cohere_spend
cohere_transaction_count
seed_rule_spend
seed_rule_transaction_count
```

Supporting metrics marts still exist and may be useful for future summaries/AI grounding:

```text
mart_spend_kpis
mart_monthly_kpis
mart_category_metrics
mart_data_quality
mart_metric_summary
```

But the user-facing Metrics tab now primarily uses:

```text
marts.mart_daily_metric_values
```

### Metrics tab UX

The Metrics tab was refactored into a row-based layout that the user liked:

```text
metric group / metric name | large rolling-30-day value + delta | individual trend line
```

This replaced the earlier approach of separate metric cards plus a combined chart, which repeated metrics in multiple places and was harder to scan.

Current Metrics tab behavior:

- Each metric appears once.
- Rows read left-to-right and top-to-bottom.
- Large value shows the rolling 30-day value as of the latest selected metric date.
- Delta compares current rolling 30-day value to prior rolling 30-day value.
- Each metric has its own small trend line using `metric_value_l30d`.
- Date/category/merchant/view filters apply to the metrics.
- A contextual `Metric groups` multi-select lives inside the Metrics tab, not in the global filter bar.
- Metric groups include values such as Spend, Behavior, Risk, Data Quality, and Credits.

Implementation details:

- `app/app.py` now loads `marts.mart_daily_metric_values`.
- Metrics page shell is rendered in `render_tab`.
- A dedicated `render_metrics_content` callback handles the in-page metric group filter.
- Dash app now uses `suppress_callback_exceptions=True` because the metric group dropdown is dynamically rendered only on the Metrics tab.

### Validation completed

Ran and passed:

```bash
source .venv/bin/activate
cd dbt && dbt build --profiles-dir .
cd ..
python -m compileall app scripts src
ruff check .
```

Latest dbt build status:

```text
PASS=52 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=52
```

### Notes for next session: Cohere features

The next session should start building the rest of the Cohere roadmap now that the metrics layer is in a better place.

Recommended next order:

1. Improve AI Summary so it is grounded in dbt-modeled metrics, especially `mart_daily_metric_values` and/or supporting metric marts.
2. Add semantic transaction search using Cohere embeddings.
3. Cache embeddings locally in DuckDB, similar to the merchant enrichment cache pattern.
4. Add a search UI tab or section.
5. Add Cohere Rerank on top of semantic search results.
6. Add natural-language spend Q&A grounded in modeled marts and retrieved transaction context.
7. Later improve merchant enrichment batching.

Cohere implementation principles to preserve:

- AI outputs should be cached and auditable.
- dbt models should expose AI provenance and coverage.
- Deterministic seed rules should take precedence over AI where appropriate.
- AI coverage/fallback rates should remain first-class metrics.
- Python should handle API calls/retries/caching, but downstream business semantics should be modeled in dbt.

## Grounded AI Summary upgrade

Implemented the first major remaining Cohere feature: a stronger AI Summary grounded in modeled marts/metrics rather than a loose text dump.

Changes made:

- Added `src/ai_summary.py`
  - builds a structured summary context from filtered `marts.fct_transactions`
  - incorporates rolling 30-day comparisons from `marts.mart_daily_metric_values`
  - includes selected-window spend, recurring, anomaly, merchant-source coverage, top categories/merchants, monthly trend, and example anomalies/recurring merchants
- Added `ai.spend_summary_cache` in DuckDB via `src/ai_cache.py`
  - stores summary key, model, filters, prompt context, response text, and timestamp
- Updated `src/cohere_client.py`
  - AI summaries now use a stricter grounded prompt
  - responses are cached in DuckDB for auditability/reuse
  - HTTP failures return a user-visible message instead of crashing the app
- Updated `app/app.py`
  - AI Summary tab now shows grounding KPI cards
  - summary generation is based on filtered dbt marts + daily metric fact
  - added a collapsible section showing the exact context sent to Cohere

Validation passed:

```bash
python -m compileall app src
.venv/bin/ruff check app src
```

## AI Summary UX + modularization follow-up

Iterated on the first AI Summary implementation after UI review and real latency testing.

What changed:

- Switched the default experience to an **instant deterministic summary**.
  - AI is no longer required for the tab to be useful.
  - The Cohere call now happens only when the user clicks `Generate AI Summary`.
- Added `app/components/ai_summary.py`.
  - moved AI Summary tab rendering and callback wiring out of `app/app.py`
  - makes the feature easier to maintain or remove later
- Expanded `src/ai_summary.py`.
  - deterministic summary now drives the default UX
  - added compact prompt-cue generation separate from the full audit/debug context
- Kept `src/cohere_client.py` summary caching in DuckDB, keyed by prompt version/model/filters/context.
- The AI Summary tab now preserves usable content even when Cohere is slow or unavailable.

Latency investigation:

- Local prep is fast (`~0.03s` for filtering + summary-context construction).
- A trivial Cohere ping (`2+2`) returned successfully in under a second.
- A compact-context summary request with a simple prompt returned successfully in about `5s`.
- The heavier instruction-rich production prompt intermittently timed out at `20–30s`.

Current interpretation:

- the bottleneck is not DuckDB/dbt/local Python work
- the bottleneck appears to be the remote Cohere request, especially when the prompt is overly constrained
- prompt complexity matters more than raw context size alone

Recommended future follow-up if we want more reliable AI-summary generation:

1. simplify the production prompt further
2. consider a faster Cohere model if available
3. optionally add lightweight latency logging around the summary request
4. keep deterministic summary as the primary UX regardless

Validation after modularization passed:

```bash
python -m compileall app src
.venv/bin/ruff check app src
python app/app.py
```

## Cohere semantic search + merchant profile retrieval

Implemented the next major Cohere roadmap slice: semantic transaction search with embeddings, rerank, and a governed merchant-profile layer.

What changed:

- Added `src/semantic_search.py`
  - builds searchable transaction text from `marts.fct_transactions`
  - caches transaction embeddings in DuckDB
  - caches query embeddings and rerank results in DuckDB
  - uses Cohere embeddings for recall and Cohere Rerank for precision
  - applies confidence gating so weak matches are hidden instead of shown
- Added `app/components/semantic_search.py`
  - isolated the search UI/callback logic from `app/app.py`
  - moved the experience into the `Transactions` tab instead of a separate AI tab
  - search runs live after a short typing pause and only affects the transactions table
- Added `scripts/backfill_transaction_embeddings.py`
  - precomputes transaction embeddings for faster repeated searches/demo runs
- Expanded `src/ai_cache.py`
  - added `ai.transaction_embedding_cache`
  - added `ai.search_query_cache`
  - added `ai.search_rerank_cache`
- Added `src/merchant_profiles.py`
  - creates a governed semantic profile per normalized merchant using Cohere chat
  - stores merchant summary + semantic tags in DuckDB
  - loads those cached profiles into search text at runtime for stronger recall
- Added `scripts/backfill_merchant_profiles.py`
  - backfills merchant profiles in batches
  - falls back to one-by-one merchant generation only if a merchant is missing from a batch response

Why the merchant-profile layer was added:

- embeddings over raw transaction text alone were not always enough for intent-style queries like `movie`
- a merchant such as `AMC` may not contain enough descriptive raw text in every row for reliable direct retrieval
- the better pattern is to enrich merchants once, cache that governed semantic profile, and let search use both raw facts and entity-level semantics
- this is more interview-relevant and closer to how a real data/AI pipeline would separate offline enrichment from online retrieval

Implementation decisions:

- avoided merchant-specific hardcoding like `AMC -> movie theater`
- kept retrieval auditable by storing semantic profiles in DuckDB
- used a Python dictionary only as an in-memory lookup over the cached merchant-profile table during app runtime
- kept the global dashboard filters deterministic; semantic search only changes the transactions view
- switched merchant-profile generation from one-request-per-merchant to batched requests

Backfill / coverage status:

- transaction embeddings were backfilled for all modeled transactions
- merchant semantic profiles were backfilled for all normalized merchants
- final merchant-profile coverage reached `114 / 114` merchants
- batch run summary:
  - `inserted=36`
  - `skipped=78`
  - `failed=0`
  - `batch_calls=4`
  - `fallback_calls=10`

Observed search behavior after the merchant-profile layer:

- `coffee` returns coffee/cafe merchants cleanly
- `health` returns healthcare/wellness merchants cleanly
- `movie` now returns `AMC` / `AMC Theatres` without hardcoding those names into the search logic

Validation:

```bash
python -m compileall app src scripts
.venv/bin/ruff check app src scripts
python scripts/backfill_transaction_embeddings.py
python scripts/backfill_merchant_profiles.py
python app/app.py
```

Git commit created for the semantic-search feature:

```text
Add Cohere semantic transaction search with merchant profiles
```

## Dashboard chart polish follow-up

Made a small UX polish pass on charts after review:

- `Top merchants by spend`
  - added value labels at the end of bars
- `Estimated monthly recurring spend`
  - added value labels at the end of bars
  - ensured the chart reads largest-at-top to smallest-at-bottom

This was intentionally kept as a separate small follow-up after the larger semantic-search implementation so the feature work and UI polish stay easy to explain independently.

## Demo preview and Render deployment notes

Validated the hosted-demo path end to end using demo-only data.

Local demo preview setup:

- built a separate demo DuckDB at `duckdb/spend_sense_demo.duckdb` so private/local data stayed untouched
- ran the full demo pipeline against that separate DB
- launched the Dash app locally with:
  - `SPEND_DATA_MODE=demo`
  - `DUCKDB_PATH=duckdb/spend_sense_demo.duckdb`
- confirmed the app loaded successfully on a local preview URL

Observed demo snapshot:

- `139` demo transactions
- `$4,554.03` debit spend
- `3` anomalies
- `24` recurring transactions

Recommended Render setup for easiest hosting:

- host as a Render Web Service from the repo root
- leave `Root Directory` blank
- use demo mode only in production
- keep private CSVs, local `.env`, and local DuckDB files out of git

Render build command used:

```bash
pip install -r requirements.txt && pip install gunicorn && python scripts/generate_demo_data.py && python scripts/ingest_chase_csv.py && cd dbt && dbt deps --profiles-dir . && dbt build --profiles-dir .
```

Render start command used:

```bash
gunicorn app.app:server --bind 0.0.0.0:$PORT
```

Render environment variables discussed:

```text
SPEND_DATA_MODE=demo
COHERE_API_KEY=...
PYTHON_VERSION=3.11.11
```

Important deployment issue encountered:

- initial Render deploy failed because Render created the environment with Python `3.14`
- `dbt` / `mashumaro` in the current stack failed under that version during build
- the fix was to set `PYTHON_VERSION=3.11.11` in Render, clear build cache, and redeploy
- after pinning Render to Python `3.11.11`, deployment succeeded

Practical hosting guidance going forward:

- local development can continue to use private mode
- the hosted site should stay on demo mode
- the default public URL will be the Render subdomain (`*.onrender.com`) unless a custom domain is later attached
