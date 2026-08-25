CREATE TABLE IF NOT EXISTS mart.country_category_revenue_eur (
    country TEXT PRIMARY KEY,
    books_revenue_eur NUMERIC(20, 2) NOT NULL,
    electronics_revenue_eur NUMERIC(20, 2) NOT NULL,
    total_revenue_eur NUMERIC(20, 2) NOT NULL,
    resolved_line_count INTEGER NOT NULL,
    pending_fx_line_count INTEGER NOT NULL,
    is_complete BOOLEAN NOT NULL,
    revenue_rank INTEGER NOT NULL UNIQUE,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT country_category_revenue_country_check
        CHECK (country ~ '^[A-Z]{2}$'),
    CONSTRAINT country_category_revenue_books_check
        CHECK (books_revenue_eur >= 0),
    CONSTRAINT country_category_revenue_electronics_check
        CHECK (electronics_revenue_eur >= 0),
    CONSTRAINT country_category_revenue_total_check
        CHECK (total_revenue_eur > 40000),
    CONSTRAINT country_category_revenue_reconciliation_check
        CHECK (total_revenue_eur = books_revenue_eur + electronics_revenue_eur),
    CONSTRAINT country_category_revenue_resolved_count_check
        CHECK (resolved_line_count > 0),
    CONSTRAINT country_category_revenue_pending_count_check
        CHECK (pending_fx_line_count >= 0),
    CONSTRAINT country_category_revenue_completeness_check
        CHECK (is_complete = (pending_fx_line_count = 0)),
    CONSTRAINT country_category_revenue_rank_check
        CHECK (revenue_rank > 0)
);

CREATE INDEX IF NOT EXISTS country_category_revenue_total_desc_idx
    ON mart.country_category_revenue_eur (total_revenue_eur DESC, country);

COMMENT ON TABLE mart.country_category_revenue_eur IS
    'Resolved Books and Electronics revenue above EUR 40,000 by country. Future FX lines are tracked as pending.';
