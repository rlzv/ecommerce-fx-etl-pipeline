# Data quality

## Reconciliation summary

| State | Rows |
|---|---:|
| Raw | 9,268 |
| Clean | 8,787 |
| Quarantined | 481 |
| Clean + quarantined | 9,268 |
| Completed clean | 8,389 |
| Refunded clean | 398 |
| Duplicate clean payloads | 0 |
| Clean required-field violations | 0 |

## Rejections

| Reason | Rows containing reason | Decision |
|---|---:|---|
| `exact_duplicate` | 183 | Keep first identical payload; quarantine later occurrences |
| `test_order` | 101 | Preserve in quarantine; exclude from production analytics |
| `invalid_quantity` | 167 | Reject null, fractional, zero, or negative quantities |
| `invalid_unit_price` | 24 | Reject null, zero, or negative prices |
| `implausible_unit_price_outlier` | 13 | Reject prices above ten times the product/currency median |

Reason counts are not mutually exclusive because one row can violate several rules. Therefore,
the reason counts sum to more than the 481 quarantined physical rows.

The positive-price outliers were discovered after the first customer mart produced totals near
EUR 1 million for several customers. Profiling by product and currency showed `999999` against
normal medians between approximately 20 and 190. The implemented rule does not hardcode the
observed value. It calculates a baseline from positive, non-test, first-occurrence rows and uses:

```text
unit_price > 10 × median_unit_price
```

This rejected 13 rows and reduced resolved revenue from EUR 9,273,443.45 to EUR 702,602.02. The
maximum clean unit price is 207.87.

## Repairs retained in clean data

| Repair | Clean rows | Rule |
|---|---:|---|
| Customer ID from email | 93 | Use only an email with exactly one known source customer ID |
| Customer surrogate from email | 1 | Flagged deterministic surrogate when no ID exists anywhere |
| Category from product catalog | 76 | Replace missing/inconsistent value with canonical category |
| SKU from product catalog | 212 | Replace missing/malformed value with canonical SKU |
| Unix/day-first timestamp | 3,486 | Parse explicitly and store as UTC `TIMESTAMPTZ` |

Repairs are recorded in the `data_repairs` text array. Rejections preserve the original JSONB,
so every decision can be reviewed without reconstructing source state.

## Important rules

### Duplicate identity

`order_id` is not unique per line because a single order can contain multiple products. Exact
canonical payload equality plus occurrence number is therefore the safe duplicate rule.

### Customer identity

Email recovery is allowed only when the normalized email maps to one known customer ID. The one
email with no source ID receives an `EMAIL-...` surrogate and an explicit repair flag rather
than being silently discarded. In production, this should move to a governed identity table and
use a keyed HMAC rather than an unkeyed deterministic digest.

### Refunds

Refunded rows are valid operational records and remain in `core.orders_clean`. Revenue marts
filter to completed lines. This separates data validity from analytical inclusion.

### FX dates

Future FX dates are intentional simulation data, not invalid dates. They remain pending. A past
date uses an exact rate when available or the latest prior date for non-publishing days. A due
date with no usable rate fails the FX quality check instead of silently dropping revenue.

## Automated checks

Checks written to `ops.data_quality_results` include:

- raw/clean/quarantine reconciliation;
- required clean fields and duplicate clean hashes;
- due FX coverage and positive stored rates;
- completed-line and FX-method reconciliation;
- non-negative EUR amounts and customer-email consistency;
- line-to-customer revenue reconciliation;
- category-to-country and source-to-mart reconciliation;
- EUR 40,000 threshold and deterministic rank sequence.

## Limitations and production extensions

- Median thresholds are robust for this stable product catalog. Production should version
  thresholds, enforce minimum group sizes, monitor drift, and route borderline rows for review.
- Country codes are syntactically validated as two uppercase characters; production should use
  an ISO reference dimension.
- Email syntax validation is deliberately lightweight and does not prove deliverability.
- Full refresh is simple and reliable here; high-volume data needs incremental checks and
  partition-level reconciliation.
- Static expected mart non-emptiness is valid for this exercise. If business data can legitimately
  produce zero qualifying countries, monitoring should use a configurable contract instead.
