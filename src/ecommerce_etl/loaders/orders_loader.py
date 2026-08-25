from dataclasses import dataclass

from psycopg.types.json import Jsonb

from ecommerce_etl.config import Settings
from ecommerce_etl.database import database_connection
from ecommerce_etl.ingestion_records import RawOrderRecord


@dataclass(frozen=True)
class RawLoadMetrics:
    fetched_rows: int
    inserted_rows: int
    updated_rows: int
    total_raw_rows: int
    distinct_payloads: int
    duplicate_payload_copies: int

    def as_dict(self) -> dict[str, int]:
        return {
            "fetched_rows": self.fetched_rows,
            "inserted_rows": self.inserted_rows,
            "updated_rows": self.updated_rows,
            "total_raw_rows": self.total_raw_rows,
            "distinct_payloads": self.distinct_payloads,
            "duplicate_payload_copies": self.duplicate_payload_copies,
        }


def load_raw_orders(
    records: list[RawOrderRecord],
    pipeline_run_id: int,
    settings: Settings | None = None,
) -> RawLoadMetrics:
    """Upsert a complete source snapshot without collapsing exact duplicates."""

    with database_connection(settings) as connection:
        connection.execute(
            """
            CREATE TEMP TABLE orders_raw_stage (
                source_record_hash TEXT NOT NULL,
                source_occurrence INTEGER NOT NULL,
                source_row_number INTEGER NOT NULL,
                source_payload JSONB NOT NULL
            ) ON COMMIT DROP
            """
        )
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO orders_raw_stage (
                    source_record_hash,
                    source_occurrence,
                    source_row_number,
                    source_payload
                )
                VALUES (%s, %s, %s, %s)
                """,
                [
                    (
                        record.source_record_hash,
                        record.source_occurrence,
                        record.source_row_number,
                        Jsonb(record.source_payload),
                    )
                    for record in records
                ],
            )

        existing_row = connection.execute(
            """
            SELECT COUNT(*) AS existing_rows
            FROM orders_raw_stage AS stage
            INNER JOIN raw.orders_raw AS target
                USING (source_record_hash, source_occurrence)
            """
        ).fetchone()
        existing_rows = int(existing_row["existing_rows"]) if existing_row else 0

        connection.execute(
            """
            INSERT INTO raw.orders_raw (
                source_record_hash,
                source_occurrence,
                source_row_number,
                source_payload,
                first_seen_run_id,
                last_seen_run_id
            )
            SELECT
                source_record_hash,
                source_occurrence,
                source_row_number,
                source_payload,
                %(pipeline_run_id)s,
                %(pipeline_run_id)s
            FROM orders_raw_stage
            ON CONFLICT (source_record_hash, source_occurrence)
            DO UPDATE SET
                source_row_number = EXCLUDED.source_row_number,
                source_payload = EXCLUDED.source_payload,
                last_seen_run_id = EXCLUDED.last_seen_run_id,
                last_seen_at = NOW()
            """,
            {"pipeline_run_id": pipeline_run_id},
        )

        total_row = connection.execute(
            "SELECT COUNT(*) AS total_raw_rows FROM raw.orders_raw"
        ).fetchone()
        total_raw_rows = int(total_row["total_raw_rows"]) if total_row else 0

    distinct_payloads = len({record.source_record_hash for record in records})
    fetched_rows = len(records)
    return RawLoadMetrics(
        fetched_rows=fetched_rows,
        inserted_rows=fetched_rows - existing_rows,
        updated_rows=existing_rows,
        total_raw_rows=total_raw_rows,
        distinct_payloads=distinct_payloads,
        duplicate_payload_copies=fetched_rows - distinct_payloads,
    )
