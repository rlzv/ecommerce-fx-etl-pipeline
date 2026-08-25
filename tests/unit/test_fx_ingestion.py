from datetime import date

import pytest

from ecommerce_etl.fx_ingestion import (
    FxCoverageError,
    FxCoverageMetrics,
    FxRequirements,
    build_fetch_window,
    validate_fx_coverage,
)


def test_fetch_window_adds_lookback_and_excludes_future_end() -> None:
    requirements = FxRequirements(
        minimum_date=date(2026, 8, 23),
        maximum_date=date(2026, 9, 3),
        required_dates=12,
    )

    assert build_fetch_window(requirements, date(2026, 8, 25), 7) == (
        date(2026, 8, 16),
        date(2026, 8, 25),
    )


def test_fetch_window_skips_future_only_requirements() -> None:
    requirements = FxRequirements(
        minimum_date=date(2026, 9, 1),
        maximum_date=date(2026, 9, 3),
        required_dates=3,
    )

    assert build_fetch_window(requirements, date(2026, 8, 25), 7) is None


def test_coverage_allows_pending_future_dates() -> None:
    metrics = FxCoverageMetrics(
        required_dates=12,
        due_dates=3,
        covered_due_dates=3,
        unavailable_due_dates=0,
        pending_future_dates=9,
        non_positive_stored_rates=0,
    )

    validate_fx_coverage(metrics)


def test_coverage_rejects_unavailable_due_date() -> None:
    metrics = FxCoverageMetrics(
        required_dates=12,
        due_dates=3,
        covered_due_dates=2,
        unavailable_due_dates=1,
        pending_future_dates=9,
        non_positive_stored_rates=0,
    )

    with pytest.raises(FxCoverageError, match="no usable prior rate"):
        validate_fx_coverage(metrics)
