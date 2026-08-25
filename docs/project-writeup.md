# Project writeup

## Data issues and decisions

The source contains 9,268 order lines and 9,085 distinct JSON payloads. An `order_id` may appear
on multiple legitimate product lines, so deduplicating by `order_id` would destroy valid data.
Instead, ingestion calculates a canonical payload hash and source occurrence number. Cleaning
keeps the first identical payload and quarantines 183 later copies.

The final cleaning result is 8,787 accepted lines and 481 quarantined lines. Rejection reasons
are arrays and can overlap. The main issues were 101 test rows, 167 invalid quantities, 24
non-positive prices, and 13 extreme positive price outliers. The outliers used a value of
`999999`; rather than hardcoding that value, the SQL compares each price with the median for its
product and currency and rejects values above ten times that baseline. This conservative rule
records `implausible_unit_price_outlier`, removes the planted anomalies, and leaves a maximum
clean price of 207.87.

Recoverable fields were repaired rather than discarded. The clean table contains 93 customer
IDs recovered from unambiguous email mappings, one explicitly flagged deterministic surrogate,
76 category repairs, 212 SKU repairs, and 3,486 non-ISO timestamp repairs. Missing categories
and malformed SKUs were repaired from a canonical product catalog. Rows with invalid quantities
or prices were quarantined because inventing financial values would be unsafe. Refunded rows
remain in the clean table for auditability but only completed rows contribute to revenue.

EUR orders use a rate of one. RON orders use the latest available rate on or before their
`fx_reference_date`, preferring an exact date. Future dates stay pending and contribute no EUR
amount until the date arrives. This avoids using a plausible but incorrect current rate. Both
marts expose pending counts and completeness flags so partial totals cannot be mistaken for
final totals.

## Production monitoring

Each stage writes a running, succeeded, or failed record to `ops.pipeline_runs`, including
timestamps, metrics, and a bounded error message. Critical SQL checks are written to
`ops.data_quality_results`. The parent `daily_etl` run succeeds only after ingestion, cleaning,
FX loading, and both marts complete successfully.

GitHub Actions runs the pipeline daily at 06:15 UTC. A monitor is triggered after every daily
workflow completion, so explicit failures are visible immediately. A second independent monitor
runs at 09:00 UTC. If GitHub silently misses the daily trigger, there is no failed daily job to
inspect. At 09:00, the most recent successful database run would be older than the 26-hour limit,
so the independent check fails on the same day.

The monitor also detects a newer failed database run, empty source/clean tables, empty expected
marts, and stale mart refresh timestamps. GitHub records the failure and can send repository
notifications. In a production system I would forward failures to Slack or PagerDuty through a
dedicated alerting integration, include the parent and stage run IDs, define ownership and
severity, and graph freshness, duration, row-count changes, quarantine rates, pending FX, and
revenue movements in an observability platform.

## AI usage

I used ChatGPT/Codex during architecture design, boilerplate generation, SQL and Python review,
test design, edge-case discussion, and documentation editing. I kept the layered PostgreSQL
model, explicit SQL transformations, idempotent loaders, operational tables, and automated test
structure after reviewing and validating them.

I changed several AI-assisted proposals based on observed data and execution results. I did not
deduplicate by `order_id`; I added an auditable surrogate for the one otherwise recoverable
customer; I kept future FX values pending; I added median-based positive-price outlier detection
after mart totals revealed an initially missed anomaly; and I changed the independent monitor
time after identifying that the original schedule could miss a silent trigger failure for a day.
I also selected the IPv4-compatible Supabase Session pooler after testing the hosted connection.

I personally executed every migration and pipeline stage, reviewed SQL samples and aggregate
results, ran repeated idempotency checks, verified the hosted database, reviewed Git diffs,
managed feature/fix branches and pull requests, and retained final responsibility for the data
rules and submitted implementation. No AI service is used by the runtime ETL pipeline.
