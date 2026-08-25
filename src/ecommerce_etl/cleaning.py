from dataclasses import dataclass
from pathlib import Path
from typing import Any

from psycopg import Connection

from ecommerce_etl.config import Settings, get_settings
from ecommerce_etl.database import database_connection
from ecommerce_etl.pipeline_runs import (
    fail_pipeline_run,
    start_pipeline_run,
    succeed_pipeline_run,
)

PIPELINE_NAME = "orders_cleaning"
DEFAULT_CLEANING_SQL = (
    Path(__file__).resolve().parent / "sql" / "transformations" / "clean_orders.sql"
)


class DataQualityError(RuntimeError):
    """Raised when a critical post-cleaning invariant fails."""


@dataclass(frozen=True)
class CleaningMetrics:
    raw_rows: int
    clean_rows: int
    rejected_rows: int
    completed_rows: int
    refunded_rows: int
    duplicate_rejections: int
    test_rejections: int
    invalid_quantity_rejections: int
    invalid_price_rejections: int
    price_outlier_rejections: int
    customer_id_repairs: int
    customer_surrogate_repairs: int
    category_repairs: int
    sku_repairs: int
    timestamp_repairs: int
    invalid_clean_rows: int
    duplicate_clean_payloads: int

    def as_dict(self) -> dict[str, int]:
        return {
            "raw_rows": self.raw_rows,
            "clean_rows": self.clean_rows,
            "rejected_rows": self.rejected_rows,
            "completed_rows": self.completed_rows,
            "refunded_rows": self.refunded_rows,
            "duplicate_rejections": self.duplicate_rejections,
            "test_rejections": self.test_rejections,
            "invalid_quantity_rejections": self.invalid_quantity_rejections,
            "invalid_price_rejections": self.invalid_price_rejections,
            "price_outlier_rejections": self.price_outlier_rejections,
            "customer_id_repairs": self.customer_id_repairs,
            "customer_surrogate_repairs": self.customer_surrogate_repairs,
            "category_repairs": self.category_repairs,
            "sku_repairs": self.sku_repairs,
            "timestamp_repairs": self.timestamp_repairs,
            "invalid_clean_rows": self.invalid_clean_rows,
            "duplicate_clean_payloads": self.duplicate_clean_payloads,
        }


def validate_cleaning_metrics(metrics: CleaningMetrics) -> None:
    if metrics.clean_rows + metrics.rejected_rows != metrics.raw_rows:
        raise DataQualityError("Clean and rejected rows do not reconcile to raw rows")
    if metrics.invalid_clean_rows != 0:
        raise DataQualityError("Clean table contains rows that violate required-field rules")
    if metrics.duplicate_clean_payloads != 0:
        raise DataQualityError("Clean table contains duplicate source payloads")


def clean_orders(settings: Settings | None = None) -> dict[str, int]:
    """Refresh clean/quarantine tables transactionally and enforce quality invariants."""

    active_settings = settings or get_settings()
    pipeline_run_id = start_pipeline_run(PIPELINE_NAME, active_settings)

    try:
        metrics = _refresh_clean_orders(pipeline_run_id, active_settings)
        result = {"pipeline_run_id": pipeline_run_id, **metrics.as_dict()}
        succeed_pipeline_run(pipeline_run_id, result, active_settings)
        return result
    except Exception as error:
        fail_pipeline_run(pipeline_run_id, error, active_settings)
        raise


def _refresh_clean_orders(pipeline_run_id: int, settings: Settings) -> CleaningMetrics:
    transformation_sql = DEFAULT_CLEANING_SQL.read_text(encoding="utf-8")

    with database_connection(settings) as connection:
        connection.execute(transformation_sql)
        row = connection.execute(_METRICS_SQL).fetchone()
        if row is None:
            raise RuntimeError("Cleaning metrics query returned no result")

        metrics = CleaningMetrics(
            raw_rows=int(row["raw_rows"]),
            clean_rows=int(row["clean_rows"]),
            rejected_rows=int(row["rejected_rows"]),
            completed_rows=int(row["completed_rows"]),
            refunded_rows=int(row["refunded_rows"]),
            duplicate_rejections=int(row["duplicate_rejections"]),
            test_rejections=int(row["test_rejections"]),
            invalid_quantity_rejections=int(row["invalid_quantity_rejections"]),
            invalid_price_rejections=int(row["invalid_price_rejections"]),
            price_outlier_rejections=int(row["price_outlier_rejections"]),
            customer_id_repairs=int(row["customer_id_repairs"]),
            customer_surrogate_repairs=int(row["customer_surrogate_repairs"]),
            category_repairs=int(row["category_repairs"]),
            sku_repairs=int(row["sku_repairs"]),
            timestamp_repairs=int(row["timestamp_repairs"]),
            invalid_clean_rows=int(row["invalid_clean_rows"]),
            duplicate_clean_payloads=int(row["duplicate_clean_payloads"]),
        )
        _write_quality_results(connection, pipeline_run_id, metrics)
        validate_cleaning_metrics(metrics)

    return metrics


def _write_quality_results(
    connection: Connection[Any],
    pipeline_run_id: int,
    metrics: CleaningMetrics,
) -> None:
    checks = [
        (
            "orders_row_reconciliation",
            metrics.clean_rows + metrics.rejected_rows,
            metrics.raw_rows,
        ),
        ("orders_clean_required_fields", metrics.invalid_clean_rows, 0),
        ("orders_clean_duplicate_payloads", metrics.duplicate_clean_payloads, 0),
    ]

    for check_name, observed, expected in checks:
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


_METRICS_SQL = """
    SELECT
        (SELECT COUNT(*) FROM raw.orders_raw) AS raw_rows,
        (SELECT COUNT(*) FROM core.orders_clean) AS clean_rows,
        (SELECT COUNT(*) FROM quarantine.orders_rejected) AS rejected_rows,
        (SELECT COUNT(*) FROM core.orders_clean WHERE status = 'completed') AS completed_rows,
        (SELECT COUNT(*) FROM core.orders_clean WHERE status = 'refunded') AS refunded_rows,
        (SELECT COUNT(*) FROM quarantine.orders_rejected
            WHERE 'exact_duplicate' = ANY(rejection_reasons)) AS duplicate_rejections,
        (SELECT COUNT(*) FROM quarantine.orders_rejected
            WHERE 'test_order' = ANY(rejection_reasons)) AS test_rejections,
        (SELECT COUNT(*) FROM quarantine.orders_rejected
            WHERE 'invalid_quantity' = ANY(rejection_reasons)) AS invalid_quantity_rejections,
        (SELECT COUNT(*) FROM quarantine.orders_rejected
            WHERE 'invalid_unit_price' = ANY(rejection_reasons)) AS invalid_price_rejections,
        (SELECT COUNT(*) FROM quarantine.orders_rejected
            WHERE 'implausible_unit_price_outlier' = ANY(rejection_reasons))
            AS price_outlier_rejections,
        (SELECT COUNT(*) FROM core.orders_clean
            WHERE 'customer_id_from_email' = ANY(data_repairs)) AS customer_id_repairs,
        (SELECT COUNT(*) FROM core.orders_clean
            WHERE 'customer_id_surrogate_from_email' = ANY(data_repairs))
            AS customer_surrogate_repairs,
        (SELECT COUNT(*) FROM core.orders_clean
            WHERE 'category_from_product_catalog' = ANY(data_repairs)) AS category_repairs,
        (SELECT COUNT(*) FROM core.orders_clean
            WHERE 'sku_from_product_catalog' = ANY(data_repairs)) AS sku_repairs,
        (SELECT COUNT(*) FROM core.orders_clean
            WHERE 'timestamp_from_unix_seconds' = ANY(data_repairs)
               OR 'timestamp_from_day_first' = ANY(data_repairs)) AS timestamp_repairs,
        (SELECT COUNT(*) FROM core.orders_clean
            WHERE customer_id IS NULL
               OR quantity <= 0
               OR unit_price <= 0
               OR order_ts IS NULL
               OR fx_reference_date IS NULL) AS invalid_clean_rows,
        (SELECT COUNT(*) - COUNT(DISTINCT source_record_hash)
            FROM core.orders_clean) AS duplicate_clean_payloads
"""
