-- MySQL 8.0 schema for the Olist public e-commerce dataset.
-- Import the corresponding CSV files after creating these tables. Use UTF-8
-- and keep empty timestamp fields as NULL.

CREATE DATABASE IF NOT EXISTS olist_analytics
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE olist_analytics;

CREATE TABLE IF NOT EXISTS customers (
    customer_id CHAR(32) PRIMARY KEY,
    customer_unique_id CHAR(32) NOT NULL,
    customer_zip_code_prefix INT,
    customer_city VARCHAR(100),
    customer_state CHAR(2),
    INDEX idx_customers_unique_id (customer_unique_id),
    INDEX idx_customers_state (customer_state)
);

CREATE TABLE IF NOT EXISTS olist_orders (
    order_id CHAR(32) PRIMARY KEY,
    customer_id CHAR(32) NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    order_purchase_timestamp DATETIME NOT NULL,
    order_approved_at DATETIME NULL,
    order_delivered_carrier_date DATETIME NULL,
    order_delivered_customer_date DATETIME NULL,
    order_estimated_delivery_date DATETIME NULL,
    INDEX idx_orders_customer (customer_id),
    INDEX idx_orders_purchase_time (order_purchase_timestamp),
    INDEX idx_orders_status (order_status)
);

CREATE TABLE IF NOT EXISTS order_items (
    order_id CHAR(32) NOT NULL,
    order_item_id INT NOT NULL,
    product_id CHAR(32) NOT NULL,
    seller_id CHAR(32) NOT NULL,
    shipping_limit_date DATETIME NULL,
    price DECIMAL(12, 2) NOT NULL,
    freight_value DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, order_item_id),
    INDEX idx_items_product (product_id),
    INDEX idx_items_seller (seller_id)
);

CREATE TABLE IF NOT EXISTS order_payments (
    order_id CHAR(32) NOT NULL,
    payment_sequential INT NOT NULL,
    payment_type VARCHAR(30),
    payment_installments INT,
    payment_value DECIMAL(12, 2),
    PRIMARY KEY (order_id, payment_sequential),
    INDEX idx_payments_type (payment_type)
);

CREATE TABLE IF NOT EXISTS order_reviews (
    review_row_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    review_id CHAR(32),
    order_id CHAR(32) NOT NULL,
    review_score TINYINT,
    review_comment_title TEXT,
    review_comment_message TEXT,
    review_creation_date DATETIME NULL,
    review_answer_timestamp DATETIME NULL,
    INDEX idx_reviews_order (order_id),
    INDEX idx_reviews_score (review_score)
);

CREATE TABLE IF NOT EXISTS products (
    product_id CHAR(32) PRIMARY KEY,
    product_category_name VARCHAR(100),
    product_name_length INT,
    product_description_length INT,
    product_photos_qty INT,
    product_weight_g INT,
    product_length_cm INT,
    product_height_cm INT,
    product_width_cm INT,
    INDEX idx_products_category (product_category_name)
);

CREATE TABLE IF NOT EXISTS sellers (
    seller_id CHAR(32) PRIMARY KEY,
    seller_zip_code_prefix INT,
    seller_city VARCHAR(100),
    seller_state CHAR(2),
    INDEX idx_sellers_state (seller_state)
);

CREATE TABLE IF NOT EXISTS category_translation (
    product_category_name VARCHAR(100) PRIMARY KEY,
    product_category_name_english VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS geolocation (
    geolocation_zip_code_prefix INT,
    geolocation_lat DECIMAL(10, 7),
    geolocation_lng DECIMAL(10, 7),
    geolocation_city VARCHAR(100),
    geolocation_state CHAR(2),
    INDEX idx_geo_zip (geolocation_zip_code_prefix),
    INDEX idx_geo_state (geolocation_state)
);

-- CSV-to-table mapping:
-- olist_customers_dataset.csv             -> customers
-- olist_orders_dataset.csv                -> olist_orders
-- olist_order_items_dataset.csv           -> order_items
-- olist_order_payments_dataset.csv        -> order_payments
-- olist_order_reviews_dataset.csv         -> order_reviews (omit review_row_id)
-- olist_products_dataset.csv              -> products
-- olist_sellers_dataset.csv               -> sellers
-- product_category_name_translation.csv   -> category_translation
-- olist_geolocation_dataset.csv           -> geolocation

