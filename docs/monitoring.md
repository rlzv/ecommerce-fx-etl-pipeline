# Monitoring and runbook

## Detection model

| Failure mode | Detection | Expected response time |
|---|---|---|
| Stage exception or critical quality failure | Parent `daily_etl` fails and GitHub job exits non-zero | Immediate |
| Daily workflow explicitly fails | `workflow_run` starts freshness workflow and fails it | Minutes |
| GitHub silently misses the daily trigger | Independent 09:00 UTC monitor finds success older than 26 hours | Same morning |
| Pipeline overlap | PostgreSQL advisory lock rejects the second run | Immediate |
| Source/clean data unexpectedly empty | Freshness validation | Scheduled or post-run check |
| Customer/country mart stale | Mart `refreshed_at` age check | Scheduled or post-run check |
| Due FX missing | FX coverage quality check | During pipeline |
| Revenue or rank inconsistency | Mart reconciliation checks | During pipeline |

The daily pipeline runs at 06:15 UTC. The independent 09:00 monitor allows normal GitHub
scheduling delays while making the previous day's successful run older than the 26-hour limit if
the current trigger never happened.

## Operational tables

`ops.pipeline_runs` provides:

- pipeline and stage name;
- `running`, `succeeded`, or `failed` status;
- start and finish timestamps;
- JSON metrics;
- bounded exception type and message.

`ops.data_quality_results` provides check name, status, observed value, expected value, details,
and timestamp.

## Triage queries

Latest runs:

```sql
SELECT pipeline_run_id, pipeline_name, status, started_at, finished_at, error_message
FROM ops.pipeline_runs
ORDER BY pipeline_run_id DESC
LIMIT 20;
```

Failed stages:

```sql
SELECT pipeline_run_id, pipeline_name, started_at, error_message
FROM ops.pipeline_runs
WHERE status = 'failed'
ORDER BY started_at DESC;
```

Quality checks for a run:

```sql
SELECT check_name, check_status, observed_value, expected_value, details
FROM ops.data_quality_results
WHERE pipeline_run_id = :pipeline_run_id
ORDER BY check_name;
```

Recent daily metrics:

```sql
SELECT pipeline_run_id, finished_at, metrics
FROM ops.pipeline_runs
WHERE pipeline_name = 'daily_etl'
  AND status = 'succeeded'
ORDER BY finished_at DESC
LIMIT 7;
```

## Incident procedure

1. Open the failed GitHub Actions job and identify whether failure occurred before connection,
   during extraction, or in a named stage.
2. Find the parent and stage rows in `ops.pipeline_runs`.
3. Inspect quality results for the failed stage.
4. Check source availability, database connectivity, credential rotation, row-count movement,
   pending/due FX dates, and quarantine changes.
5. Reproduce with the individual local stage command against a safe database when needed.
6. Correct the root cause through a reviewed fix branch.
7. Manually dispatch the end-to-end workflow; do not modify mart tables by hand.
8. Confirm a successful parent run and successful freshness check.
9. Document cause, impact, detection gap, and prevention action.

## Production alerting

GitHub failures are visible in Actions and repository notifications. A production deployment
should additionally:

- deliver alerts to Slack/PagerDuty with environment, severity, run ID, stage, and error;
- alert on missing success, not only explicit failure;
- graph duration, row counts, rejection rate, pending FX, revenue, and freshness;
- define warning/error thresholds from historical behavior;
- suppress duplicate notifications while preserving escalation;
- assign an owner and documented on-call response;
- retain structured logs and correlate them with pipeline run IDs.

## Security and maintenance

- Database and source credentials are repository secrets.
- The Supabase Session pooler provides an IPv4-compatible hosted connection.
- Workflow permissions are read-only for repository contents.
- Concurrency prevents overlapping workflow executions.
- After the requested 3–5 day demonstration, disable the schedules or pause the hosted project
  to avoid unnecessary resource use.
