from ecommerce_etl.ingestion_records import build_raw_records, payload_hash


def test_payload_hash_is_independent_of_json_key_order() -> None:
    assert payload_hash({"order_id": "1", "qty": 2}) == payload_hash({"qty": 2, "order_id": "1"})


def test_build_raw_records_preserves_exact_duplicates() -> None:
    duplicate = {"order_id": "1", "qty": "2"}

    records = build_raw_records([duplicate, {"order_id": "2"}, duplicate.copy()])

    assert len(records) == 3
    assert records[0].source_record_hash == records[2].source_record_hash
    assert records[0].source_occurrence == 1
    assert records[2].source_occurrence == 2
    assert [record.source_row_number for record in records] == [1, 2, 3]
