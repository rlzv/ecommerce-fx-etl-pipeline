from datetime import date
from decimal import Decimal
from typing import cast
from unittest.mock import Mock

import pytest
import requests

from ecommerce_etl.clients.frankfurter_client import FrankfurterApiError, FrankfurterClient
from ecommerce_etl.config import Settings


def response_with(payload: object, status_code: int = 200) -> Mock:
    response = Mock(spec=requests.Response)
    response.status_code = status_code
    response.json.return_value = payload
    response.text = ""
    return response


def test_fetch_rates_parses_v2_response() -> None:
    session = Mock(spec=requests.Session)
    session.get.return_value = response_with(
        [
            {"date": "2026-08-21", "base": "RON", "quote": "EUR", "rate": 0.1964},
            {"date": "2026-08-24", "base": "RON", "quote": "EUR", "rate": 0.1962},
        ]
    )
    settings = Settings(_env_file=None)

    rates = FrankfurterClient(settings, cast(requests.Session, session)).fetch_rates(
        date(2026, 8, 21),
        date(2026, 8, 24),
    )

    assert [rate.rate_date for rate in rates] == [date(2026, 8, 21), date(2026, 8, 24)]
    assert rates[0].rate == Decimal("0.1964")
    assert session.get.call_args.kwargs["params"] == {
        "from": "2026-08-21",
        "to": "2026-08-24",
        "base": "RON",
        "quotes": "EUR",
    }


def test_fetch_rates_rejects_wrong_currency_pair() -> None:
    session = Mock(spec=requests.Session)
    session.get.return_value = response_with(
        [{"date": "2026-08-21", "base": "EUR", "quote": "RON", "rate": 5.1}]
    )

    with pytest.raises(FrankfurterApiError, match="Unexpected FX pair"):
        FrankfurterClient(
            Settings(_env_file=None),
            cast(requests.Session, session),
        ).fetch_rates(date(2026, 8, 21), date(2026, 8, 21))


def test_fetch_rates_rejects_non_positive_rate() -> None:
    session = Mock(spec=requests.Session)
    session.get.return_value = response_with(
        [{"date": "2026-08-21", "base": "RON", "quote": "EUR", "rate": 0}]
    )

    with pytest.raises(FrankfurterApiError, match="finite and positive"):
        FrankfurterClient(
            Settings(_env_file=None),
            cast(requests.Session, session),
        ).fetch_rates(date(2026, 8, 21), date(2026, 8, 21))
