from ecommerce_etl.customer_spend import DEFAULT_CUSTOMER_SPEND_SQL


def test_customer_spend_sql_contains_fx_and_revenue_rules() -> None:
    sql = DEFAULT_CUSTOMER_SPEND_SQL.read_text(encoding="utf-8")

    required_rules = [
        "orders.status = 'completed'",
        "LEFT JOIN LATERAL",
        "fx_rates.rate_date <= orders.fx_reference_date",
        "orders.fx_reference_date <= CURRENT_DATE",
        "WHEN source_currency = 'EUR' THEN 1::NUMERIC",
        "WHEN fx_reference_date > CURRENT_DATE THEN 'pending'",
        "WHEN available_fx_date = fx_reference_date THEN 'exact'",
        "ELSE 'prior'",
        "ROUND(source_amount * fx_rate, 2)",
        "GROUP BY customer_id",
    ]

    for rule in required_rules:
        assert rule in sql
