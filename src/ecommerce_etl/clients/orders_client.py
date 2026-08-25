from collections.abc import Mapping
from typing import Any

import requests
from requests import Response, Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ecommerce_etl.config import Settings, get_settings

OrderPayload = dict[str, Any]


class OrdersApiError(RuntimeError):
    """Raised when the orders endpoint returns an unusable response."""


class OrdersClient:
    """Paginated client for the Supabase/PostgREST orders endpoint."""

    def __init__(
        self,
        settings: Settings | None = None,
        session: Session | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._session = session or requests.Session()

    def fetch_orders(self) -> list[OrderPayload]:
        api_key = self._settings.orders_api_key.get_secret_value()
        if not api_key:
            raise ValueError("ORDERS_API_KEY is required to ingest orders")

        rows: list[OrderPayload] = []
        offset = 0

        while True:
            response = self._fetch_page(offset, api_key)
            page = self._parse_page(response)
            rows.extend(page)

            total = _parse_content_range_total(response.headers)
            offset += len(page)

            if not page or len(page) < self._settings.orders_page_size:
                break
            if total is not None and offset >= total:
                break

        if not rows:
            raise OrdersApiError("Orders API returned no rows")

        return rows

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )
    def _fetch_page(self, offset: int, api_key: str) -> Response:
        page_end = offset + self._settings.orders_page_size - 1
        response = self._session.get(
            self._settings.orders_api_url,
            headers={
                "Accept": "application/json",
                "apikey": api_key,
                "Prefer": "count=exact",
                "Range": f"{offset}-{page_end}",
                "Range-Unit": "items",
            },
            timeout=self._settings.request_timeout_seconds,
        )

        if response.status_code == 429 or response.status_code >= 500:
            response.raise_for_status()
        if response.status_code >= 400:
            raise OrdersApiError(
                f"Orders API returned HTTP {response.status_code}: {response.text[:300]}"
            )

        return response

    @staticmethod
    def _parse_page(response: Response) -> list[OrderPayload]:
        try:
            payload = response.json()
        except requests.JSONDecodeError as error:
            raise OrdersApiError("Orders API returned invalid JSON") from error

        if not isinstance(payload, list):
            raise OrdersApiError("Orders API response must be a JSON array")
        if any(not isinstance(row, dict) for row in payload):
            raise OrdersApiError("Every orders API row must be a JSON object")

        return payload


def _parse_content_range_total(headers: Mapping[str, str]) -> int | None:
    """Extract the total row count from a PostgREST Content-Range header."""

    content_range = headers.get("Content-Range")
    if not content_range or "/" not in content_range:
        return None

    total_text = content_range.rsplit("/", maxsplit=1)[1]
    if total_text == "*":
        return None

    try:
        return int(total_text)
    except ValueError:
        return None
