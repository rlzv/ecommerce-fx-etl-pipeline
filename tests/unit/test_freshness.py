from dataclasses import replace

import pytest

from ecommerce_etl.freshness import FreshnessError, FreshnessMetrics, validate_freshness


def valid_metrics() -> FreshnessMetrics:
    return FreshnessMetrics(
        latest_daily_run_id=100,
        latest_daily_status="succeeded",
        latest_successful_run_id=100,
        hours_since_success=1.0,
        failed_runs_since_success=0,
        raw_rows=9268,
        clean_rows=8787,
        customer_rows=1868,
        country_rows=2,
        customer_mart_age_hours=1.1,
        country_mart_age_hours=1.0,
    )


def test_valid_freshness_metrics_pass() -> None:
    validate_freshness(valid_metrics(), max_age_hours=26)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"latest_successful_run_id": None}, "No successful"),
        ({"latest_daily_status": "failed"}, "latest daily ETL attempt"),
        ({"failed_runs_since_success": 1}, "failure occurred"),
        ({"hours_since_success": 27.0}, "daily ETL run is stale"),
        ({"raw_rows": 0}, "orders are unexpectedly empty"),
        ({"customer_rows": 0}, "mart is unexpectedly empty"),
        ({"customer_mart_age_hours": None}, "customer mart has no"),
        ({"country_mart_age_hours": None}, "country revenue mart has no"),
        ({"customer_mart_age_hours": 27.0}, "customer mart is stale"),
        ({"country_mart_age_hours": 27.0}, "country revenue mart is stale"),
    ],
)
def test_invalid_freshness_metrics_fail(
    updates: dict[str, object],
    message: str,
) -> None:
    metrics = replace(valid_metrics(), **updates)

    with pytest.raises(FreshnessError, match=message):
        validate_freshness(metrics, max_age_hours=26)


def test_non_positive_max_age_fails() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        validate_freshness(valid_metrics(), max_age_hours=0)
