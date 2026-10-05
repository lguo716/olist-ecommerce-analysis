# 数据字典

## 原始数据表

| 表 | 原始粒度 | 关键字段 | 在项目中的用途 |
|---|---|---|---|
| `olist_orders_dataset` | 一行一笔订单 | `order_id`、`customer_id`、`order_status`、5 个时间字段 | 订单状态、趋势和履约时长 |
| `olist_customers_dataset` | 一行一个订单级顾客编号 | `customer_id`、`customer_unique_id`、城市、州 | 顾客身份、地区、复购 |
| `olist_order_items_dataset` | 一行一个订单商品行 | `order_id`、`order_item_id`、`product_id`、`seller_id`、价格、运费 | GMV、品类、商家和运费 |
| `olist_order_payments_dataset` | 一行一次支付记录 | `order_id`、`payment_sequential`、支付方式、分期、金额 | 支付金额、主要支付方式和分期 |
| `olist_order_reviews_dataset` | 一行一条订单评价 | `review_id + order_id`、评分、评论、时间 | 满意度和低评分率 |
| `olist_products_dataset` | 一行一个商品 | `product_id`、品类、重量、长宽高 | 品类及商品物理属性 |
| `olist_sellers_dataset` | 一行一个商家 | `seller_id`、城市、州 | 商家履约诊断 |
| `product_category_name_translation` | 一行一个葡语品类 | 葡语品类、英语品类 | 统一英文品类标签 |
| `olist_geolocation_dataset` | 一行一个邮编坐标记录 | 邮编、经纬度、城市、州 | 可选地图分析；本项目州级分析不加载全表 |

## 关键标识

- `customer_id` 是订单级顾客编号，不能用于跨订单复购。
- `customer_unique_id` 是跨订单稳定的匿名顾客编号，用于复购、RFM 和同期群。
- `order_id` 是订单级模型的唯一键。
- `order_id + order_item_id` 是商品明细业务键。
- `order_id + payment_sequential` 是支付明细业务键。

## 核心派生字段

| 字段 | 粒度 | 定义 |
|---|---|---|
| `item_revenue` | 订单 | 同一订单商品价格之和 |
| `freight_value` | 订单 | 同一订单运费之和 |
| `primary_payment_type` | 订单 | 支付金额最高的支付方式 |
| `review_score` | 订单 | 同一订单多条评价的平均分 |
| `delivery_days` | 订单 | 实际送达时间减下单时间，单位天 |
| `delivery_delta_days` | 订单 | 实际送达时间减预计送达时间；正数为延迟 |
| `is_late` | 订单 | 实际送达晚于预计送达 |
| `customer_order_number` | 顾客订单 | 顾客成交订单按时间排序后的序号 |
| `eligible_90d` | 顾客 | 首购后至少还有 90 天可观察窗口 |
| `repeat_within_90d` | 顾客 | 第二笔成交订单发生在首购后 90 天内 |
| `reviewed_orders` | 品类/商家/州 | 有订单级评分的成交订单数 |
| `low_review_orders` | 品类/商家/州 | 订单级评分小于等于 2 的成交订单数 |
| `low_review_rate` | 品类/商家/州 | 低评分订单数 ÷ 有评分订单数 |

## 输出数据集

| 文件 | 粒度 | 用途 |
|---|---|---|
| `powerbi_orders.csv` | 一行一笔订单 | 经营、履约和评分主事实表 |
| `powerbi_order_items.csv` | 一行一个订单商品行 | 品类、商家、重量和运费下钻 |
| `powerbi_customers.csv` | 一行一个成交顾客 | RFM、分层和 90 天复购 |
| `monthly_metrics.csv` | 一行一个月 | 趋势与环比 |
| `cohort_retention_tidy.csv` | 一行一个同期群月份组合 | 留存热力图 |
| `category_performance.csv` | 一行一个品类 | 品类经营表现 |
| `category_growth_quality.csv` | 一行一个品类 | 同期间增长与质量变化 |
| `seller_scorecard.csv` | 一行一个商家 | 商家关注清单 |
| `state_performance.csv` | 一行一个顾客州 | 地区经营与履约 |
