from dataclasses import replace
from decimal import Decimal

import pytest

from ecommerce_etl.country_revenue import (
    CountryRevenueMetrics,
    CountryRevenueQualityError,
    validate_country_revenue_metrics,
)


def valid_metrics() -> CountryRevenueMetrics:
    return CountryRevenueMetrics(
        eligible_line_rows=2500,
        resolved_line_rows=2200,
        pending_fx_line_rows=300,
        source_country_rows=8,
        qualifying_country_rows=4,
        complete_country_rows=1,
        incomplete_country_rows=3,
        threshold_violations=0,
        rank_violations=0,
        category_reconciliation_difference=Decimal("0"),
        source_reconciliation_difference=Decimal("0"),
        total_qualifying_revenue_eur=Decimal("345678.90"),
    )


def test_valid_country_revenue_metrics_pass() -> None:
    validate_country_revenue_metrics(valid_metrics())


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("pending_fx_line_rows", 299, "line states"),
        ("incomplete_country_rows", 2, "completeness states"),
        ("threshold_violations", 1, "40,000 threshold"),
        ("rank_violations", 1, "ranks"),
        ("category_reconciliation_difference", Decimal("0.01"), "Category revenue"),
        ("source_reconciliation_difference", Decimal("0.01"), "source revenue"),
    ],
)
def test_invalid_country_revenue_metrics_fail(
    field_name: str,
    value: int | Decimal,
    message: str,
) -> None:
    metrics = replace(valid_metrics(), **{field_name: value})

    with pytest.raises(CountryRevenueQualityError, match=message):
        validate_country_revenue_metrics(metrics)
