CREATE TABLE IF NOT EXISTS reference.fx_rates (
    rate_date DATE NOT NULL,
    source_currency TEXT NOT NULL,
    target_currency TEXT NOT NULL,
    rate NUMERIC(18, 10) NOT NULL,
    source_name TEXT NOT NULL,
    source_payload JSONB NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (rate_date, source_currency, target_currency),
    CONSTRAINT fx_rates_source_currency_format_check
        CHECK (source_currency ~ '^[A-Z]{3}$'),
    CONSTRAINT fx_rates_target_currency_format_check
        CHECK (target_currency ~ '^[A-Z]{3}$'),
    CONSTRAINT fx_rates_currency_pair_check
        CHECK (source_currency <> target_currency),
    CONSTRAINT fx_rates_rate_positive_check
        CHECK (rate > 0)
);

CREATE INDEX IF NOT EXISTS fx_rates_pair_date_desc_idx
    ON reference.fx_rates (source_currency, target_currency, rate_date DESC);

COMMENT ON TABLE reference.fx_rates IS
    'Historical source-to-target rates; multiply a source amount by rate to obtain target.';
