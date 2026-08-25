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

## Branching

Feature branches are created from `develop` and merged through pull requests. The `main`
branch contains the release-ready version.
