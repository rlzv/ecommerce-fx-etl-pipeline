import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

from ecommerce_etl.clients.orders_client import OrderPayload


@dataclass(frozen=True)
class RawOrderRecord:
    source_record_hash: str
    source_occurrence: int
    source_row_number: int
    source_payload: OrderPayload


def canonical_payload(payload: OrderPayload) -> str:
    """Serialize a source row deterministically without changing its values."""

    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def payload_hash(payload: OrderPayload) -> str:
    serialized = canonical_payload(payload)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_raw_records(rows: list[dict[str, Any]]) -> list[RawOrderRecord]:
    """Attach stable identity while retaining repeated identical source rows."""

    occurrences: Counter[str] = Counter()
    records: list[RawOrderRecord] = []

    for row_number, payload in enumerate(rows, start=1):
        record_hash = payload_hash(payload)
        occurrences[record_hash] += 1
        records.append(
            RawOrderRecord(
                source_record_hash=record_hash,
                source_occurrence=occurrences[record_hash],
                source_row_number=row_number,
                source_payload=payload,
            )
        )

    return records
