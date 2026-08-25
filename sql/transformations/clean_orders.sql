SET LOCAL TIME ZONE 'UTC';
SELECT PG_ADVISORY_XACT_LOCK(HASHTEXT('orders_cleaning'));

CREATE TEMP TABLE orders_cleaning_stage ON COMMIT DROP AS
WITH source_rows AS (
    SELECT
        raw_order_row_id,
        source_record_hash,
        source_occurrence,
        source_payload,
        NULLIF(BTRIM(source_payload ->> 'order_id'), '') AS order_id,
        NULLIF(BTRIM(source_payload ->> 'customer_id'), '') AS original_customer_id,
        LOWER(NULLIF(BTRIM(source_payload ->> 'customer_email'), '')) AS customer_email,
        BTRIM(source_payload ->> 'order_ts') AS order_ts_text,
        UPPER(NULLIF(BTRIM(source_payload ->> 'country'), '')) AS country,
        NULLIF(BTRIM(source_payload ->> 'product_name'), '') AS product_name,
        NULLIF(BTRIM(source_payload ->> 'category'), '') AS original_category,
        NULLIF(BTRIM(source_payload ->> 'sku'), '') AS original_sku,
        BTRIM(source_payload ->> 'qty') AS quantity_text,
        BTRIM(source_payload ->> 'unit_price') AS unit_price_text,
        UPPER(NULLIF(BTRIM(source_payload ->> 'currency'), '')) AS currency,
        LOWER(NULLIF(BTRIM(source_payload ->> 'status'), '')) AS status,
        LOWER(NULLIF(BTRIM(source_payload ->> 'channel'), '')) AS channel,
        BTRIM(source_payload ->> 'fx_reference_date') AS fx_reference_date_text
    FROM raw.orders_raw
),
customer_identity_map AS (
    SELECT
        customer_email,
        MIN(original_customer_id) AS mapped_customer_id,
        COUNT(DISTINCT original_customer_id)
            FILTER (WHERE original_customer_id IS NOT NULL) AS known_id_count
    FROM source_rows
    WHERE customer_email IS NOT NULL
    GROUP BY customer_email
),
typed_rows AS (
    SELECT
        source_rows.*,
        CASE
            WHEN source_rows.original_customer_id IS NOT NULL
                THEN source_rows.original_customer_id
            WHEN customer_identity_map.known_id_count = 1
                THEN customer_identity_map.mapped_customer_id
            WHEN COALESCE(customer_identity_map.known_id_count, 0) = 0
                 AND source_rows.customer_email ~ '^[^@ ]+@[^@ ]+[.][^@ ]+$'
                THEN 'EMAIL-' || UPPER(MD5(source_rows.customer_email))
        END AS customer_id,
        COALESCE(customer_identity_map.known_id_count, 0) AS known_customer_id_count,
        product_catalog.sku AS canonical_sku,
        product_catalog.category AS canonical_category,
        CASE
            WHEN order_ts_text ~ '^[0-9]{10}$'
                THEN TO_TIMESTAMP(order_ts_text::BIGINT)
            WHEN order_ts_text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}[T ]'
                THEN order_ts_text::TIMESTAMPTZ
            WHEN order_ts_text ~
                 '^[0-9]{2}/[0-9]{2}/[0-9]{4}[ ]+[0-9]{2}:[0-9]{2}$'
                THEN TO_TIMESTAMP(order_ts_text, 'DD/MM/YYYY HH24:MI')
        END AS order_ts,
        CASE
            WHEN quantity_text ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$'
                THEN quantity_text::NUMERIC
        END AS quantity,
        CASE
            WHEN unit_price_text ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$'
                THEN unit_price_text::NUMERIC
        END AS unit_price,
        CASE
            WHEN fx_reference_date_text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                THEN fx_reference_date_text::DATE
        END AS fx_reference_date
    FROM source_rows
    LEFT JOIN customer_identity_map USING (customer_email)
    LEFT JOIN reference.product_catalog AS product_catalog
        ON product_catalog.product_name = source_rows.product_name
),
price_baselines AS (
    SELECT
        product_name,
        currency,
        PERCENTILE_CONT(0.5) WITHIN GROUP (
            ORDER BY unit_price
        )::NUMERIC AS median_unit_price
    FROM typed_rows
    WHERE source_occurrence = 1
      AND status <> 'test'
      AND unit_price > 0
    GROUP BY product_name, currency
),
classified AS (
    SELECT
        typed_rows.*,
        ARRAY_REMOVE(
            ARRAY[
                CASE WHEN source_occurrence > 1 THEN 'exact_duplicate' END,
                CASE WHEN status = 'test' THEN 'test_order' END,
                CASE
                    WHEN quantity IS NULL OR quantity <= 0 OR quantity <> TRUNC(quantity)
                        THEN 'invalid_quantity'
                END,
                CASE
                    WHEN unit_price IS NULL OR unit_price <= 0
                        THEN 'invalid_unit_price'
                END,
                CASE
                    WHEN unit_price > price_baselines.median_unit_price * 10
                        THEN 'implausible_unit_price_outlier'
                END,
                CASE WHEN order_id IS NULL THEN 'missing_order_id' END,
                CASE WHEN customer_id IS NULL THEN 'missing_customer_id' END,
                CASE
                    WHEN customer_email IS NULL OR customer_email !~ '^[^@ ]+@[^@ ]+[.][^@ ]+$'
                        THEN 'invalid_customer_email'
                END,
                CASE WHEN order_ts IS NULL THEN 'invalid_order_timestamp' END,
                CASE WHEN country IS NULL OR country !~ '^[A-Z]{2}$' THEN 'invalid_country' END,
                CASE WHEN canonical_sku IS NULL THEN 'unknown_product' END,
                CASE WHEN currency NOT IN ('EUR', 'RON') THEN 'unsupported_currency' END,
                CASE
                    WHEN status NOT IN ('completed', 'refunded', 'test')
                        THEN 'unsupported_status'
                END,
                CASE WHEN channel IS NULL THEN 'missing_channel' END,
                CASE WHEN fx_reference_date IS NULL THEN 'invalid_fx_reference_date' END
            ]::TEXT[],
            NULL
        ) AS rejection_reasons,
        ARRAY_REMOVE(
            ARRAY[
                CASE
                    WHEN original_customer_id IS NULL
                         AND known_customer_id_count = 1
                         AND customer_id IS NOT NULL
                        THEN 'customer_id_from_email'
                END,
                CASE
                    WHEN original_customer_id IS NULL
                         AND known_customer_id_count = 0
                         AND customer_id IS NOT NULL
                        THEN 'customer_id_surrogate_from_email'
                END,
                CASE
                    WHEN original_category IS DISTINCT FROM canonical_category
                        THEN 'category_from_product_catalog'
                END,
                CASE
                    WHEN original_sku IS DISTINCT FROM canonical_sku
                        THEN 'sku_from_product_catalog'
                END,
                CASE
                    WHEN order_ts_text ~ '^[0-9]{10}$'
                        THEN 'timestamp_from_unix_seconds'
                END,
                CASE
                    WHEN order_ts_text ~
                         '^[0-9]{2}/[0-9]{2}/[0-9]{4}[ ]+[0-9]{2}:[0-9]{2}$'
                        THEN 'timestamp_from_day_first'
                END
            ]::TEXT[],
            NULL
        ) AS data_repairs
    FROM typed_rows
    LEFT JOIN price_baselines USING (product_name, currency)
)
SELECT *
FROM classified;

DELETE FROM core.orders_clean;
DELETE FROM quarantine.orders_rejected;

INSERT INTO quarantine.orders_rejected (
    raw_order_row_id,
    source_record_hash,
    source_occurrence,
    source_payload,
    rejection_reasons
)
SELECT
    raw_order_row_id,
    source_record_hash,
    source_occurrence,
    source_payload,
    rejection_reasons
FROM orders_cleaning_stage
WHERE CARDINALITY(rejection_reasons) > 0;

INSERT INTO core.orders_clean (
    raw_order_row_id,
    source_record_hash,
    order_id,
    customer_id,
    customer_email,
    order_ts,
    country,
    product_name,
    category,
    sku,
    quantity,
    unit_price,
    currency,
    status,
    channel,
    fx_reference_date,
    data_repairs
)
SELECT
    raw_order_row_id,
    source_record_hash,
    order_id,
    customer_id,
    customer_email,
    order_ts,
    country,
    product_name,
    canonical_category,
    canonical_sku,
    quantity::INTEGER,
    unit_price,
    currency,
    status,
    channel,
    fx_reference_date,
    data_repairs
FROM orders_cleaning_stage
WHERE CARDINALITY(rejection_reasons) = 0;
