import pytest
from pydantic import ValidationError

from ecommerce_etl.config import Settings


def test_settings_use_local_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_environment == "local"
    assert settings.database_url.endswith("localhost:5433/ecommerce_etl")
    assert settings.request_timeout_seconds == 30.0
    assert settings.orders_page_size == 1000
    assert settings.fx_lookback_days == 7


def test_database_url_must_be_postgresql() -> None:
    with pytest.raises(ValidationError, match="PostgreSQL scheme"):
        Settings(database_url="sqlite:///local.db", _env_file=None)


def test_timeout_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(request_timeout_seconds=0, _env_file=None)


def test_orders_page_size_cannot_exceed_supabase_limit() -> None:
    with pytest.raises(ValidationError):
        Settings(orders_page_size=1001, _env_file=None)


def test_fx_lookback_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(fx_lookback_days=0, _env_file=None)
