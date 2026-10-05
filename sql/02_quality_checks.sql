USE olist_analytics;

-- Expected row counts and uniqueness checks.
SELECT 'customers' AS table_name, COUNT(*) AS rows, COUNT(DISTINCT customer_id) AS distinct_keys
FROM customers
UNION ALL
SELECT 'orders', COUNT(*), COUNT(DISTINCT order_id) FROM olist_orders
UNION ALL
SELECT 'items', COUNT(*), COUNT(DISTINCT order_id, order_item_id) FROM order_items
UNION ALL
SELECT 'payments', COUNT(*), COUNT(DISTINCT order_id, payment_sequential) FROM order_payments
UNION ALL
SELECT 'products', COUNT(*), COUNT(DISTINCT product_id) FROM products
UNION ALL
SELECT 'sellers', COUNT(*), COUNT(DISTINCT seller_id) FROM sellers;

-- Orphan relationship checks. Every result should normally be zero.
SELECT 'orders_without_customer' AS check_name, COUNT(*) AS failed_rows
FROM olist_orders o
LEFT JOIN customers c ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL
UNION ALL
SELECT 'items_without_order', COUNT(*)
FROM order_items i
LEFT JOIN olist_orders o ON o.order_id = i.order_id
WHERE o.order_id IS NULL
UNION ALL
SELECT 'items_without_product', COUNT(*)
FROM order_items i
LEFT JOIN products p ON p.product_id = i.product_id
WHERE p.product_id IS NULL
UNION ALL
SELECT 'items_without_seller', COUNT(*)
FROM order_items i
LEFT JOIN sellers s ON s.seller_id = i.seller_id
WHERE s.seller_id IS NULL
UNION ALL
SELECT 'payments_without_order', COUNT(*)
FROM order_payments p
LEFT JOIN olist_orders o ON o.order_id = p.order_id
WHERE o.order_id IS NULL
UNION ALL
SELECT 'reviews_without_order', COUNT(*)
FROM order_reviews r
LEFT JOIN olist_orders o ON o.order_id = r.order_id
WHERE o.order_id IS NULL;

-- Invalid value checks. These are kept separate from missing-value checks so
-- an analyst can decide whether a row represents a real refund or source error.
SELECT
    SUM(price < 0) AS negative_item_price,
    SUM(freight_value < 0) AS negative_freight_value
FROM order_items;

SELECT SUM(payment_value < 0) AS negative_payment_value
FROM order_payments;

SELECT SUM(review_score NOT BETWEEN 1 AND 5) AS invalid_review_score
FROM order_reviews;

-- Timestamp logic checks. Keep the output for manual review instead of silently
-- deleting records.
SELECT
    SUM(order_approved_at < order_purchase_timestamp) AS approval_before_purchase,
    SUM(order_delivered_carrier_date < order_purchase_timestamp) AS carrier_before_purchase,
    SUM(order_delivered_customer_date < order_delivered_carrier_date) AS delivery_before_carrier,
    SUM(order_delivered_customer_date < order_purchase_timestamp) AS delivery_before_purchase,
    MIN(order_purchase_timestamp) AS sample_start,
    MAX(order_purchase_timestamp) AS sample_end
FROM olist_orders;

SELECT COUNT(*) AS orders_missing_customer_unique_id
FROM olist_orders o
LEFT JOIN customers c ON c.customer_id = o.customer_id
WHERE c.customer_unique_id IS NULL;

-- Reconciliation used to detect revenue duplication after joins.
SELECT
    COUNT(*) AS item_rows,
    ROUND(SUM(price), 2) AS raw_item_revenue,
    ROUND(SUM(freight_value), 2) AS raw_freight
FROM order_items;
