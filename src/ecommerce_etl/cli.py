import argparse
import json
from collections.abc import Sequence

from ecommerce_etl.cleaning import clean_orders
from ecommerce_etl.country_revenue import refresh_country_revenue
from ecommerce_etl.customer_spend import refresh_customer_spend
from ecommerce_etl.database import check_database_connection
from ecommerce_etl.freshness import DEFAULT_MAX_AGE_HOURS, check_freshness
from ecommerce_etl.fx_ingestion import ingest_fx_rates
from ecommerce_etl.ingestion import ingest_orders
from ecommerce_etl.migrations import apply_migrations
from ecommerce_etl.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="E-commerce orders and FX ETL pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("db-check", help="Verify the configured PostgreSQL connection")
    subparsers.add_parser("migrate", help="Apply pending SQL migrations")
    subparsers.add_parser("ingest-orders", help="Fetch and upsert the raw orders snapshot")
    subparsers.add_parser("clean-orders", help="Refresh clean and quarantined orders")
    subparsers.add_parser("ingest-fx", help="Fetch and upsert required RON-to-EUR FX rates")
    subparsers.add_parser(
        "refresh-customer-spend",
        help="Refresh line-level EUR conversions and customer totals",
    )
    subparsers.add_parser(
        "refresh-country-revenue",
        help="Refresh ranked Books and Electronics revenue by country",
    )
    subparsers.add_parser("run-pipeline", help="Run the complete ETL pipeline")
    freshness_parser = subparsers.add_parser(
        "check-freshness",
        help="Fail when the daily pipeline or marts are stale",
    )
    freshness_parser.add_argument(
        "--max-age-hours",
        type=float,
        default=DEFAULT_MAX_AGE_HOURS,
        help="Maximum accepted age in hours (default: 26)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.command == "db-check":
        print(json.dumps(check_database_connection(), indent=2))
        return

    if args.command == "migrate":
        applied = apply_migrations()
        if applied:
            print("Applied migrations:")
            for filename in applied:
                print(f"- {filename}")
        else:
            print("Database is already up to date.")
        return

    if args.command == "ingest-orders":
        print(json.dumps(ingest_orders(), indent=2))
        return

    if args.command == "clean-orders":
        print(json.dumps(clean_orders(), indent=2))
        return

    if args.command == "ingest-fx":
        print(json.dumps(ingest_fx_rates(), indent=2))
        return

    if args.command == "refresh-customer-spend":
        print(json.dumps(refresh_customer_spend(), indent=2))
        return

    if args.command == "refresh-country-revenue":
        print(json.dumps(refresh_country_revenue(), indent=2))
        return

    if args.command == "run-pipeline":
        print(json.dumps(run_pipeline(), indent=2))
        return

    if args.command == "check-freshness":
        print(json.dumps(check_freshness(max_age_hours=args.max_age_hours), indent=2))
