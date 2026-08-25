from dataclasses import dataclass
from typing import Any

from ecommerce_etl.config import Settings, get_settings
from ecommerce_etl.database import database_connection
from ecommerce_etl.pipeline_runs import (
    fail_pipeline_run,
    start_pipeline_run,
    succeed_pipeline_run,
)

PIPELINE_NAME = "freshness_monitor"
MONITORED_PIPELINE_NAME = "daily_etl"
DEFAULT_MAX_AGE_HOURS = 26.0


class FreshnessError(RuntimeError):
    """Raised when pipeline or mart freshness is outside the accepted limits."""


@dataclass(frozen=True)
class FreshnessMetrics:
    latest_daily_run_id: int | None
    latest_daily_status: str | None
    latest_successful_run_id: int | None
    hours_since_success: float | None
    failed_runs_since_success: int
    raw_rows: int
    clean_rows: int
    customer_rows: int
    country_rows: int
    customer_mart_age_hours: float | None
    country_mart_age_hours: float | None

    def as_dict(self) -> dict[str, int | float | str | None]:
        return {
            "latest_daily_run_id": self.latest_daily_run_id,
            "latest_daily_status": self.latest_daily_status,
            "latest_successful_run_id": self.latest_successful_run_id,
            "hours_since_success": self.hours_since_success,
            "failed_runs_since_success": self.failed_runs_since_success,
            "raw_rows": self.raw_rows,
            "clean_rows": self.clean_rows,
            "customer_rows": self.customer_rows,
            "country_rows": self.country_rows,
            "customer_mart_age_hours": self.customer_mart_age_hours,
            "country_mart_age_hours": self.country_mart_age_hours,
        }


def validate_freshness(metrics: FreshnessMetrics, max_age_hours: float) -> None:
    if max_age_hours <= 0:
        raise ValueError("max_age_hours must be positive")
    if metrics.latest_successful_run_id is None or metrics.hours_since_success is None:
        raise FreshnessError("No successful daily ETL run exists")
    if metrics.latest_daily_status != "succeeded":
        raise FreshnessError("The latest daily ETL attempt did not succeed")
    if metrics.failed_runs_since_success != 0:
        raise FreshnessError("A daily ETL failure occurred after the latest success")
    if metrics.hours_since_success > max_age_hours:
        raise FreshnessError("The latest successful daily ETL run is stale")
    if metrics.raw_rows <= 0 or metrics.clean_rows <= 0:
        raise FreshnessError("Raw or clean orders are unexpectedly empty")
    if metrics.customer_rows <= 0 or metrics.country_rows <= 0:
        raise FreshnessError("An analytical mart is unexpectedly empty")
    if metrics.customer_mart_age_hours is None:
        raise FreshnessError("The customer mart has no refresh timestamp")
    if metrics.country_mart_age_hours is None:
        raise FreshnessError("The country revenue mart has no refresh timestamp")
    if metrics.customer_mart_age_hours > max_age_hours:
        raise FreshnessError("The customer mart is stale")
    if metrics.country_mart_age_hours > max_age_hours:
        raise FreshnessError("The country revenue mart is stale")


def check_freshness(
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Check daily pipeline health independently and record the monitor outcome."""

    active_settings = settings or get_settings()
    pipeline_run_id = start_pipeline_run(PIPELINE_NAME, active_settings)

    try:
        metrics = _read_freshness_metrics(active_settings)
        validate_freshness(metrics, max_age_hours)
        result: dict[str, Any] = {
            "pipeline_run_id": pipeline_run_id,
            "max_age_hours": max_age_hours,
            **metrics.as_dict(),
        }
        succeed_pipeline_run(pipeline_run_id, result, active_settings)
        return result
    except Exception as error:
        fail_pipeline_run(pipeline_run_id, error, active_settings)
        raise


def _read_freshness_metrics(settings: Settings) -> FreshnessMetrics:
    with database_connection(settings) as connection:
        row = connection.execute(
            _FRESHNESS_SQL,
            {"pipeline_name": MONITORED_PIPELINE_NAME},
        ).fetchone()

    if row is None:
        raise RuntimeError("Freshness metrics query returned no result")

    return FreshnessMetrics(
        latest_daily_run_id=_optional_int(row["latest_daily_run_id"]),
        latest_daily_status=_optional_str(row["latest_daily_status"]),
        latest_successful_run_id=_optional_int(row["latest_successful_run_id"]),
        hours_since_success=_optional_float(row["hours_since_success"]),
        failed_runs_since_success=int(row["failed_runs_since_success"]),
        raw_rows=int(row["raw_rows"]),
        clean_rows=int(row["clean_rows"]),
        customer_rows=int(row["customer_rows"]),
        country_rows=int(row["country_rows"]),
        customer_mart_age_hours=_optional_float(row["customer_mart_age_hours"]),
        country_mart_age_hours=_optional_float(row["country_mart_age_hours"]),
    )


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _optional_float(value: Any) -> float | None:
    return round(float(value), 4) if value is not None else None


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


_FRESHNESS_SQL = """
    WITH latest_attempt AS (
        SELECT pipeline_run_id, status
        FROM ops.pipeline_runs
        WHERE pipeline_name = %(pipeline_name)s
        ORDER BY started_at DESC, pipeline_run_id DESC
        LIMIT 1
    ),
    latest_success AS (
        SELECT pipeline_run_id, finished_at
        FROM ops.pipeline_runs
        WHERE pipeline_name = %(pipeline_name)s
          AND status = 'succeeded'
        ORDER BY finished_at DESC, pipeline_run_id DESC
        LIMIT 1
    )
    SELECT
        (SELECT pipeline_run_id FROM latest_attempt) AS latest_daily_run_id,
        (SELECT status FROM latest_attempt) AS latest_daily_status,
        (SELECT pipeline_run_id FROM latest_success) AS latest_successful_run_id,
        EXTRACT(EPOCH FROM (
            NOW() - (SELECT finished_at FROM latest_success)
        )) / 3600 AS hours_since_success,
        (
            SELECT COUNT(*)
            FROM ops.pipeline_runs
            WHERE pipeline_name = %(pipeline_name)s
              AND status = 'failed'
              AND started_at > (SELECT finished_at FROM latest_success)
        ) AS failed_runs_since_success,
        (SELECT COUNT(*) FROM raw.orders_raw) AS raw_rows,
        (SELECT COUNT(*) FROM core.orders_clean) AS clean_rows,
        (SELECT COUNT(*) FROM mart.customer_spend_eur) AS customer_rows,
        (SELECT COUNT(*) FROM mart.country_category_revenue_eur) AS country_rows,
        EXTRACT(EPOCH FROM (
            NOW() - (SELECT MAX(refreshed_at) FROM mart.customer_spend_eur)
        )) / 3600 AS customer_mart_age_hours,
        EXTRACT(EPOCH FROM (
            NOW() - (SELECT MAX(refreshed_at) FROM mart.country_category_revenue_eur)
        )) / 3600 AS country_mart_age_hours
"""
