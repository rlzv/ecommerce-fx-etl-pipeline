from ecommerce_etl.cleaning import DEFAULT_CLEANING_SQL
from ecommerce_etl.country_revenue import DEFAULT_COUNTRY_REVENUE_SQL
from ecommerce_etl.customer_spend import DEFAULT_CUSTOMER_SPEND_SQL
from ecommerce_etl.migrations import DEFAULT_MIGRATIONS_DIRECTORY, discover_migrations


def test_runtime_sql_assets_exist_inside_package() -> None:
    sql_files = [
        DEFAULT_CLEANING_SQL,
        DEFAULT_CUSTOMER_SPEND_SQL,
        DEFAULT_COUNTRY_REVENUE_SQL,
        *discover_migrations(),
    ]

    assert DEFAULT_MIGRATIONS_DIRECTORY.parent.name == "sql"
    assert len(sql_files) == 9
    assert all(path.is_file() for path in sql_files)
