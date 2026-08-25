SET LOCAL TIME ZONE 'UTC';
SELECT PG_ADVISORY_XACT_LOCK(HASHTEXT('customer_spend_mart'));

DELETE FROM mart.customer_spend_eur;
DELETE FROM mart.order_lines_eur;

WITH completed_lines AS (
    SELECT
        orders.raw_order_row_id,
        orders.order_id,
        orders.customer_id,
        orders.customer_email,
        orders.currency AS source_currency,
        (orders.quantity * orders.unit_price)::NUMERIC(20, 2) AS source_amount,
        orders.fx_reference_date,
        rates.rate_date AS available_fx_date,
        rates.rate AS available_fx_rate
    FROM core.orders_clean AS orders
    LEFT JOIN LATERAL (
        SELECT
            fx_rates.rate_date,
            fx_rates.rate
        FROM reference.fx_rates AS fx_rates
        WHERE fx_rates.source_currency = 'RON'
          AND fx_rates.target_currency = 'EUR'
          AND fx_rates.rate_date <= orders.fx_reference_date
          AND orders.fx_reference_date <= CURRENT_DATE
        ORDER BY fx_rates.rate_date DESC
        LIMIT 1
    ) AS rates ON orders.currency = 'RON'
    WHERE orders.status = 'completed'
),
converted_lines AS (
    SELECT
        completed_lines.*,
        CASE
            WHEN source_currency = 'EUR' THEN fx_reference_date
            WHEN source_currency = 'RON' AND fx_reference_date <= CURRENT_DATE
                THEN available_fx_date
        END AS applied_fx_date,
        CASE
            WHEN source_currency = 'EUR' THEN 1::NUMERIC
            WHEN source_currency = 'RON' AND fx_reference_date <= CURRENT_DATE
                THEN available_fx_rate
        END AS fx_rate,
        CASE
            WHEN source_currency = 'EUR' THEN 'identity'
            WHEN fx_reference_date > CURRENT_DATE THEN 'pending'
            WHEN available_fx_rate IS NULL THEN 'unavailable'
            WHEN available_fx_date = fx_reference_date THEN 'exact'
            ELSE 'prior'
        END AS fx_rate_method
    FROM completed_lines
)
INSERT INTO mart.order_lines_eur (
    raw_order_row_id,
    order_id,
    customer_id,
    customer_email,
    source_currency,
    source_amount,
    fx_reference_date,
    applied_fx_date,
    fx_rate,
    fx_rate_method,
    amount_eur
)
SELECT
    raw_order_row_id,
    order_id,
    customer_id,
    customer_email,
    source_currency,
    source_amount,
    fx_reference_date,
    applied_fx_date,
    fx_rate,
    fx_rate_method,
    CASE
        WHEN fx_rate IS NOT NULL THEN ROUND(source_amount * fx_rate, 2)
    END AS amount_eur
FROM converted_lines;

INSERT INTO mart.customer_spend_eur (
    customer_id,
    customer_email,
    total_spent_eur,
    completed_order_count,
    completed_line_count,
    resolved_line_count,
    pending_fx_line_count,
    is_complete
)
SELECT
    customer_id,
    MIN(customer_email) AS customer_email,
    COALESCE(SUM(amount_eur), 0)::NUMERIC(20, 2) AS total_spent_eur,
    COUNT(DISTINCT order_id)::INTEGER AS completed_order_count,
    COUNT(*)::INTEGER AS completed_line_count,
    COUNT(amount_eur)::INTEGER AS resolved_line_count,
    COUNT(*) FILTER (WHERE amount_eur IS NULL)::INTEGER AS pending_fx_line_count,
    BOOL_AND(amount_eur IS NOT NULL) AS is_complete
FROM mart.order_lines_eur
GROUP BY customer_id;
