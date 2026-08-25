from typing import Any

from psycopg.types.json import Jsonb

from ecommerce_etl.config import Settings
from ecommerce_etl.database import database_connection


def start_pipeline_run(pipeline_name: str, settings: Settings | None = None) -> int:
    with database_connection(settings) as connection:
        row = connection.execute(
            """
            INSERT INTO ops.pipeline_runs (pipeline_name, status)
            VALUES (%s, 'running')
            RETURNING pipeline_run_id
            """,
            (pipeline_name,),
        ).fetchone()

    if row is None:
        raise RuntimeError("Could not create pipeline run")
    return int(row["pipeline_run_id"])


def succeed_pipeline_run(
    pipeline_run_id: int,
    metrics: dict[str, Any],
    settings: Settings | None = None,
) -> None:
    with database_connection(settings) as connection:
        connection.execute(
            """
            UPDATE ops.pipeline_runs
            SET status = 'succeeded',
                finished_at = NOW(),
                metrics = %s
            WHERE pipeline_run_id = %s
            """,
            (Jsonb(metrics), pipeline_run_id),
        )


def fail_pipeline_run(
    pipeline_run_id: int,
    error: Exception,
    settings: Settings | None = None,
) -> None:
    with database_connection(settings) as connection:
        connection.execute(
            """
            UPDATE ops.pipeline_runs
            SET status = 'failed',
                finished_at = NOW(),
                error_message = %s
            WHERE pipeline_run_id = %s
            """,
            (f"{type(error).__name__}: {error}"[:4000], pipeline_run_id),
        )
