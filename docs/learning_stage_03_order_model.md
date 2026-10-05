# 学习阶段 3：建立一单一行的订单模型

## 1. 本阶段整体要做什么

这一阶段的目标是把订单、顾客、商品、支付和评价整理成一张统一的订单分析表：

```text
一行 = 一笔订单
唯一键 = order_id
```

最终订单模型既保留订单状态和时间，也包含商品金额、运费、支付、评分、顾客地区和物流指标。后续GMV、客单价、复购、物流和看板都依赖这张表。

## 2. 本阶段使用什么工具

| 工具 | 本阶段的作用 |
|---|---|
| Python + pandas | 执行聚合、连接、派生字段和守恒检查 |
| PowerShell | 运行学习脚本与自动化测试 |
| VS Code | 对照原始表、Python代码和模型结果 |
| SQL | 使用`GROUP BY`、聚合视图和`JOIN`定义订单级分析模型 |
| unittest | 验证一单一行、金额和记录数守恒 |

SQL分析视图保存在`sql/04_powerbi_views.sql`中；Python建模脚本负责自动化生成与一单一行、金额守恒等校验。

## 3. 运行第三阶段演示

```powershell
cd D:\resume\projects\olist-ecommerce-analysis
.\.venv\Scripts\python.exe src\inspect_order_model.py
```

脚本会展示一个真实订单在商品、支付和评价表中的原始行，随后展示聚合和连接后的最终一行，并检查金额与记录数是否守恒。

## 4. 先确定目标粒度

建模前必须先决定最终表的一行代表什么。本项目的目标是订单经营分析，因此选择：

```text
目标粒度：订单
一行代表：一笔订单
唯一键：order_id
```

`olist_orders`天然就是一单一行，因此它是模型的骨架。其他表用于给订单补充信息。

| 表 | 原始粒度 | 连接前处理 |
|---|---|---|
| `customers` | 一行一个订单级顾客编号 | 直接按`customer_id`连接 |
| `order_items` | 一行一个订单商品行 | 按`order_id`聚合 |
| `order_payments` | 一行一次支付 | 按`order_id`聚合 |
| `order_reviews` | 一行一条订单评价 | 按`order_id`聚合 |

## 5. 聚合商品明细

Python代码：

```python
item_agg = (
    items.groupby("order_id", as_index=False)
    .agg(
        item_revenue=("price", "sum"),
        freight_value=("freight_value", "sum"),
        item_count=("order_item_id", "count"),
        unique_products=("product_id", "nunique"),
        seller_count=("seller_id", "nunique"),
    )
)
```

各字段含义：

- `item_revenue`：一笔订单所有商品价格之和；
- `freight_value`：一笔订单所有商品行运费之和；
- `item_count`：订单商品行数量；
- `unique_products`：不同商品数量；
- `seller_count`：不同商家数量。

对应SQL：

```sql
SELECT
    order_id,
    SUM(price) AS item_revenue,
    SUM(freight_value) AS freight_value,
    COUNT(*) AS item_count,
    COUNT(DISTINCT product_id) AS unique_products,
    COUNT(DISTINCT seller_id) AS seller_count
FROM order_items
GROUP BY order_id;
```

`GROUP BY order_id`把同一订单的多行商品放进一组，再对每组求和或计数。

## 6. 聚合支付记录

```python
payment_agg = (
    payments.groupby("order_id", as_index=False)
    .agg(
        payment_value=("payment_value", "sum"),
        payment_records=("payment_sequential", "count"),
        max_installments=("payment_installments", "max"),
    )
)
```

- `payment_value`：一笔订单所有支付记录之和；
- `payment_records`：支付记录数量；
- `max_installments`：该订单出现的最大分期数。

一笔订单可能同时使用信用卡和代金券。项目先按`order_id + payment_type`汇总金额，再选择金额最高的支付方式作为`primary_payment_type`。它表示主要支付方式，不代表订单只使用了这一种方式。

## 7. 聚合评价记录

```python
review_agg = (
    reviews.groupby("order_id", as_index=False)
    .agg(
        review_score=("review_score", "mean"),
        review_records=("review_id", "count"),
        has_review_comment=("review_comment_message", lambda x: int(x.notna().any())),
    )
)
```

- 多条评价使用平均分作为订单评分；
- `review_records`记录一笔订单有多少条评价；
- 只要有一条评价正文，`has_review_comment`就为1。

## 8. 连接顾客和三张聚合表

Python代码：

```python
model = (
    orders.merge(customers, on="customer_id", how="left", validate="many_to_one")
    .merge(item_agg, on="order_id", how="left", validate="one_to_one")
    .merge(payment_agg, on="order_id", how="left", validate="one_to_one")
    .merge(review_agg, on="order_id", how="left", validate="one_to_one")
)
```

这里有两个不同的连接关系：

- 多笔订单可以对应同一个`customer_unique_id`，但每个`customer_id`在顾客表中只有一行，因此订单连接顾客使用`many_to_one`检查；
- 三张聚合表对每个`order_id`最多一行，因此连接订单使用`one_to_one`检查。

`how="left"`表示保留全部订单。没有商品、支付或评价时，相应字段暂时为空，而不是把订单删除。

金额、运费和数量缺失可以填0；没有评价时，评分必须保持缺失，不能填成0分。

## 9. 生成订单级派生字段

连接完成后计算：

| 字段 | 定义 |
|---|---|
| `purchase_date` | 下单日期 |
| `purchase_month` | 下单月份 |
| `is_delivered` | 是否已送达 |
| `is_canceled` | 是否取消 |
| `is_unavailable` | 是否商品不可用 |
| `delivery_days` | 实际送达时间减下单时间 |
| `delivery_delta_days` | 实际送达时间减预计送达时间 |
| `is_late` | 实际送达是否晚于预计送达 |
| `delivered_gmv` | 只有成交订单才计入的商品金额 |
| `customer_order_number` | 顾客的第几笔成交订单 |
| `is_repeat_order` | 是否为该顾客第二笔及以后订单 |

## 10. 真实订单结果

订单`3df55fc07ff463109ce0422439693aee`原来有2个商品行、2个支付行和2条评价。聚合连接后只有一行：

| 指标 | 结果 |
|---|---:|
| 商品金额 | 282.63 BRL |
| 运费 | 33.97 BRL |
| 支付金额 | 316.60 BRL |
| 商品行数 | 2 |
| 不同商品数 | 2 |
| 商家数 | 2 |
| 支付记录数 | 2 |
| 主要支付方式 | 信用卡 |
| 平均评分 | 2.5 |
| 评价记录数 | 2 |

其中：

```text
商品金额 282.63 + 运费 33.97 = 支付金额 316.60
```

## 11. 模型验收

最终必须同时满足：

```text
模型行数 = 原始订单数 = 99,441
不同order_id数量 = 99,441
聚合前商品金额 = 聚合后商品金额 = 13,591,643.70 BRL
聚合前运费 = 聚合后运费 = 2,256,599.44 BRL
商品行、支付记录和评价记录数量聚合前后守恒
```

只验证行数不够。如果金额发生变化，说明连接或聚合仍然存在重复或遗漏。

## 12. 本阶段通过标准

进入经营指标阶段前，应当能回答：

1. 为什么以`olist_orders`作为模型骨架？
2. 为什么商品、支付和评价必须先聚合？
3. `groupby`、`sum`、`count`和`nunique`分别做什么？
4. `many_to_one`与`one_to_one`连接检查有什么区别？
5. 为什么没有评价时不能把评分填成0？
6. 为什么既要检查`order_id`唯一，又要检查金额守恒？

下一阶段将在这张一单一行模型上计算成交额、订单量、客单价、取消率、顾客数、准时送达率和月度趋势。
