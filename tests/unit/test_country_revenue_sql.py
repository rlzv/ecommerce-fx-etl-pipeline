from ecommerce_etl.country_revenue import DEFAULT_COUNTRY_REVENUE_SQL


def test_country_revenue_sql_contains_filter_threshold_and_rank_rules() -> None:
    sql = DEFAULT_COUNTRY_REVENUE_SQL.read_text(encoding="utf-8")

    required_rules = [
        "orders.category IN ('Books', 'Electronics')",
        "SUM(lines.amount_eur) FILTER (WHERE orders.category = 'Books')",
        "SUM(lines.amount_eur) FILTER (WHERE orders.category = 'Electronics')",
        "WHERE total_revenue_eur > 40000",
        "ROW_NUMBER() OVER",
        "ORDER BY total_revenue_eur DESC, country ASC",
        "pending_fx_line_count = 0 AS is_complete",
    ]

    for rule in required_rules:
        assert rule in sql
