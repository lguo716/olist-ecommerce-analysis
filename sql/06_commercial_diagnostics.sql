USE olist_analytics;

-- Category performance. Aggregate to category-order grain before carrying the
-- order-level review and delivery status into a category summary.
WITH category_order AS (
    SELECT
        i.category,
        i.order_id,
        SUM(i.price) AS category_revenue,
        SUM(i.freight_value) AS category_freight,
        COUNT(*) AS items,
        MAX(o.customer_unique_id) AS customer_unique_id,
        MAX(o.review_score) AS review_score,
        MAX(o.is_late) AS is_late
    FROM v_powerbi_order_items i
    JOIN v_powerbi_orders o ON o.order_id = i.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY i.category, i.order_id
)
SELECT
    category,
    ROUND(SUM(category_revenue), 2) AS revenue,
    ROUND(SUM(category_freight), 2) AS freight,
    COUNT(*) AS orders,
    COUNT(DISTINCT customer_unique_id) AS customers,
    SUM(items) AS items,
    SUM(review_score IS NOT NULL) AS reviewed_orders,
    SUM(review_score <= 2) AS low_review_orders,
    ROUND(AVG(review_score), 4) AS average_review_score,
    ROUND(AVG(CASE WHEN review_score IS NOT NULL THEN review_score <= 2 END), 4)
        AS low_review_rate,
    ROUND(AVG(CASE WHEN is_late IS NOT NULL THEN is_late END), 4) AS late_delivery_rate,
    ROUND(SUM(category_revenue) / SUM(items), 2) AS average_item_price,
    ROUND(SUM(category_freight) / NULLIF(SUM(category_revenue), 0), 4)
        AS freight_to_revenue_rate,
    COUNT(*) >= 300 AS reliable_sample
FROM category_order
GROUP BY category
ORDER BY revenue DESC;

-- Customer-state performance. v_powerbi_orders is already one order per row.
SELECT
    customer_state,
    COUNT(*) AS orders,
    COUNT(DISTINCT customer_unique_id) AS customers,
    ROUND(SUM(item_revenue), 2) AS revenue,
    ROUND(SUM(freight_value), 2) AS freight,
    SUM(review_score IS NOT NULL) AS reviewed_orders,
    SUM(review_score <= 2) AS low_review_orders,
    ROUND(AVG(review_score), 4) AS average_review_score,
    ROUND(AVG(CASE WHEN review_score IS NOT NULL THEN review_score <= 2 END), 4)
        AS low_review_rate,
    ROUND(AVG(CASE WHEN is_late IS NOT NULL THEN is_late END), 4) AS late_delivery_rate,
    ROUND(AVG(delivery_days), 2) AS average_delivery_days,
    ROUND(SUM(item_revenue) / COUNT(*), 2) AS average_order_value,
    ROUND(SUM(freight_value) / NULLIF(SUM(item_revenue), 0), 4)
        AS freight_to_revenue_rate,
    COUNT(*) >= 500 AS reliable_sample
FROM v_powerbi_orders
WHERE order_status = 'delivered'
GROUP BY customer_state
ORDER BY revenue DESC;

-- Seller scorecard. Aggregate multiple items from one seller in one order
-- before attaching the order-level review and delivery status.
WITH seller_order AS (
    SELECT
        i.seller_id,
        i.order_id,
        MAX(i.seller_state) AS seller_state,
        SUM(i.price) AS seller_revenue,
        SUM(i.freight_value) AS seller_freight,
        COUNT(*) AS items,
        MAX(o.review_score) AS review_score,
        MAX(o.is_late) AS is_late,
        MAX(o.delivery_days) AS delivery_days
    FROM v_powerbi_order_items i
    JOIN v_powerbi_orders o ON o.order_id = i.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY i.seller_id, i.order_id
), seller_summary AS (
    SELECT
        seller_id,
        MAX(seller_state) AS seller_state,
        COUNT(*) AS orders,
        ROUND(SUM(seller_revenue), 2) AS revenue,
        ROUND(SUM(seller_freight), 2) AS freight,
        SUM(items) AS items,
        SUM(review_score IS NOT NULL) AS reviewed_orders,
        SUM(review_score <= 2) AS low_review_orders,
        AVG(review_score) AS average_review_score,
        AVG(CASE WHEN review_score IS NOT NULL THEN review_score <= 2 END) AS low_review_rate,
        AVG(CASE WHEN is_late IS NOT NULL THEN is_late END) AS late_delivery_rate,
        AVG(delivery_days) AS average_delivery_days
    FROM seller_order
    GROUP BY seller_id
)
SELECT
    *,
    ROUND(freight / NULLIF(revenue, 0), 4) AS freight_to_revenue_rate,
    orders >= 30 AS reliable_sample
FROM seller_summary
ORDER BY revenue DESC;

-- Comparable category growth and quality: Jan-Aug 2018 versus Jan-Aug 2017.
WITH category_order AS (
    SELECT
        i.category,
        i.order_id,
        YEAR(o.purchase_month) AS comparison_year,
        SUM(i.price) AS category_revenue,
        MAX(o.review_score) AS review_score,
        MAX(o.is_late) AS is_late
    FROM v_powerbi_order_items i
    JOIN v_powerbi_orders o ON o.order_id = i.order_id
    WHERE o.order_status = 'delivered'
      AND YEAR(o.purchase_month) IN (2017, 2018)
      AND MONTH(o.purchase_month) <= 8
    GROUP BY i.category, i.order_id, YEAR(o.purchase_month)
), category_period AS (
    SELECT
        category,
        SUM(CASE WHEN comparison_year = 2017 THEN category_revenue END)
            AS revenue_2017_jan_aug,
        SUM(CASE WHEN comparison_year = 2018 THEN category_revenue END)
            AS revenue_2018_jan_aug,
        SUM(comparison_year = 2017) AS orders_2017_jan_aug,
        SUM(comparison_year = 2018) AS orders_2018_jan_aug,
        AVG(CASE WHEN comparison_year = 2017 THEN review_score END)
            AS average_review_score_2017_jan_aug,
        AVG(CASE WHEN comparison_year = 2018 THEN review_score END)
            AS average_review_score_2018_jan_aug,
        AVG(CASE WHEN comparison_year = 2017 THEN is_late END)
            AS late_delivery_rate_2017_jan_aug,
        AVG(CASE WHEN comparison_year = 2018 THEN is_late END)
            AS late_delivery_rate_2018_jan_aug
    FROM category_order
    GROUP BY category
), category_change AS (
    SELECT
        *,
        revenue_2018_jan_aug / NULLIF(revenue_2017_jan_aug, 0) - 1 AS revenue_growth,
        average_review_score_2018_jan_aug - average_review_score_2017_jan_aug
            AS review_score_change,
        late_delivery_rate_2018_jan_aug - late_delivery_rate_2017_jan_aug
            AS late_rate_change,
        orders_2017_jan_aug >= 100 AND orders_2018_jan_aug >= 100 AS comparable_sample
    FROM category_period
)
SELECT
    *,
    comparable_sample
        AND revenue_growth > 0
        AND (review_score_change < -0.1 OR late_rate_change > 0.03)
        AS growth_quality_risk
FROM category_change
ORDER BY growth_quality_risk DESC, revenue_growth DESC;
