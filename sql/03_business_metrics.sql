USE olist_analytics;

-- Core platform metrics. Aggregate items to order grain before joining.
WITH item_agg AS (
    SELECT
        order_id,
        SUM(price) AS item_revenue,
        SUM(freight_value) AS freight_value,
        COUNT(*) AS item_count,
        COUNT(DISTINCT seller_id) AS seller_count
    FROM order_items
    GROUP BY order_id
), order_model AS (
    SELECT
        o.order_id,
        o.order_status,
        o.order_purchase_timestamp,
        c.customer_unique_id,
        COALESCE(i.item_revenue, 0) AS item_revenue,
        COALESCE(i.freight_value, 0) AS freight_value,
        i.item_count,
        i.seller_count,
        o.order_delivered_customer_date,
        o.order_estimated_delivery_date
    FROM olist_orders o
    JOIN customers c ON c.customer_id = o.customer_id
    LEFT JOIN item_agg i ON i.order_id = o.order_id
)
SELECT
    COUNT(*) AS total_orders,
    SUM(order_status = 'delivered') AS delivered_orders,
    ROUND(SUM(CASE WHEN order_status = 'delivered' THEN item_revenue ELSE 0 END), 2) AS delivered_gmv,
    ROUND(
        SUM(CASE WHEN order_status = 'delivered' THEN item_revenue ELSE 0 END)
        / NULLIF(SUM(order_status = 'delivered'), 0),
        2
    ) AS average_order_value,
    ROUND(AVG(order_status = 'canceled'), 4) AS cancellation_rate,
    ROUND(AVG(
        CASE
            WHEN order_status = 'delivered' AND order_delivered_customer_date IS NOT NULL
                THEN order_delivered_customer_date <= order_estimated_delivery_date
        END
    ), 4) AS on_time_delivery_rate
FROM order_model;

-- Monthly performance. The first and last partial months should be marked in
-- the dashboard instead of being interpreted as a decline.
WITH item_agg AS (
    SELECT order_id, SUM(price) AS item_revenue, SUM(freight_value) AS freight_value
    FROM order_items
    GROUP BY order_id
)
SELECT
    DATE_FORMAT(o.order_purchase_timestamp, '%Y-%m-01') AS purchase_month,
    COUNT(DISTINCT o.order_id) AS total_orders,
    COUNT(DISTINCT CASE WHEN o.order_status = 'delivered' THEN o.order_id END) AS delivered_orders,
    ROUND(SUM(CASE WHEN o.order_status = 'delivered' THEN i.item_revenue ELSE 0 END), 2) AS delivered_gmv,
    ROUND(AVG(CASE WHEN o.order_status = 'delivered' THEN i.item_revenue END), 2) AS average_order_value,
    COUNT(DISTINCT c.customer_unique_id) AS customers
FROM olist_orders o
JOIN customers c ON c.customer_id = o.customer_id
LEFT JOIN item_agg i ON i.order_id = o.order_id
GROUP BY DATE_FORMAT(o.order_purchase_timestamp, '%Y-%m-01')
ORDER BY purchase_month;

-- Repeat-customer rate based on the cross-order stable customer_unique_id.
WITH customer_frequency AS (
    SELECT c.customer_unique_id, COUNT(DISTINCT o.order_id) AS delivered_orders
    FROM olist_orders o
    JOIN customers c ON c.customer_id = o.customer_id
    WHERE o.order_status = 'delivered'
    GROUP BY c.customer_unique_id
)
SELECT
    COUNT(*) AS purchasing_customers,
    SUM(delivered_orders >= 2) AS repeat_customers,
    ROUND(AVG(delivered_orders >= 2), 4) AS repeat_customer_rate
FROM customer_frequency;

-- Delivery status and review score. This is an association, not a causal estimate.
WITH review_agg AS (
    SELECT order_id, AVG(review_score) AS review_score
    FROM order_reviews
    GROUP BY order_id
)
SELECT
    CASE
        WHEN o.order_delivered_customer_date <= o.order_estimated_delivery_date THEN 'On time'
        ELSE 'Late'
    END AS delivery_status,
    COUNT(*) AS orders,
    ROUND(AVG(r.review_score), 3) AS average_review_score,
    SUM(r.review_score <= 2) AS low_review_orders,
    ROUND(AVG(r.review_score <= 2), 4) AS low_review_rate,
    ROUND(AVG(TIMESTAMPDIFF(HOUR, o.order_purchase_timestamp, o.order_delivered_customer_date)) / 24, 2)
        AS average_delivery_days,
    ROUND(AVG(TIMESTAMPDIFF(HOUR, o.order_estimated_delivery_date, o.order_delivered_customer_date)) / 24, 2)
        AS average_delta_days
FROM olist_orders o
JOIN review_agg r ON r.order_id = o.order_id
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL
  AND o.order_estimated_delivery_date IS NOT NULL
GROUP BY delivery_status;

-- Monthly cohort retention, returned in tidy form for Power BI.
-- Observable months with no returning customer are 0; future months stay absent.
WITH RECURSIVE delivered_activity AS (
    SELECT DISTINCT
        c.customer_unique_id,
        CAST(DATE_FORMAT(o.order_purchase_timestamp, '%Y-%m-01') AS DATE) AS order_month
    FROM olist_orders o
    JOIN customers c ON c.customer_id = o.customer_id
    WHERE o.order_status = 'delivered'
), cohort_activity AS (
    SELECT
        customer_unique_id,
        order_month,
        MIN(order_month) OVER (PARTITION BY customer_unique_id) AS cohort_month
    FROM delivered_activity
), cohort_counts AS (
    SELECT
        cohort_month,
        TIMESTAMPDIFF(MONTH, cohort_month, order_month) AS cohort_index,
        COUNT(DISTINCT customer_unique_id) AS active_customers
    FROM cohort_activity
    GROUP BY cohort_month, cohort_index
), cohort_sizes AS (
    SELECT cohort_month, active_customers AS cohort_size
    FROM cohort_counts
    WHERE cohort_index = 0
), dataset_end AS (
    SELECT MAX(order_month) AS last_observed_month
    FROM delivered_activity
), month_numbers (cohort_index) AS (
    SELECT 0
    UNION ALL
    SELECT cohort_index + 1
    FROM month_numbers
    WHERE cohort_index < (
        SELECT MAX(TIMESTAMPDIFF(MONTH, s.cohort_month, d.last_observed_month))
        FROM cohort_sizes s
        CROSS JOIN dataset_end d
    )
), observable_grid AS (
    SELECT
        s.cohort_month,
        n.cohort_index,
        s.cohort_size
    FROM cohort_sizes s
    CROSS JOIN dataset_end d
    JOIN month_numbers n
      ON n.cohort_index <= TIMESTAMPDIFF(MONTH, s.cohort_month, d.last_observed_month)
)
SELECT
    g.cohort_month,
    g.cohort_index,
    COALESCE(c.active_customers, 0) AS active_customers,
    g.cohort_size,
    ROUND(COALESCE(c.active_customers, 0) / g.cohort_size, 4) AS retention_rate
FROM observable_grid g
LEFT JOIN cohort_counts c
  ON c.cohort_month = g.cohort_month
 AND c.cohort_index = g.cohort_index
ORDER BY g.cohort_month, g.cohort_index;
