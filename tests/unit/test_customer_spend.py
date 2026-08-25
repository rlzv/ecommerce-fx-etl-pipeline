from dataclasses import replace
from decimal import Decimal

import pytest

from ecommerce_etl.customer_spend import (
    CustomerSpendMetrics,
    CustomerSpendQualityError,
    validate_customer_spend_metrics,
)


def valid_metrics() -> CustomerSpendMetrics:
    return CustomerSpendMetrics(
        completed_clean_lines=8402,
        mart_line_rows=8402,
        customer_rows=4000,
        complete_customers=3100,
        incomplete_customers=900,
        identity_fx_lines=7000,
        exact_fx_lines=400,
        prior_fx_lines=2,
        pending_fx_lines=1000,
        unavailable_due_lines=0,
        negative_amount_lines=0,
        customer_email_conflicts=0,
        total_resolved_spend_eur=Decimal("123456.78"),
        revenue_reconciliation_difference=Decimal("0"),
    )


def test_valid_customer_spend_metrics_pass() -> None:
    validate_customer_spend_metrics(valid_metrics())


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("mart_line_rows", 8401, "Mart lines"),
        ("incomplete_customers", 899, "completeness states"),
        ("pending_fx_lines", 999, "FX method states"),
        ("unavailable_due_lines", 1, "no usable FX rate"),
        ("negative_amount_lines", 1, "must not be negative"),
        ("customer_email_conflicts", 1, "multiple email"),
        ("revenue_reconciliation_difference", Decimal("0.01"), "do not reconcile"),
    ],
)
def test_invalid_customer_spend_metrics_fail(
    field_name: str,
    value: int | Decimal,
    message: str,
) -> None:
    metrics = replace(valid_metrics(), **{field_name: value})

    with pytest.raises(CustomerSpendQualityError, match=message):
        validate_customer_spend_metrics(metrics)
