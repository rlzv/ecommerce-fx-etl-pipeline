import argparse
import json
from collections.abc import Sequence

from ecommerce_etl.database import check_database_connection
from ecommerce_etl.migrations import apply_migrations


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="E-commerce orders and FX ETL pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("db-check", help="Verify the configured PostgreSQL connection")
    subparsers.add_parser("migrate", help="Apply pending SQL migrations")
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
