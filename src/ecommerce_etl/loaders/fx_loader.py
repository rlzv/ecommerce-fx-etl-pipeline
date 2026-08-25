from dataclasses import dataclass

from psycopg.types.json import Jsonb

from ecommerce_etl.clients.frankfurter_client import FxRate
from ecommerce_etl.config import Settings
from ecommerce_etl.database import database_connection


@dataclass(frozen=True)
class FxLoadMetrics:
    fetched_rates: int
    inserted_rates: int
    updated_rates: int
    stored_rates: int


def load_fx_rates(
    rates: list[FxRate],
    settings: Settings | None = None,
) -> FxLoadMetrics:
    """Upsert rates by date and currency pair."""

    with database_connection(settings) as connection:
        connection.execute(
            """
            CREATE TEMP TABLE fx_rates_stage (
                rate_date DATE NOT NULL,
                source_currency TEXT NOT NULL,
                target_currency TEXT NOT NULL,
                rate NUMERIC NOT NULL,
                source_payload JSONB NOT NULL
            ) ON COMMIT DROP
            """
        )

        if rates:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO fx_rates_stage (
                        rate_date,
                        source_currency,
                        target_currency,
                        rate,
                        source_payload
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            rate.rate_date,
                            rate.source_currency,
                            rate.target_currency,
                            rate.rate,
                            Jsonb(rate.source_payload),
                        )
                        for rate in rates
                    ],
                )

        existing_row = connection.execute(
            """
            SELECT COUNT(*) AS existing_rates
            FROM fx_rates_stage AS stage
            INNER JOIN reference.fx_rates AS target
                USING (rate_date, source_currency, target_currency)
            """
        ).fetchone()
        existing_rates = int(existing_row["existing_rates"]) if existing_row else 0

        connection.execute(
            """
            INSERT INTO reference.fx_rates (
                rate_date,
                source_currency,
                target_currency,
                rate,
                source_name,
                source_payload
            )
            SELECT
                rate_date,
                source_currency,
                target_currency,
                rate,
                'frankfurter_v2_blended',
                source_payload
            FROM fx_rates_stage
            ON CONFLICT (rate_date, source_currency, target_currency)
            DO UPDATE SET
                rate = EXCLUDED.rate,
                source_name = EXCLUDED.source_name,
                source_payload = EXCLUDED.source_payload,
                last_refreshed_at = NOW()
            """
        )

        total_row = connection.execute(
            "SELECT COUNT(*) AS stored_rates FROM reference.fx_rates"
        ).fetchone()
        stored_rates = int(total_row["stored_rates"]) if total_row else 0

    return FxLoadMetrics(
        fetched_rates=len(rates),
        inserted_rates=len(rates) - existing_rates,
        updated_rates=existing_rates,
        stored_rates=stored_rates,
    )
