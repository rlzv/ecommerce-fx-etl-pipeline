CREATE TABLE IF NOT EXISTS raw.orders_raw (
    raw_order_row_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_record_hash TEXT NOT NULL,
    source_occurrence INTEGER NOT NULL,
    source_row_number INTEGER NOT NULL,
    source_payload JSONB NOT NULL,
    first_seen_run_id BIGINT REFERENCES ops.pipeline_runs (pipeline_run_id),
    last_seen_run_id BIGINT REFERENCES ops.pipeline_runs (pipeline_run_id),
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT orders_raw_source_identity_unique
        UNIQUE (source_record_hash, source_occurrence),
    CONSTRAINT orders_raw_hash_format_check
        CHECK (source_record_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT orders_raw_occurrence_positive_check
        CHECK (source_occurrence > 0),
    CONSTRAINT orders_raw_row_number_positive_check
        CHECK (source_row_number > 0),
    CONSTRAINT orders_raw_payload_object_check
        CHECK (jsonb_typeof(source_payload) = 'object')
);

CREATE INDEX IF NOT EXISTS orders_raw_order_id_idx
    ON raw.orders_raw ((source_payload ->> 'order_id'));

CREATE INDEX IF NOT EXISTS orders_raw_last_seen_run_id_idx
    ON raw.orders_raw (last_seen_run_id);

COMMENT ON TABLE raw.orders_raw IS
    'Lossless orders API landing table; source values remain unchanged in source_payload.';

COMMENT ON COLUMN raw.orders_raw.source_occurrence IS
    'One-based occurrence of an identical payload, preserving exact duplicate source rows.';
