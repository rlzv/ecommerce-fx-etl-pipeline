from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from ecommerce_etl.cleaning import clean_orders
from ecommerce_etl.config import Settings, get_settings
from ecommerce_etl.country_revenue import refresh_country_revenue
from ecommerce_etl.customer_spend import refresh_customer_spend
from ecommerce_etl.database import database_connection
from ecommerce_etl.fx_ingestion import ingest_fx_rates
from ecommerce_etl.ingestion import ingest_orders
from ecommerce_etl.migrations import apply_migrations
from ecommerce_etl.pipeline_runs import (
    fail_pipeline_run,
    start_pipeline_run,
    succeed_pipeline_run,
)

PIPELINE_NAME = "daily_etl"


class PipelineAlreadyRunningError(RuntimeError):
    """Raised when another end-to-end pipeline holds the database lock."""


def run_pipeline(settings: Settings | None = None) -> dict[str, Any]:
    """Run every ETL stage in dependency order and fail fast on any error."""

    active_settings = settings or get_settings()
    applied_migrations = apply_migrations(active_settings)

    with _pipeline_lock(active_settings):
        pipeline_run_id = start_pipeline_run(PIPELINE_NAME, active_settings)
        try:
            stage_metrics = _run_stages(active_settings)
            result: dict[str, Any] = {
                "pipeline_run_id": pipeline_run_id,
                "applied_migrations": applied_migrations,
                "stages": stage_metrics,
            }
            succeed_pipeline_run(pipeline_run_id, result, active_settings)
            return result
        except Exception as error:
            fail_pipeline_run(pipeline_run_id, error, active_settings)
            raise


def _run_stages(settings: Settings) -> dict[str, dict[str, Any]]:
    return {
        "orders_ingestion": ingest_orders(settings),
        "orders_cleaning": clean_orders(settings),
        "fx_ingestion": ingest_fx_rates(settings),
        "customer_spend_mart": refresh_customer_spend(settings),
        "country_category_revenue_mart": refresh_country_revenue(settings),
    }


@contextmanager
def _pipeline_lock(settings: Settings) -> Iterator[None]:
    with database_connection(settings) as connection:
        row = connection.execute(
            "SELECT pg_try_advisory_xact_lock(hashtext('ecommerce_etl_daily_pipeline')) AS acquired"
        ).fetchone()
        if row is None or not bool(row["acquired"]):
            raise PipelineAlreadyRunningError("Another daily ETL pipeline is already running")
        yield
