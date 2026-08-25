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

PIPELINE_NAME = "country_category_revenue_mart"
DEFAULT_COUNTRY_REVENUE_SQL = (
    Path(__file__).resolve().parents[2] / "sql" / "marts" / "refresh_country_category_revenue.sql"
)


class CountryRevenueQualityError(RuntimeError):
    """Raised when the country revenue mart violates a critical invariant."""


@dataclass(frozen=True)
class CountryRevenueMetrics:
    eligible_line_rows: int
    resolved_line_rows: int
    pending_fx_line_rows: int
    source_country_rows: int
    qualifying_country_rows: int
    complete_country_rows: int
    incomplete_country_rows: int
    threshold_violations: int
    rank_violations: int
    category_reconciliation_difference: Decimal
    source_reconciliation_difference: Decimal
    total_qualifying_revenue_eur: Decimal

    def as_dict(self) -> dict[str, int | str]:
        return {
            "eligible_line_rows": self.eligible_line_rows,
            "resolved_line_rows": self.resolved_line_rows,
            "pending_fx_line_rows": self.pending_fx_line_rows,
            "source_country_rows": self.source_country_rows,
            "qualifying_country_rows": self.qualifying_country_rows,
            "complete_country_rows": self.complete_country_rows,
            "incomplete_country_rows": self.incomplete_country_rows,
            "threshold_violations": self.threshold_violations,
            "rank_violations": self.rank_violations,
            "category_reconciliation_difference": str(self.category_reconciliation_difference),
            "source_reconciliation_difference": str(self.source_reconciliation_difference),
            "total_qualifying_revenue_eur": str(self.total_qualifying_revenue_eur),
        }


def validate_country_revenue_metrics(metrics: CountryRevenueMetrics) -> None:
    if metrics.resolved_line_rows + metrics.pending_fx_line_rows != metrics.eligible_line_rows:
        raise CountryRevenueQualityError("Eligible line states do not reconcile")
    if (
        metrics.complete_country_rows + metrics.incomplete_country_rows
        != metrics.qualifying_country_rows
    ):
        raise CountryRevenueQualityError("Country completeness states do not reconcile")
    if metrics.threshold_violations != 0:
        raise CountryRevenueQualityError("A mart row does not exceed the EUR 40,000 threshold")
    if metrics.rank_violations != 0:
        raise CountryRevenueQualityError("Country revenue ranks are not deterministic")
    if metrics.category_reconciliation_difference != Decimal("0"):
        raise CountryRevenueQualityError("Category revenue does not reconcile to country totals")
    if metrics.source_reconciliation_difference != Decimal("0"):
        raise CountryRevenueQualityError(
            "Mart revenue does not reconcile to qualifying source revenue"
        )


def refresh_country_revenue(settings: Settings | None = None) -> dict[str, Any]:
    """Refresh the ranked Books and Electronics revenue mart transactionally."""

    active_settings = settings or get_settings()
    pipeline_run_id = start_pipeline_run(PIPELINE_NAME, active_settings)

    try:
        metrics = _refresh_country_revenue(pipeline_run_id, active_settings)
        result: dict[str, Any] = {"pipeline_run_id": pipeline_run_id, **metrics.as_dict()}
        succeed_pipeline_run(pipeline_run_id, result, active_settings)
        return result
    except Exception as error:
        fail_pipeline_run(pipeline_run_id, error, active_settings)
        raise


def _refresh_country_revenue(
    pipeline_run_id: int,
    settings: Settings,
) -> CountryRevenueMetrics:
    transformation_sql = DEFAULT_COUNTRY_REVENUE_SQL.read_text(encoding="utf-8")

    with database_connection(settings) as connection:
        connection.execute(transformation_sql)
        row = connection.execute(_METRICS_SQL).fetchone()
        if row is None:
            raise RuntimeError("Country revenue metrics query returned no result")

        metrics = CountryRevenueMetrics(
            eligible_line_rows=int(row["eligible_line_rows"]),
            resolved_line_rows=int(row["resolved_line_rows"]),
            pending_fx_line_rows=int(row["pending_fx_line_rows"]),
            source_country_rows=int(row["source_country_rows"]),
            qualifying_country_rows=int(row["qualifying_country_rows"]),
            complete_country_rows=int(row["complete_country_rows"]),
            incomplete_country_rows=int(row["incomplete_country_rows"]),
            threshold_violations=int(row["threshold_violations"]),
            rank_violations=int(row["rank_violations"]),
            category_reconciliation_difference=Decimal(row["category_reconciliation_difference"]),
            source_reconciliation_difference=Decimal(row["source_reconciliation_difference"]),
            total_qualifying_revenue_eur=Decimal(row["total_qualifying_revenue_eur"]),
        )
        _write_quality_results(connection, pipeline_run_id, metrics)
        validate_country_revenue_metrics(metrics)

    return metrics


def _write_quality_results(
    connection: Connection[Any],
    pipeline_run_id: int,
    metrics: CountryRevenueMetrics,
) -> None:
    checks: list[tuple[str, int | Decimal, int | Decimal]] = [
        (
            "country_revenue_line_state_reconciliation",
            metrics.resolved_line_rows + metrics.pending_fx_line_rows,
            metrics.eligible_line_rows,
        ),
        (
            "country_revenue_completeness_reconciliation",
            metrics.complete_country_rows + metrics.incomplete_country_rows,
            metrics.qualifying_country_rows,
        ),
        ("country_revenue_threshold", metrics.threshold_violations, 0),
        ("country_revenue_rank_sequence", metrics.rank_violations, 0),
        (
            "country_revenue_category_reconciliation",
            metrics.category_reconciliation_difference,
            Decimal("0"),
        ),
        (
            "country_revenue_source_reconciliation",
            metrics.source_reconciliation_difference,
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
    WITH eligible_lines AS (
        SELECT
            orders.country,
            lines.amount_eur
        FROM mart.order_lines_eur AS lines
        JOIN core.orders_clean AS orders USING (raw_order_row_id)
        WHERE orders.category IN ('Books', 'Electronics')
    ),
    expected_countries AS (
        SELECT
            country,
            COALESCE(SUM(amount_eur), 0)::NUMERIC(20, 2) AS total_revenue_eur
        FROM eligible_lines
        GROUP BY country
        HAVING COALESCE(SUM(amount_eur), 0) > 40000
    ),
    rank_checks AS (
        SELECT
            revenue_rank,
            ROW_NUMBER() OVER (
                ORDER BY total_revenue_eur DESC, country ASC
            ) AS expected_rank
        FROM mart.country_category_revenue_eur
    )
    SELECT
        (SELECT COUNT(*) FROM eligible_lines) AS eligible_line_rows,
        (SELECT COUNT(*) FROM eligible_lines WHERE amount_eur IS NOT NULL)
            AS resolved_line_rows,
        (SELECT COUNT(*) FROM eligible_lines WHERE amount_eur IS NULL)
            AS pending_fx_line_rows,
        (SELECT COUNT(DISTINCT country) FROM eligible_lines) AS source_country_rows,
        (SELECT COUNT(*) FROM mart.country_category_revenue_eur)
            AS qualifying_country_rows,
        (SELECT COUNT(*) FROM mart.country_category_revenue_eur WHERE is_complete)
            AS complete_country_rows,
        (SELECT COUNT(*) FROM mart.country_category_revenue_eur WHERE NOT is_complete)
            AS incomplete_country_rows,
        (SELECT COUNT(*) FROM mart.country_category_revenue_eur
            WHERE total_revenue_eur <= 40000) AS threshold_violations,
        (SELECT COUNT(*) FROM rank_checks WHERE revenue_rank <> expected_rank)
            AS rank_violations,
        ABS(COALESCE((
            SELECT SUM(total_revenue_eur - books_revenue_eur - electronics_revenue_eur)
            FROM mart.country_category_revenue_eur
        ), 0)) AS category_reconciliation_difference,
        ABS(
            COALESCE((SELECT SUM(total_revenue_eur) FROM expected_countries), 0)
            - COALESCE((
                SELECT SUM(total_revenue_eur)
                FROM mart.country_category_revenue_eur
            ), 0)
        ) AS source_reconciliation_difference,
        COALESCE((
            SELECT SUM(total_revenue_eur)
            FROM mart.country_category_revenue_eur
        ), 0) AS total_qualifying_revenue_eur
"""
