from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from psycopg import Connection

from ecommerce_etl.clients.frankfurter_client import FrankfurterClient
from ecommerce_etl.config import Settings, get_settings
from ecommerce_etl.database import database_connection
from ecommerce_etl.loaders.fx_loader import FxLoadMetrics, load_fx_rates
from ecommerce_etl.pipeline_runs import (
    fail_pipeline_run,
    start_pipeline_run,
    succeed_pipeline_run,
)

PIPELINE_NAME = "fx_ingestion"
SOURCE_CURRENCY = "RON"
TARGET_CURRENCY = "EUR"


class FxCoverageError(RuntimeError):
    """Raised when a due FX reference date cannot use any available rate."""


@dataclass(frozen=True)
class FxRequirements:
    minimum_date: date | None
    maximum_date: date | None
    required_dates: int


@dataclass(frozen=True)
class FxCoverageMetrics:
    required_dates: int
    due_dates: int
    covered_due_dates: int
    unavailable_due_dates: int
    pending_future_dates: int
    non_positive_stored_rates: int


def build_fetch_window(
    requirements: FxRequirements,
    as_of_date: date,
    lookback_days: int,
) -> tuple[date, date] | None:
    """Return a due-date range plus lookback, excluding future-only requirements."""

    if requirements.minimum_date is None or requirements.maximum_date is None:
        return None
    if requirements.minimum_date > as_of_date:
        return None

    return (
        requirements.minimum_date - timedelta(days=lookback_days),
        min(requirements.maximum_date, as_of_date),
    )


def validate_fx_coverage(metrics: FxCoverageMetrics) -> None:
    if metrics.unavailable_due_dates != 0:
        raise FxCoverageError("At least one due FX reference date has no usable prior rate")
    if metrics.non_positive_stored_rates != 0:
        raise FxCoverageError("Stored FX rates must all be positive")


def ingest_fx_rates(
    settings: Settings | None = None,
    client: FrankfurterClient | None = None,
    as_of_date: date | None = None,
) -> dict[str, Any]:
    """Fetch available RON/EUR rates and report future dates as pending."""

    active_settings = settings or get_settings()
    effective_date = as_of_date or datetime.now(UTC).date()
    pipeline_run_id = start_pipeline_run(PIPELINE_NAME, active_settings)

    try:
        requirements = _read_fx_requirements(active_settings)
        window = build_fetch_window(
            requirements,
            effective_date,
            active_settings.fx_lookback_days,
        )
        rates = (
            (client or FrankfurterClient(active_settings)).fetch_rates(
                window[0],
                window[1],
                SOURCE_CURRENCY,
                TARGET_CURRENCY,
            )
            if window is not None
            else []
        )
        load_metrics = load_fx_rates(rates, active_settings)
        coverage = _read_fx_coverage(effective_date, active_settings)
        _write_quality_results(pipeline_run_id, coverage, active_settings)
        validate_fx_coverage(coverage)

        result = _build_result(
            pipeline_run_id,
            effective_date,
            window,
            load_metrics,
            coverage,
        )
        succeed_pipeline_run(pipeline_run_id, result, active_settings)
        return result
    except Exception as error:
        fail_pipeline_run(pipeline_run_id, error, active_settings)
        raise


def _read_fx_requirements(settings: Settings) -> FxRequirements:
    with database_connection(settings) as connection:
        row = connection.execute(
            """
            SELECT
                MIN(fx_reference_date) AS minimum_date,
                MAX(fx_reference_date) AS maximum_date,
                COUNT(DISTINCT fx_reference_date) AS required_dates
            FROM core.orders_clean
            WHERE currency = %s
            """,
            (SOURCE_CURRENCY,),
        ).fetchone()

    if row is None:
        raise RuntimeError("FX requirements query returned no result")

    minimum_date = row["minimum_date"]
    maximum_date = row["maximum_date"]
    return FxRequirements(
        minimum_date=minimum_date if isinstance(minimum_date, date) else None,
        maximum_date=maximum_date if isinstance(maximum_date, date) else None,
        required_dates=int(row["required_dates"]),
    )


def _read_fx_coverage(as_of_date: date, settings: Settings) -> FxCoverageMetrics:
    with database_connection(settings) as connection:
        row = connection.execute(
            _COVERAGE_SQL,
            {
                "as_of_date": as_of_date,
                "source_currency": SOURCE_CURRENCY,
                "target_currency": TARGET_CURRENCY,
            },
        ).fetchone()

    if row is None:
        raise RuntimeError("FX coverage query returned no result")

    return FxCoverageMetrics(
        required_dates=int(row["required_dates"]),
        due_dates=int(row["due_dates"]),
        covered_due_dates=int(row["covered_due_dates"]),
        unavailable_due_dates=int(row["unavailable_due_dates"]),
        pending_future_dates=int(row["pending_future_dates"]),
        non_positive_stored_rates=int(row["non_positive_stored_rates"]),
    )


def _write_quality_results(
    pipeline_run_id: int,
    metrics: FxCoverageMetrics,
    settings: Settings,
) -> None:
    checks = [
        ("fx_due_date_coverage", metrics.unavailable_due_dates, 0),
        ("fx_rates_positive", metrics.non_positive_stored_rates, 0),
    ]

    with database_connection(settings) as connection:
        for check_name, observed, expected in checks:
            _insert_quality_result(connection, pipeline_run_id, check_name, observed, expected)


def _insert_quality_result(
    connection: Connection[Any],
    pipeline_run_id: int,
    check_name: str,
    observed: int,
    expected: int,
) -> None:
    connection.execute(
        """
        INSERT INTO ops.data_quality_results (
            pipeline_run_id,
            check_name,
            check_status,
            observed_value,
            expected_value
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            pipeline_run_id,
            check_name,
            "passed" if observed == expected else "failed",
            observed,
            str(expected),
        ),
    )


def _build_result(
    pipeline_run_id: int,
    as_of_date: date,
    window: tuple[date, date] | None,
    load_metrics: FxLoadMetrics,
    coverage: FxCoverageMetrics,
) -> dict[str, Any]:
    return {
        "pipeline_run_id": pipeline_run_id,
        "as_of_date": as_of_date.isoformat(),
        "fetch_start_date": window[0].isoformat() if window else None,
        "fetch_end_date": window[1].isoformat() if window else None,
        "fetched_rates": load_metrics.fetched_rates,
        "inserted_rates": load_metrics.inserted_rates,
        "updated_rates": load_metrics.updated_rates,
        "stored_rates": load_metrics.stored_rates,
        "required_dates": coverage.required_dates,
        "due_dates": coverage.due_dates,
        "covered_due_dates": coverage.covered_due_dates,
        "unavailable_due_dates": coverage.unavailable_due_dates,
        "pending_future_dates": coverage.pending_future_dates,
        "non_positive_stored_rates": coverage.non_positive_stored_rates,
    }


_COVERAGE_SQL = """
    WITH required_dates AS (
        SELECT DISTINCT fx_reference_date
        FROM core.orders_clean
        WHERE currency = %(source_currency)s
    ),
    coverage AS (
        SELECT
            fx_reference_date,
            fx_reference_date <= %(as_of_date)s AS is_due,
            EXISTS (
                SELECT 1
                FROM reference.fx_rates AS rates
                WHERE rates.source_currency = %(source_currency)s
                  AND rates.target_currency = %(target_currency)s
                  AND rates.rate_date <= required_dates.fx_reference_date
            ) AS has_usable_rate
        FROM required_dates
    )
    SELECT
        COUNT(*) AS required_dates,
        COUNT(*) FILTER (WHERE is_due) AS due_dates,
        COUNT(*) FILTER (WHERE is_due AND has_usable_rate) AS covered_due_dates,
        COUNT(*) FILTER (WHERE is_due AND NOT has_usable_rate) AS unavailable_due_dates,
        COUNT(*) FILTER (WHERE NOT is_due) AS pending_future_dates,
        (
            SELECT COUNT(*)
            FROM reference.fx_rates
            WHERE source_currency = %(source_currency)s
              AND target_currency = %(target_currency)s
              AND rate <= 0
        ) AS non_positive_stored_rates
    FROM coverage
"""
