CREATE TABLE IF NOT EXISTS reference.product_catalog (
    product_name TEXT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    CONSTRAINT product_catalog_sku_format_check
        CHECK (sku ~ '^SKU-[A-Z]{2}-[0-9]{3}$')
);

INSERT INTO reference.product_catalog (product_name, sku, category)
VALUES
    ('4K Action Camera', 'SKU-EL-004', 'Electronics'),
    ('Adjustable Dumbbell Set', 'SKU-SP-002', 'Sports'),
    ('Air Fryer 5L', 'SKU-HK-003', 'Home & Kitchen'),
    ('Atomic Habits (RO ed.)', 'SKU-BK-001', 'Books'),
    ('Bluetooth Speaker Mini', 'SKU-EL-003', 'Electronics'),
    ('Hair Dryer Ionic 2200W', 'SKU-BE-002', 'Beauty'),
    ('Men''s Slim Fit Jeans', 'SKU-FA-001', 'Fashion'),
    ('Non-stick Frying Pan 28cm', 'SKU-HK-002', 'Home & Kitchen'),
    ('Running Shoes Pro', 'SKU-FA-003', 'Fashion'),
    ('Stainless Steel Kettle', 'SKU-HK-001', 'Home & Kitchen'),
    ('The Pragmatic Programmer', 'SKU-BK-002', 'Books'),
    ('USB-C Fast Charger 65W', 'SKU-EL-002', 'Electronics'),
    ('Vitamin C Serum 30ml', 'SKU-BE-001', 'Beauty'),
    ('Wireless Earbuds X2', 'SKU-EL-001', 'Electronics'),
    ('Women''s Wool Coat', 'SKU-FA-002', 'Fashion'),
    ('Yoga Mat Premium', 'SKU-SP-001', 'Sports')
ON CONFLICT (product_name)
DO UPDATE SET
    sku = EXCLUDED.sku,
    category = EXCLUDED.category;

CREATE TABLE IF NOT EXISTS core.orders_clean (
    raw_order_row_id BIGINT PRIMARY KEY
        REFERENCES raw.orders_raw (raw_order_row_id),
    source_record_hash TEXT NOT NULL UNIQUE,
    order_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    customer_email TEXT NOT NULL,
    order_ts TIMESTAMPTZ NOT NULL,
    country TEXT NOT NULL,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL,
    channel TEXT NOT NULL,
    fx_reference_date DATE NOT NULL,
    data_repairs TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    cleaned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT orders_clean_quantity_positive_check CHECK (quantity > 0),
    CONSTRAINT orders_clean_price_positive_check CHECK (unit_price > 0),
    CONSTRAINT orders_clean_country_format_check CHECK (country ~ '^[A-Z]{2}$'),
    CONSTRAINT orders_clean_currency_check CHECK (currency IN ('EUR', 'RON')),
    CONSTRAINT orders_clean_status_check CHECK (status IN ('completed', 'refunded')),
    CONSTRAINT orders_clean_sku_format_check CHECK (sku ~ '^SKU-[A-Z]{2}-[0-9]{3}$')
);

CREATE INDEX IF NOT EXISTS orders_clean_customer_id_idx
    ON core.orders_clean (customer_id);

CREATE INDEX IF NOT EXISTS orders_clean_fx_reference_date_idx
    ON core.orders_clean (fx_reference_date);

CREATE INDEX IF NOT EXISTS orders_clean_country_category_idx
    ON core.orders_clean (country, category);

CREATE TABLE IF NOT EXISTS quarantine.orders_rejected (
    raw_order_row_id BIGINT PRIMARY KEY
        REFERENCES raw.orders_raw (raw_order_row_id),
    source_record_hash TEXT NOT NULL,
    source_occurrence INTEGER NOT NULL,
    source_payload JSONB NOT NULL,
    rejection_reasons TEXT[] NOT NULL,
    rejected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT orders_rejected_reason_required_check
        CHECK (CARDINALITY(rejection_reasons) > 0)
);

CREATE INDEX IF NOT EXISTS orders_rejected_reasons_idx
    ON quarantine.orders_rejected USING GIN (rejection_reasons);
