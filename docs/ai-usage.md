# AI usage disclosure

## Tools used

ChatGPT/Codex was used as an AI-assisted engineering collaborator for:

- architecture and schema discussion;
- Python and SQL boilerplate generation;
- review of transformations and edge cases;
- test-case and monitoring suggestions;
- Git branch, pull-request, and validation workflow guidance;
- documentation editing.

No AI model is called by the ETL pipeline at runtime.

## What I kept

- Layered PostgreSQL schemas for raw, reference, core, quarantine, mart, and operations data.
- Plain SQL transformations so cleaning and analytical logic remain visible to reviewers.
- Python clients/loaders for API concerns, retries, orchestration, and metrics.
- Idempotent source and FX loading.
- Explicit rejection and repair arrays.
- A shared line-level EUR conversion table used by both analytical outputs.
- Versioned migrations, unit tests, CI, daily automation, and independent monitoring.

## What I changed or rejected

- I rejected deduplication by `order_id` after verifying that orders legitimately contain several
  product lines.
- I added a flagged deterministic customer surrogate for one recoverable row that had no source
  ID or mapping.
- I kept future FX reference dates pending rather than applying today's rate.
- The first positive-price rule missed 13 `999999` values. After reviewing mart totals and price
  distributions, I added a product/currency median-based threshold and rebuilt both marts.
- I adjusted expected row counts to the executed data rather than trusting initial estimates.
- I moved independent freshness monitoring from 07:00 to 09:00 UTC after identifying that the
  earlier time could allow a silently missed trigger to pass the 26-hour rule.
- I selected the Supabase Session pooler after considering GitHub-hosted runner IPv4 support.

## Human validation and ownership

I executed all migrations and commands, inspected source profiles and SQL samples, compared
consecutive idempotent runs, reviewed Git changes, verified every quality check, and tested the
complete pipeline against local and hosted PostgreSQL databases. I managed feature/fix branches
and pull requests and made the final decisions about data validity, FX behavior, monitoring, and
documentation.

AI output was treated as a draft requiring execution and review. The missed positive outliers
and the monitor timing correction are examples where downstream evidence and manual reasoning
changed the initial implementation.

## Short disclosure for submission

> I used ChatGPT/Codex to assist with architecture discussion, boilerplate, SQL/Python review,
> test ideas, edge-case analysis, Git workflow guidance, and documentation. I retained the
> layered database design, auditable SQL transformations, idempotent loaders, and automated test
> structure. I changed the duplicate identity, missing-customer handling, future-FX policy,
> positive-price outlier rule, freshness schedule, and hosted connection approach based on
> profiling and executed results. I personally ran and reviewed all migrations, tests, pipeline
> outputs, data-quality checks, hosted validation, commits, and pull requests. No AI is used by
> the runtime pipeline.
