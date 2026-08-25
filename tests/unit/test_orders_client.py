from typing import cast
from unittest.mock import Mock

import pytest
import requests

from ecommerce_etl.clients.orders_client import OrdersApiError, OrdersClient
from ecommerce_etl.config import Settings


def response_with(payload: object, content_range: str, status_code: int = 200) -> Mock:
    response = Mock(spec=requests.Response)
    response.status_code = status_code
    response.headers = {"Content-Range": content_range}
    response.json.return_value = payload
    response.text = ""
    return response


def test_fetch_orders_paginates_until_content_range_total() -> None:
    session = Mock(spec=requests.Session)
    session.get.side_effect = [
        response_with([{"id": 1}, {"id": 2}], "0-1/3"),
        response_with([{"id": 3}], "2-2/3"),
    ]
    settings = Settings(orders_api_key="public-key", orders_page_size=2, _env_file=None)

    rows = OrdersClient(settings, cast(requests.Session, session)).fetch_orders()

    assert rows == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert session.get.call_count == 2
    assert session.get.call_args_list[0].kwargs["headers"]["Range"] == "0-1"
    assert session.get.call_args_list[1].kwargs["headers"]["Range"] == "2-3"
    assert session.get.call_args_list[0].kwargs["headers"]["apikey"] == "public-key"


def test_fetch_orders_requires_api_key() -> None:
    settings = Settings(orders_api_key="", _env_file=None)

    with pytest.raises(ValueError, match="ORDERS_API_KEY"):
        OrdersClient(settings).fetch_orders()


def test_fetch_orders_rejects_non_array_response() -> None:
    session = Mock(spec=requests.Session)
    session.get.return_value = response_with({"message": "unexpected"}, "*/0")
    settings = Settings(orders_api_key="public-key", _env_file=None)

    with pytest.raises(OrdersApiError, match="JSON array"):
        OrdersClient(settings, cast(requests.Session, session)).fetch_orders()
