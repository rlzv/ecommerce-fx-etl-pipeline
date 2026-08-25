from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
from requests import Response, Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ecommerce_etl.config import Settings, get_settings


class FrankfurterApiError(RuntimeError):
    """Raised when Frankfurter returns an unusable response."""


@dataclass(frozen=True)
class FxRate:
    rate_date: date
    source_currency: str
    target_currency: str
    rate: Decimal
    source_payload: dict[str, Any]


class FrankfurterClient:
    """Client for Frankfurter v2 historical and time-series exchange rates."""

    def __init__(
        self,
        settings: Settings | None = None,
        session: Session | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._session = session or requests.Session()

    def fetch_rates(
        self,
        start_date: date,
        end_date: date,
        source_currency: str = "RON",
        target_currency: str = "EUR",
    ) -> list[FxRate]:
        if start_date > end_date:
            raise ValueError("FX start date must not be after end date")

        source = source_currency.upper()
        target = target_currency.upper()
        response = self._request_rates(start_date, end_date, source, target)

        try:
            payload = response.json()
        except requests.JSONDecodeError as error:
            raise FrankfurterApiError("Frankfurter returned invalid JSON") from error

        if not isinstance(payload, list):
            raise FrankfurterApiError("Frankfurter rates response must be a JSON array")

        return [_parse_rate(item, start_date, end_date, source, target) for item in payload]

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )
    def _request_rates(
        self,
        start_date: date,
        end_date: date,
        source_currency: str,
        target_currency: str,
    ) -> Response:
        response = self._session.get(
            f"{self._settings.frankfurter_base_url.rstrip('/')}/rates",
            params={
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
                "base": source_currency,
                "quotes": target_currency,
            },
            headers={"Accept": "application/json"},
            timeout=self._settings.request_timeout_seconds,
        )

        if response.status_code == 429 or response.status_code >= 500:
            response.raise_for_status()
        if response.status_code >= 400:
            raise FrankfurterApiError(
                f"Frankfurter returned HTTP {response.status_code}: {response.text[:300]}"
            )

        return response


def _parse_rate(
    payload: object,
    start_date: date,
    end_date: date,
    expected_source: str,
    expected_target: str,
) -> FxRate:
    if not isinstance(payload, dict):
        raise FrankfurterApiError("Every Frankfurter rate must be a JSON object")

    try:
        rate_date = date.fromisoformat(str(payload["date"]))
        source = str(payload["base"]).upper()
        target = str(payload["quote"]).upper()
        rate = Decimal(str(payload["rate"]))
    except (KeyError, ValueError, InvalidOperation) as error:
        raise FrankfurterApiError("Frankfurter rate has invalid required fields") from error

    if source != expected_source or target != expected_target:
        raise FrankfurterApiError(f"Unexpected FX pair {source}/{target}")
    if not start_date <= rate_date <= end_date:
        raise FrankfurterApiError("Frankfurter returned a rate outside the requested range")
    if not rate.is_finite() or rate <= 0:
        raise FrankfurterApiError("Frankfurter rate must be finite and positive")

    return FxRate(
        rate_date=rate_date,
        source_currency=source,
        target_currency=target,
        rate=rate,
        source_payload=payload,
    )
