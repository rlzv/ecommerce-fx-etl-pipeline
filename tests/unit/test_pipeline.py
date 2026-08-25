from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from ecommerce_etl import pipeline
from ecommerce_etl.config import Settings


def test_run_stages_executes_in_dependency_order(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def stage(name: str):  # type: ignore[no-untyped-def]
        def run(settings: Settings) -> dict[str, object]:
            calls.append(name)
            return {"stage": name}

        return run

    monkeypatch.setattr(pipeline, "ingest_orders", stage("orders_ingestion"))
    monkeypatch.setattr(pipeline, "clean_orders", stage("orders_cleaning"))
    monkeypatch.setattr(pipeline, "ingest_fx_rates", stage("fx_ingestion"))
    monkeypatch.setattr(pipeline, "refresh_customer_spend", stage("customer_spend_mart"))
    monkeypatch.setattr(
        pipeline,
        "refresh_country_revenue",
        stage("country_category_revenue_mart"),
    )

    result = pipeline._run_stages(Settings())

    assert calls == [
        "orders_ingestion",
        "orders_cleaning",
        "fx_ingestion",
        "customer_spend_mart",
        "country_category_revenue_mart",
    ]
    assert list(result) == calls


def test_run_stages_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def ingestion(settings: Settings) -> dict[str, object]:
        calls.append("orders_ingestion")
        return {}

    def cleaning(settings: Settings) -> dict[str, object]:
        calls.append("orders_cleaning")
        raise RuntimeError("cleaning failed")

    def should_not_run(settings: Settings) -> dict[str, object]:
        calls.append("unexpected")
        return {}

    monkeypatch.setattr(pipeline, "ingest_orders", ingestion)
    monkeypatch.setattr(pipeline, "clean_orders", cleaning)
    monkeypatch.setattr(pipeline, "ingest_fx_rates", should_not_run)

    with pytest.raises(RuntimeError, match="cleaning failed"):
        pipeline._run_stages(Settings())

    assert calls == ["orders_ingestion", "orders_cleaning"]


def test_run_pipeline_records_parent_success(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings()
    completed: list[tuple[int, dict[str, object]]] = []

    @contextmanager
    def lock(active_settings: Settings) -> Iterator[None]:
        yield

    monkeypatch.setattr(pipeline, "apply_migrations", lambda active_settings: ["006.sql"])
    monkeypatch.setattr(pipeline, "_pipeline_lock", lock)
    monkeypatch.setattr(pipeline, "start_pipeline_run", lambda name, active_settings: 42)
    monkeypatch.setattr(pipeline, "_run_stages", lambda active_settings: {"stage": {}})
    monkeypatch.setattr(
        pipeline,
        "succeed_pipeline_run",
        lambda run_id, metrics, active_settings: completed.append((run_id, metrics)),
    )

    result = pipeline.run_pipeline(settings)

    assert result["pipeline_run_id"] == 42
    assert result["applied_migrations"] == ["006.sql"]
    assert completed == [(42, result)]
