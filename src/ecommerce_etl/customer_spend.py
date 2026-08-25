from dataclasses import dataclass
from decimal import Decimal
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

PIPELINE_NAME = "customer_spend_mart"
DEFAULT_CUSTOMER_SPEND_SQL = (
    Path(__file__).resolve().parent / "sql" / "marts" / "refresh_customer_spend.sql"
)


class CustomerSpendQualityError(RuntimeError):
    """Raised when the customer-spend mart violates a critical invariant."""


@dataclass(frozen=True)
class CustomerSpendMetrics:
    completed_clean_lines: int
    mart_line_rows: int
    customer_rows: int
    complete_customers: int
    incomplete_customers: int
    identity_fx_lines: int
    exact_fx_lines: int
    prior_fx_lines: int
    pending_fx_lines: int
    unavailable_due_lines: int
    negative_amount_lines: int
    customer_email_conflicts: int
    total_resolved_spend_eur: Decimal
    revenue_reconciliation_difference: Decimal

    def as_dict(self) -> dict[str, int | str]:
        return {
            "completed_clean_lines": self.completed_clean_lines,
            "mart_line_rows": self.mart_line_rows,
            "customer_rows": self.customer_rows,
            "complete_customers": self.complete_customers,
            "incomplete_customers": self.incomplete_customers,
            "identity_fx_lines": self.identity_fx_lines,
            "exact_fx_lines": self.exact_fx_lines,
            "prior_fx_lines": self.prior_fx_lines,
            "pending_fx_lines": self.pending_fx_lines,
            "unavailable_due_lines": self.unavailable_due_lines,
            "negative_amount_lines": self.negative_amount_lines,
            "customer_email_conflicts": self.customer_email_conflicts,
            "total_resolved_spend_eur": str(self.total_resolved_spend_eur),
            "revenue_reconciliation_difference": str(self.revenue_reconciliation_difference),
        }


def validate_customer_spend_metrics(metrics: CustomerSpendMetrics) -> None:
    if metrics.mart_line_rows != metrics.completed_clean_lines:
        raise CustomerSpendQualityError("Mart lines do not reconcile to completed clean lines")
    if metrics.complete_customers + metrics.incomplete_customers != metrics.customer_rows:
        raise CustomerSpendQualityError("Customer completeness states do not reconcile")
    if metrics.unavailable_due_lines != 0:
        raise CustomerSpendQualityError("A due RON line has no usable FX rate")
    fx_method_rows = (
        metrics.identity_fx_lines
        + metrics.exact_fx_lines
        + metrics.prior_fx_lines
        + metrics.pending_fx_lines
        + metrics.unavailable_due_lines
    )
    if fx_method_rows != metrics.mart_line_rows:
        raise CustomerSpendQualityError("FX method states do not reconcile to mart lines")
    if metrics.negative_amount_lines != 0:
        raise CustomerSpendQualityError("Converted line amounts must not be negative")
    if metrics.customer_email_conflicts != 0:
        raise CustomerSpendQualityError("A customer ID maps to multiple email addresses")
    if metrics.revenue_reconciliation_difference != Decimal("0"):
        raise CustomerSpendQualityError("Customer totals do not reconcile to converted lines")


def refresh_customer_spend(settings: Settings | None = None) -> dict[str, Any]:
    """Refresh EUR line conversions and per-customer totals transactionally."""

    active_settings = settings or get_settings()
    pipeline_run_id = start_pipeline_run(PIPELINE_NAME, active_settings)

    try:
        metrics = _refresh_customer_spend(pipeline_run_id, active_settings)
        result: dict[str, Any] = {"pipeline_run_id": pipeline_run_id, **metrics.as_dict()}
        succeed_pipeline_run(pipeline_run_id, result, active_settings)
        return result
    except Exception as error:
        fail_pipeline_run(pipeline_run_id, error, active_settings)
        raise


def _refresh_customer_spend(
    pipeline_run_id: int,
    settings: Settings,
) -> CustomerSpendMetrics:
    transformation_sql = DEFAULT_CUSTOMER_SPEND_SQL.read_text(encoding="utf-8")

    with database_connection(settings) as connection:
        connection.execute(transformation_sql)
        row = connection.execute(_METRICS_SQL).fetchone()
        if row is None:
            raise RuntimeError("Customer-spend metrics query returned no result")

        metrics = CustomerSpendMetrics(
            completed_clean_lines=int(row["completed_clean_lines"]),
            mart_line_rows=int(row["mart_line_rows"]),
            customer_rows=int(row["customer_rows"]),
            complete_customers=int(row["complete_customers"]),
            incomplete_customers=int(row["incomplete_customers"]),
            identity_fx_lines=int(row["identity_fx_lines"]),
            exact_fx_lines=int(row["exact_fx_lines"]),
            prior_fx_lines=int(row["prior_fx_lines"]),
            pending_fx_lines=int(row["pending_fx_lines"]),
            unavailable_due_lines=int(row["unavailable_due_lines"]),
            negative_amount_lines=int(row["negative_amount_lines"]),
            customer_email_conflicts=int(row["customer_email_conflicts"]),
            total_resolved_spend_eur=Decimal(row["total_resolved_spend_eur"]),
            revenue_reconciliation_difference=Decimal(row["revenue_reconciliation_difference"]),
        )
        _write_quality_results(connection, pipeline_run_id, metrics)
        validate_customer_spend_metrics(metrics)

    return metrics


def _write_quality_results(
    connection: Connection[Any],
    pipeline_run_id: int,
    metrics: CustomerSpendMetrics,
) -> None:
    checks: list[tuple[str, int | Decimal, int | Decimal]] = [
        (
            "customer_spend_line_reconciliation",
            metrics.mart_line_rows,
            metrics.completed_clean_lines,
        ),
        (
            "customer_spend_customer_state_reconciliation",
            metrics.complete_customers + metrics.incomplete_customers,
            metrics.customer_rows,
        ),
        (
            "customer_spend_fx_method_reconciliation",
            metrics.identity_fx_lines
            + metrics.exact_fx_lines
            + metrics.prior_fx_lines
            + metrics.pending_fx_lines
            + metrics.unavailable_due_lines,
            metrics.mart_line_rows,
        ),
        ("customer_spend_due_fx_coverage", metrics.unavailable_due_lines, 0),
        ("customer_spend_non_negative_amounts", metrics.negative_amount_lines, 0),
        ("customer_spend_email_consistency", metrics.customer_email_conflicts, 0),
        (
            "customer_spend_revenue_reconciliation",
            metrics.revenue_reconciliation_difference,
            Decimal("0"),
        ),
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
        (SELECT COUNT(*) FROM core.orders_clean WHERE status = 'completed')
            AS completed_clean_lines,
        (SELECT COUNT(*) FROM mart.order_lines_eur) AS mart_line_rows,
        (SELECT COUNT(*) FROM mart.customer_spend_eur) AS customer_rows,
        (SELECT COUNT(*) FROM mart.customer_spend_eur WHERE is_complete)
            AS complete_customers,
        (SELECT COUNT(*) FROM mart.customer_spend_eur WHERE NOT is_complete)
            AS incomplete_customers,
        (SELECT COUNT(*) FROM mart.order_lines_eur WHERE fx_rate_method = 'identity')
            AS identity_fx_lines,
        (SELECT COUNT(*) FROM mart.order_lines_eur WHERE fx_rate_method = 'exact')
            AS exact_fx_lines,
        (SELECT COUNT(*) FROM mart.order_lines_eur WHERE fx_rate_method = 'prior')
            AS prior_fx_lines,
        (SELECT COUNT(*) FROM mart.order_lines_eur WHERE fx_rate_method = 'pending')
            AS pending_fx_lines,
        (SELECT COUNT(*) FROM mart.order_lines_eur WHERE fx_rate_method = 'unavailable')
            AS unavailable_due_lines,
        (SELECT COUNT(*) FROM mart.order_lines_eur WHERE amount_eur < 0)
            AS negative_amount_lines,
        (
            SELECT COUNT(*)
            FROM (
                SELECT customer_id
                FROM mart.order_lines_eur
                GROUP BY customer_id
                HAVING COUNT(DISTINCT customer_email) > 1
            ) AS conflicts
        ) AS customer_email_conflicts,
        COALESCE((SELECT SUM(amount_eur) FROM mart.order_lines_eur), 0)
            AS total_resolved_spend_eur,
        ABS(
            COALESCE((SELECT SUM(amount_eur) FROM mart.order_lines_eur), 0)
            - COALESCE((SELECT SUM(total_spent_eur) FROM mart.customer_spend_eur), 0)
        ) AS revenue_reconciliation_difference
"""
