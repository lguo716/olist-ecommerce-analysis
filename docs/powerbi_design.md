# Power BI 看板设计

## 导入与建模

1. 导入 `data/processed/powerbi_orders.csv`、`powerbi_order_items.csv`、`powerbi_customers.csv`，以及 `reports/tables` 下的8张汇总表，共11张输入表。
2. 导入 `powerbi/olist-theme.json` 作为报表主题。
3. 使用 `powerbi/date_table.dax` 创建日期表，并建立日期关系。
4. 按 `powerbi/measures.dax` 创建核心度量值；金额格式设置为 BRL，比例保留 1～2 位小数。
5. 日期到订单、顾客到订单、订单到商品共三条关系全部使用单向筛选；其余汇总表保持独立。
6. `powerbi_orders` 与 `powerbi_order_items` 通过 `order_id` 建立一对多关系；平台GMV使用订单表，品类GMV使用商品表，不能互换。

## 页面 1：经营总览

- 卡片：成交额、成交订单数、客单价、购买顾客数、复购率、准时送达率；
- 折线图：月度成交额与订单数；
- 条形图：Top 10 商品品类；
- 地图或矩阵：州级成交额与订单表现；
- 筛选器：日期、顾客州、商品品类、订单状态。

## 页面 2：用户与复购

- RFM 分层人数及成交贡献；
- 首购月份同期群留存矩阵；
- 新客、复购顾客趋势；
- 顾客频次与客单价分布。

## 页面 3：物流与满意度

- 准时送达率、平均履约时长、平均评分、低评分率；
- 准时与延迟订单评分对比；
- 州级延迟率矩阵；
- 物流延迟天数与评分分布；
- 需要关注的商家列表。

## 页面 4：商品与商家

- 品类成交额、订单数、平均评分、延迟率；
- 商家成交额与履约表现象限；
- 多卖家订单占比；
- 商品体积、重量与运费的关系。

## 建议导入文件

- `data/processed/powerbi_orders.csv`
- `data/processed/powerbi_order_items.csv`
- `data/processed/powerbi_customers.csv`
- `reports/tables/monthly_metrics.csv`
- `reports/tables/cohort_retention_tidy.csv`
- `reports/tables/seller_scorecard.csv`

学习原理见[`learning_stage_09_powerbi_dashboard.md`](learning_stage_09_powerbi_dashboard.md)，逐项搭建与验收步骤见[`powerbi/build_checklist.md`](../powerbi/build_checklist.md)。
