USE olist_analytics;

-- Customer-level base for first-order experience and 90-day repurchase.
-- Customers whose first order has fewer than 90 observable days are excluded
-- from comparative rates, rather than being treated as non-repeat buyers.
CREATE OR REPLACE VIEW v_customer_repurchase_90d AS
WITH item_agg AS (
    SELECT order_id, SUM(price) AS order_value
    FROM order_items
    GROUP BY order_id
), review_agg AS (
    SELECT order_id, AVG(review_score) AS review_score
    FROM order_reviews
    GROUP BY order_id
), delivered_orders AS (
    SELECT
        c.customer_unique_id,
        o.order_id,
        o.order_purchase_timestamp,
        c.customer_state,
        COALESCE(i.order_value, 0) AS order_value,
        r.review_score,
        CASE
            WHEN o.order_delivered_customer_date IS NULL
              OR o.order_estimated_delivery_date IS NULL THEN NULL
            ELSE o.order_delivered_customer_date > o.order_estimated_delivery_date
        END AS is_late,
        ROW_NUMBER() OVER (
            PARTITION BY c.customer_unique_id
            ORDER BY o.order_purchase_timestamp, o.order_id
        ) AS order_number,
        COUNT(*) OVER (PARTITION BY c.customer_unique_id) AS lifetime_orders
    FROM olist_orders o
    JOIN customers c ON c.customer_id = o.customer_id
    LEFT JOIN item_agg i ON i.order_id = o.order_id
    LEFT JOIN review_agg r ON r.order_id = o.order_id
    WHERE o.order_status = 'delivered'
), first_category_sales AS (
    SELECT
        d.customer_unique_id,
        COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS category,
        SUM(i.price) AS category_revenue
    FROM delivered_orders d
    JOIN order_items i ON i.order_id = d.order_id
    LEFT JOIN products p ON p.product_id = i.product_id
    LEFT JOIN category_translation t
        ON t.product_category_name = p.product_category_name
    WHERE d.order_number = 1
    GROUP BY d.customer_unique_id, category
), ranked_first_category AS (
    SELECT
        customer_unique_id,
        category,
        ROW_NUMBER() OVER (
            PARTITION BY customer_unique_id
            ORDER BY category_revenue DESC, category
        ) AS category_rank
    FROM first_category_sales
), first_and_second AS (
    SELECT
        first_order.customer_unique_id,
        first_order.order_id AS first_order_id,
        first_order.order_purchase_timestamp AS first_purchase_at,
        second_order.order_purchase_timestamp AS second_purchase_at,
        first_order.customer_state,
        first_order.order_value AS first_order_value,
        first_order.review_score AS first_review_score,
        first_order.is_late AS first_is_late,
        first_order.lifetime_orders,
        fc.category AS first_primary_category
    FROM delivered_orders first_order
    LEFT JOIN delivered_orders second_order
        ON second_order.customer_unique_id = first_order.customer_unique_id
       AND second_order.order_number = 2
    LEFT JOIN ranked_first_category fc
        ON fc.customer_unique_id = first_order.customer_unique_id
       AND fc.category_rank = 1
    WHERE first_order.order_number = 1
), sample_end AS (
    SELECT DATE_ADD(DATE(MAX(order_purchase_timestamp)), INTERVAL 1 DAY) AS reference_date
    FROM olist_orders
    WHERE order_status = 'delivered'
)
SELECT
    fs.*,
    DATEDIFF(s.reference_date, DATE(fs.first_purchase_at)) AS observation_days,
    DATEDIFF(s.reference_date, DATE(fs.first_purchase_at)) >= 90 AS eligible_90d,
    fs.second_purchase_at IS NOT NULL
      AND fs.second_purchase_at <= DATE_ADD(fs.first_purchase_at, INTERVAL 90 DAY)
      AS repeat_within_90d,
    CASE
        WHEN fs.first_is_late = 1 THEN 'Late'
        WHEN fs.first_is_late = 0 THEN 'On time'
        ELSE 'Unknown'
    END AS first_delivery_status,
    CASE
        WHEN fs.first_review_score <= 2 THEN 'Low (1-2)'
        WHEN fs.first_review_score < 4 THEN 'Neutral (>2,<4)'
        WHEN fs.first_review_score >= 4 THEN 'High (4-5)'
        ELSE 'Missing'
    END AS first_review_group
FROM first_and_second fs
CROSS JOIN sample_end s;

-- Overall 90-day repeat rate.
SELECT
    COUNT(*) AS eligible_customers,
    SUM(repeat_within_90d) AS repeat_90d_customers,
    ROUND(AVG(repeat_within_90d), 4) AS repeat_90d_rate
FROM v_customer_repurchase_90d
WHERE eligible_90d = 1;

-- First-delivery experience comparison. Repeat this pattern for state,
-- first_primary_category and first_review_group as needed.
SELECT
    first_delivery_status,
    COUNT(*) AS customers,
    SUM(repeat_within_90d) AS repeat_90d_customers,
    ROUND(AVG(repeat_within_90d), 4) AS repeat_90d_rate,
    ROUND(AVG(first_order_value), 2) AS average_first_order_value
FROM v_customer_repurchase_90d
WHERE eligible_90d = 1
GROUP BY first_delivery_status
ORDER BY customers DESC;

SELECT
    first_review_group,
    COUNT(*) AS customers,
    SUM(repeat_within_90d) AS repeat_90d_customers,
    ROUND(AVG(repeat_within_90d), 4) AS repeat_90d_rate
FROM v_customer_repurchase_90d
WHERE eligible_90d = 1
GROUP BY first_review_group
ORDER BY customers DESC;
