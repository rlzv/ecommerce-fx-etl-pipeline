CREATE TABLE IF NOT EXISTS mart.order_lines_eur (
    raw_order_row_id BIGINT PRIMARY KEY
        REFERENCES core.orders_clean (raw_order_row_id) ON DELETE CASCADE,
    order_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    customer_email TEXT NOT NULL,
    source_currency TEXT NOT NULL,
    source_amount NUMERIC(20, 2) NOT NULL,
    fx_reference_date DATE NOT NULL,
    applied_fx_date DATE,
    fx_rate NUMERIC(18, 10),
    fx_rate_method TEXT NOT NULL,
    amount_eur NUMERIC(20, 2),
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT order_lines_eur_source_currency_check
        CHECK (source_currency IN ('EUR', 'RON')),
    CONSTRAINT order_lines_eur_source_amount_check
        CHECK (source_amount >= 0),
    CONSTRAINT order_lines_eur_rate_method_check
        CHECK (fx_rate_method IN ('identity', 'exact', 'prior', 'pending', 'unavailable')),
    CONSTRAINT order_lines_eur_conversion_state_check
        CHECK (
            (
                fx_rate_method IN ('identity', 'exact', 'prior')
                AND applied_fx_date IS NOT NULL
                AND fx_rate IS NOT NULL
                AND fx_rate > 0
                AND amount_eur IS NOT NULL
            )
            OR
            (
                fx_rate_method IN ('pending', 'unavailable')
                AND applied_fx_date IS NULL
                AND fx_rate IS NULL
                AND amount_eur IS NULL
            )
        ),
    CONSTRAINT order_lines_eur_amount_check
        CHECK (amount_eur IS NULL OR amount_eur >= 0)
);

CREATE INDEX IF NOT EXISTS order_lines_eur_customer_id_idx
    ON mart.order_lines_eur (customer_id);

CREATE INDEX IF NOT EXISTS order_lines_eur_fx_state_idx
    ON mart.order_lines_eur (fx_rate_method, fx_reference_date);

CREATE TABLE IF NOT EXISTS mart.customer_spend_eur (
    customer_id TEXT PRIMARY KEY,
    customer_email TEXT NOT NULL,
    total_spent_eur NUMERIC(20, 2) NOT NULL,
    completed_order_count INTEGER NOT NULL,
    completed_line_count INTEGER NOT NULL,
    resolved_line_count INTEGER NOT NULL,
    pending_fx_line_count INTEGER NOT NULL,
    is_complete BOOLEAN NOT NULL,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT customer_spend_eur_total_check CHECK (total_spent_eur >= 0),
    CONSTRAINT customer_spend_eur_order_count_check CHECK (completed_order_count > 0),
    CONSTRAINT customer_spend_eur_line_count_check CHECK (completed_line_count > 0),
    CONSTRAINT customer_spend_eur_resolved_count_check CHECK (resolved_line_count >= 0),
    CONSTRAINT customer_spend_eur_pending_count_check CHECK (pending_fx_line_count >= 0),
    CONSTRAINT customer_spend_eur_line_reconciliation_check
        CHECK (resolved_line_count + pending_fx_line_count = completed_line_count),
    CONSTRAINT customer_spend_eur_completeness_check
        CHECK (is_complete = (pending_fx_line_count = 0))
);

CREATE INDEX IF NOT EXISTS customer_spend_eur_total_desc_idx
    ON mart.customer_spend_eur (total_spent_eur DESC);

CREATE INDEX IF NOT EXISTS customer_spend_eur_incomplete_idx
    ON mart.customer_spend_eur (is_complete)
    WHERE NOT is_complete;

COMMENT ON COLUMN mart.customer_spend_eur.total_spent_eur IS
    'Sum of currently resolved completed lines; use is_complete before treating it as final.';
