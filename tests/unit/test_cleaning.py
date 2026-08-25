from dataclasses import replace

import pytest

from ecommerce_etl.cleaning import CleaningMetrics, DataQualityError, validate_cleaning_metrics


def valid_metrics() -> CleaningMetrics:
    return CleaningMetrics(
        raw_rows=9268,
        clean_rows=8800,
        rejected_rows=468,
        completed_rows=8402,
        refunded_rows=398,
        duplicate_rejections=183,
        test_rejections=97,
        invalid_quantity_rejections=167,
        invalid_price_rejections=24,
        customer_id_repairs=93,
        customer_surrogate_repairs=1,
        category_repairs=77,
        sku_repairs=218,
        timestamp_repairs=0,
        invalid_clean_rows=0,
        duplicate_clean_payloads=0,
    )


def test_valid_cleaning_metrics_reconcile() -> None:
    validate_cleaning_metrics(valid_metrics())


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("rejected_rows", 467, "reconcile"),
        ("invalid_clean_rows", 1, "required-field"),
        ("duplicate_clean_payloads", 1, "duplicate source"),
    ],
)
def test_invalid_cleaning_metrics_fail(
    field_name: str,
    value: int,
    message: str,
) -> None:
    metrics = replace(valid_metrics(), **{field_name: value})

    with pytest.raises(DataQualityError, match=message):
        validate_cleaning_metrics(metrics)
