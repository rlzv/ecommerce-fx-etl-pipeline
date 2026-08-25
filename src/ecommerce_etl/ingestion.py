from typing import Any

from ecommerce_etl.clients.orders_client import OrdersClient
from ecommerce_etl.config import Settings, get_settings
from ecommerce_etl.ingestion_records import build_raw_records
from ecommerce_etl.loaders.orders_loader import load_raw_orders
from ecommerce_etl.pipeline_runs import (
    fail_pipeline_run,
    start_pipeline_run,
    succeed_pipeline_run,
)

PIPELINE_NAME = "orders_ingestion"


def ingest_orders(
    settings: Settings | None = None,
    client: OrdersClient | None = None,
) -> dict[str, Any]:
    """Fetch the orders snapshot, load it transactionally, and record the outcome."""

    active_settings = settings or get_settings()
    pipeline_run_id = start_pipeline_run(PIPELINE_NAME, active_settings)

    try:
        rows = (client or OrdersClient(active_settings)).fetch_orders()
        records = build_raw_records(rows)
        metrics = load_raw_orders(records, pipeline_run_id, active_settings).as_dict()
        result: dict[str, Any] = {"pipeline_run_id": pipeline_run_id, **metrics}
        succeed_pipeline_run(pipeline_run_id, result, active_settings)
        return result
    except Exception as error:
        fail_pipeline_run(pipeline_run_id, error, active_settings)
        raise
