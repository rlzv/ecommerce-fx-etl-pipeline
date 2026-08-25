# E-commerce FX ETL Pipeline

An end-to-end data engineering project that ingests e-commerce order lines, cleans and
validates inconsistent source data, loads daily foreign-exchange rates, and builds analytical
tables in EUR.

## Technology

- Python 3.12+
- PostgreSQL 17
- Docker Compose
- SQL transformations
- Pytest, Ruff, and mypy
- GitHub Actions

## Local bootstrap

Copy the environment template and start PostgreSQL:

```bash
cp .env.example .env
docker compose up -d postgres
docker compose ps
```

Create and activate a virtual environment on Windows Git Bash:

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Apply migrations and verify the database connection:

```bash
ecommerce-etl db-check
ecommerce-etl migrate
```

## Orders ingestion

Set `ORDERS_API_KEY` in `.env`, apply pending migrations, and ingest the complete paginated
orders snapshot:

```bash
ecommerce-etl migrate
ecommerce-etl ingest-orders
```

The `raw.orders_raw` landing table stores each source object unchanged as JSONB. A canonical
SHA-256 fingerprint plus an occurrence number preserves exact duplicate rows while keeping
repeat pipeline runs idempotent. Each execution and its row-count metrics are recorded in
`ops.pipeline_runs`.

Inspect the result in PostgreSQL:

```sql
SELECT COUNT(*) FROM raw.orders_raw;

SELECT pipeline_run_id, status, metrics, started_at, finished_at
FROM ops.pipeline_runs
WHERE pipeline_name = 'orders_ingestion'
ORDER BY pipeline_run_id DESC;
```

## Orders cleaning

Refresh the typed clean table and the rejected-row quarantine:

```bash
ecommerce-etl migrate
ecommerce-etl clean-orders
```

Cleaning is implemented in SQL and runs transactionally. The transformation:

- keeps the first copy of an exact duplicate and quarantines later copies;
- quarantines test orders and rows with invalid quantities or prices;
- parses ISO, Unix-second, and `DD/MM/YYYY HH:MM` timestamps as UTC;
- repairs customer IDs from unambiguous normalized-email mappings and creates an explicitly
  flagged deterministic email-based surrogate when no source ID exists anywhere;
- repairs missing categories and malformed SKUs from the canonical product catalog;
- retains refunded orders in `core.orders_clean`, with downstream revenue marts responsible
  for excluding them.

Every rejected row contains one or more explicit reasons, and every repaired clean row records
the applied rules in `data_repairs`. Critical reconciliation and validity checks are stored in
`ops.data_quality_results`.

## Exchange-rate ingestion

Fetch the available RON-to-EUR rate series required by clean orders:

```bash
ecommerce-etl migrate
ecommerce-etl ingest-fx
```

The pipeline requests Frankfurter v2 only through the latest due reference date and adds a
seven-day lookback so weekends and holidays can use the latest earlier published rate. Rates
are upserted into `reference.fx_rates` by date and currency pair. Future order reference dates
remain explicitly pending until a later daily run; they are never filled prematurely with the
current rate.

## Customer spend in EUR

Refresh auditable line conversions and per-customer totals:

```bash
ecommerce-etl migrate
ecommerce-etl refresh-customer-spend
```

Only completed orders contribute to spending. EUR lines use an identity rate of `1`; due RON
lines use the latest available rate on or before `fx_reference_date`. Future RON lines remain
pending and do not silently contribute a guessed amount. `mart.order_lines_eur` records the
requested date, applied date, rate, method, source amount, and EUR amount. The required
`mart.customer_spend_eur` table aggregates those lines and exposes `is_complete` plus pending
line counts so partial totals cannot be mistaken for final totals.

## Country and category revenue

Refresh the ranked Books and Electronics revenue breakdown:

```bash
ecommerce-etl migrate
ecommerce-etl refresh-country-revenue
```

`mart.country_category_revenue_eur` shows resolved EUR revenue for Books, Electronics, and
their combined total by country. It includes only countries whose combined resolved revenue
exceeds EUR 40,000 and ranks them deterministically by revenue. Pending future FX lines and a
completeness flag remain visible so currently partial country totals are not presented as final.

## End-to-end automation and monitoring

Run every stage locally in dependency order:

```bash
ecommerce-etl run-pipeline
ecommerce-etl check-freshness --max-age-hours 26
```

The end-to-end command applies migrations, ingests orders, rebuilds the clean and quarantine
tables, loads currently available FX rates, and refreshes both marts. A PostgreSQL advisory
transaction lock prevents overlapping executions, every stage keeps its own audit record, and
the parent `daily_etl` run fails immediately when any stage or quality check fails.

`.github/workflows/daily-pipeline.yml` runs at 06:15 UTC every day and supports manual runs.
`.github/workflows/freshness-monitor.yml` runs independently at 09:00 UTC and after every daily
workflow completion. Explicit workflow failures are reported immediately; the later independent
schedule leaves normal GitHub scheduling delay headroom while still detecting a completely
missed daily trigger on the same day. The monitor also fails when the latest successful database
run is older than 26 hours, a newer failed run exists, source tables are empty, or either mart is
stale. Configure the hosted `DATABASE_URL` and `ORDERS_API_KEY` as GitHub Actions secrets.

GitHub records failed workflows and can send repository notification emails. In production,
route failures to an on-call destination such as Slack, PagerDuty, or Datadog and attach the
`ops.pipeline_runs` and `ops.data_quality_results` records to the alert for diagnosis.

## Branching

Feature branches are created from `develop` and merged through pull requests. The `main`
branch contains the release-ready version.
