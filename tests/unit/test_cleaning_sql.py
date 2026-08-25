from ecommerce_etl.cleaning import DEFAULT_CLEANING_SQL


def test_cleaning_sql_contains_auditable_rules() -> None:
    sql = DEFAULT_CLEANING_SQL.read_text(encoding="utf-8")

    required_rules = [
        "SET LOCAL TIME ZONE 'UTC'",
        "source_occurrence > 1",
        "status = 'test'",
        "invalid_quantity",
        "invalid_unit_price",
        "PERCENTILE_CONT(0.5)",
        "median_unit_price * 10",
        "implausible_unit_price_outlier",
        "customer_id_from_email",
        "customer_id_surrogate_from_email",
        "'EMAIL-' || UPPER(MD5(source_rows.customer_email))",
        "category_from_product_catalog",
        "sku_from_product_catalog",
        "TO_TIMESTAMP(order_ts_text::BIGINT)",
        "DD/MM/YYYY HH24:MI",
    ]

    for rule in required_rules:
        assert rule in sql
