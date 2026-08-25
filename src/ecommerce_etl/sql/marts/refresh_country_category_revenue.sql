SET LOCAL TIME ZONE 'UTC';
SELECT PG_ADVISORY_XACT_LOCK(HASHTEXT('country_category_revenue_mart'));

DELETE FROM mart.country_category_revenue_eur;

WITH country_totals AS (
    SELECT
        orders.country,
        COALESCE(
            SUM(lines.amount_eur) FILTER (WHERE orders.category = 'Books'),
            0
        )::NUMERIC(20, 2) AS books_revenue_eur,
        COALESCE(
            SUM(lines.amount_eur) FILTER (WHERE orders.category = 'Electronics'),
            0
        )::NUMERIC(20, 2) AS electronics_revenue_eur,
        COALESCE(SUM(lines.amount_eur), 0)::NUMERIC(20, 2) AS total_revenue_eur,
        COUNT(lines.amount_eur)::INTEGER AS resolved_line_count,
        COUNT(*) FILTER (WHERE lines.amount_eur IS NULL)::INTEGER AS pending_fx_line_count
    FROM mart.order_lines_eur AS lines
    JOIN core.orders_clean AS orders USING (raw_order_row_id)
    WHERE orders.category IN ('Books', 'Electronics')
    GROUP BY orders.country
),
qualifying_countries AS (
    SELECT
        country_totals.*,
        pending_fx_line_count = 0 AS is_complete
    FROM country_totals
    WHERE total_revenue_eur > 40000
),
ranked_countries AS (
    SELECT
        qualifying_countries.*,
        ROW_NUMBER() OVER (
            ORDER BY total_revenue_eur DESC, country ASC
        )::INTEGER AS revenue_rank
    FROM qualifying_countries
)
INSERT INTO mart.country_category_revenue_eur (
    country,
    books_revenue_eur,
    electronics_revenue_eur,
    total_revenue_eur,
    resolved_line_count,
    pending_fx_line_count,
    is_complete,
    revenue_rank
)
SELECT
    country,
    books_revenue_eur,
    electronics_revenue_eur,
    total_revenue_eur,
    resolved_line_count,
    pending_fx_line_count,
    is_complete,
    revenue_rank
FROM ranked_countries;
