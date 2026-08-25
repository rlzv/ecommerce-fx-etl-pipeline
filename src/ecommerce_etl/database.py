from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from ecommerce_etl.config import Settings, get_settings


@contextmanager
def database_connection(settings: Settings | None = None) -> Generator[Connection[Any], None, None]:
    """Open a PostgreSQL connection and close it deterministically."""

    active_settings = settings or get_settings()
    with psycopg.connect(active_settings.database_url, row_factory=dict_row) as connection:
        yield connection


def check_database_connection(settings: Settings | None = None) -> dict[str, str]:
    """Return identifying information from PostgreSQL as a connectivity smoke test."""

    query = """
        SELECT
            current_database() AS database_name,
            current_user AS database_user,
            version() AS postgres_version
    """
    with database_connection(settings) as connection:
        row = connection.execute(query).fetchone()

    if row is None:
        raise RuntimeError("Database health check returned no result")

    return {
        "database_name": str(row["database_name"]),
        "database_user": str(row["database_user"]),
        "postgres_version": str(row["postgres_version"]),
    }
