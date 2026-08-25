import re
from pathlib import Path

from ecommerce_etl.config import Settings
from ecommerce_etl.database import database_connection

MIGRATION_PATTERN = re.compile(r"^(?P<version>\d{3})_[a-z0-9_]+\.sql$")
DEFAULT_MIGRATIONS_DIRECTORY = Path(__file__).resolve().parents[2] / "sql" / "migrations"


def discover_migrations(directory: Path = DEFAULT_MIGRATIONS_DIRECTORY) -> list[Path]:
    """Return valid SQL migration files in deterministic version order."""

    migrations = [path for path in directory.glob("*.sql") if MIGRATION_PATTERN.match(path.name)]
    migrations.sort(key=lambda path: path.name)

    versions = [MIGRATION_PATTERN.match(path.name).group("version") for path in migrations]  # type: ignore[union-attr]
    if len(versions) != len(set(versions)):
        raise ValueError("Migration versions must be unique")

    return migrations


def apply_migrations(settings: Settings | None = None) -> list[str]:
    """Apply previously unseen migrations and return their filenames."""

    applied_now: list[str] = []
    migrations = discover_migrations()

    with database_connection(settings) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(hashtext('ecommerce_etl_migrations'))")
        connection.execute("CREATE SCHEMA IF NOT EXISTS ops")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ops.schema_migrations (
                version TEXT PRIMARY KEY,
                filename TEXT NOT NULL UNIQUE,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        rows = connection.execute("SELECT version FROM ops.schema_migrations").fetchall()
        applied_versions = {str(row["version"]) for row in rows}

        for path in migrations:
            match = MIGRATION_PATTERN.match(path.name)
            if match is None:
                continue

            version = match.group("version")
            if version in applied_versions:
                continue

            connection.execute(path.read_text(encoding="utf-8"))
            connection.execute(
                """
                INSERT INTO ops.schema_migrations (version, filename)
                VALUES (%s, %s)
                """,
                (version, path.name),
            )
            applied_now.append(path.name)

    return applied_now
