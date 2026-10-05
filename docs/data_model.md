# 数据模型与连接粒度

## 关系模型

```text
customers (1) ── (N) orders (1) ── (N) order_items ── (1) products
                         │                    │
                         │                    └────── (1) sellers
                         ├──── (N) order_payments
                         └──── (N) order_reviews

products (N) ── (1) product_category_name_translation
```

## 主键与分析粒度

| 表 | 主键或业务键 | 原始粒度 |
|---|---|---|
| customers | `customer_id` | 每个订单使用的顾客标识 |
| orders | `order_id` | 每笔订单 |
| order_items | `order_id, order_item_id` | 每个订单商品行 |
| order_payments | `order_id, payment_sequential` | 每次支付记录 |
| order_reviews | `review_id, order_id` | 每条评价记录 |
| products | `product_id` | 每个商品 |
| sellers | `seller_id` | 每个卖家 |

## 防止金额重复

`order_items`、`order_payments` 和 `order_reviews` 都可能在同一订单下出现多行。如果直接将三张表连接，会产生多对多笛卡尔放大。

分析流程先生成：

- `order_items_agg`：每笔订单的商品金额、运费、商品件数、卖家数；
- `payments_agg`：每笔订单的支付金额、最大分期数、支付记录数；
- `reviews_agg`：每笔订单的平均评分和评价记录数；

三张聚合表再以 `order_id` 一对一连接到 `orders`，形成 `order_model`。

## 用户标识

- `customer_id`：订单级客户标识，同一自然人在不同订单中可能不同；
- `customer_unique_id`：跨订单稳定的匿名顾客标识，用于复购、RFM 和同期群分析。

## 已知限制

- 数据经过匿名化，无法获得客户人口属性、营销触达成本和真实利润。
- 评价通常针对整笔订单，多卖家订单中的评分不能完全归因给某一个卖家。
- 成交额为商品价格合计，不代表平台收入或会计确认收入。
- 数据时间窗口有限，后进入样本的顾客天然拥有更短的复购观察期。

