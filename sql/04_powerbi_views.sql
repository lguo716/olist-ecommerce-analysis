USE olist_analytics;

CREATE OR REPLACE VIEW v_order_items_agg AS
SELECT
    order_id,
    SUM(price) AS item_revenue,
    SUM(freight_value) AS freight_value,
    COUNT(*) AS item_count,
    COUNT(DISTINCT product_id) AS unique_products,
    COUNT(DISTINCT seller_id) AS seller_count
FROM order_items
GROUP BY order_id;

CREATE OR REPLACE VIEW v_order_payments_agg AS
SELECT
    order_id,
    SUM(payment_value) AS payment_value,
    COUNT(*) AS payment_records,
    MAX(payment_installments) AS max_installments
FROM order_payments
GROUP BY order_id;

CREATE OR REPLACE VIEW v_order_reviews_agg AS
SELECT
    order_id,
    AVG(review_score) AS review_score,
    COUNT(*) AS review_records,
    MAX(review_comment_message IS NOT NULL) AS has_review_comment
FROM order_reviews
GROUP BY order_id;

CREATE OR REPLACE VIEW v_powerbi_orders AS
SELECT
    o.order_id,
    c.customer_unique_id,
    o.order_status,
    o.order_purchase_timestamp,
    DATE(o.order_purchase_timestamp) AS purchase_date,
    DATE_FORMAT(o.order_purchase_timestamp, '%Y-%m-01') AS purchase_month,
    c.customer_city,
    c.customer_state,
    COALESCE(i.item_revenue, 0) AS item_revenue,
    COALESCE(i.freight_value, 0) AS freight_value,
    COALESCE(i.item_count, 0) AS item_count,
    COALESCE(i.unique_products, 0) AS unique_products,
    COALESCE(i.seller_count, 0) AS seller_count,
    p.payment_value,
    p.payment_records,
    p.max_installments,
    r.review_score,
    TIMESTAMPDIFF(HOUR, o.order_purchase_timestamp, o.order_delivered_customer_date) / 24 AS delivery_days,
    TIMESTAMPDIFF(HOUR, o.order_estimated_delivery_date, o.order_delivered_customer_date) / 24
        AS delivery_delta_days,
    CASE
        WHEN o.order_delivered_customer_date IS NULL OR o.order_estimated_delivery_date IS NULL THEN NULL
        ELSE o.order_delivered_customer_date > o.order_estimated_delivery_date
    END AS is_late
FROM olist_orders o
JOIN customers c ON c.customer_id = o.customer_id
LEFT JOIN v_order_items_agg i ON i.order_id = o.order_id
LEFT JOIN v_order_payments_agg p ON p.order_id = o.order_id
LEFT JOIN v_order_reviews_agg r ON r.order_id = o.order_id;

CREATE OR REPLACE VIEW v_powerbi_order_items AS
SELECT
    i.order_id,
    i.order_item_id,
    i.product_id,
    i.seller_id,
    COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS category,
    i.price,
    i.freight_value,
    i.shipping_limit_date,
    s.seller_city,
    s.seller_state
FROM order_items i
LEFT JOIN products p ON p.product_id = i.product_id
LEFT JOIN category_translation t ON t.product_category_name = p.product_category_name
LEFT JOIN sellers s ON s.seller_id = i.seller_id;

