# Power BI Desktop 四页看板搭建清单

本清单用于实际操作。完整原理和每一步解释见
[`docs/learning_stage_09_powerbi_dashboard.md`](../docs/learning_stage_09_powerbi_dashboard.md)。

最终看板已完成：[打开PBIX](olist_ecommerce_analysis.pbix)。完整流程见
[项目总结](../docs/project_complete_walkthrough.md)，实际验收和截图见
[验收记录](../reports/project_acceptance.md)。以下步骤供学习或重新搭建使用。

## 检查点0：导入前预检

在PowerShell运行：

```powershell
cd D:\resume\projects\olist-ecommerce-analysis
.\.venv\Scripts\python.exe src\inspect_powerbi_inputs.py
```

通过标准：11张输入表、41项检查全部显示`PASS`。

## 检查点1：导入11张CSV

在Power BI Desktop依次点击“主页 → 获取数据 → 文本/CSV”，导入：

1. `data/processed/powerbi_orders.csv`
2. `data/processed/powerbi_order_items.csv`
3. `data/processed/powerbi_customers.csv`
4. `reports/tables/monthly_metrics.csv`
5. `reports/tables/cohort_retention_tidy.csv`
6. `reports/tables/category_performance.csv`
7. `reports/tables/category_growth_quality.csv`
8. `reports/tables/seller_scorecard.csv`
9. `reports/tables/state_performance.csv`
10. `reports/tables/repurchase_by_first_delivery.csv`
11. `reports/tables/repurchase_by_first_review.csv`

保留文件名去掉`.csv`后的表名。导入后核对：

| 表 | 行数 |
|---|---:|
| `powerbi_orders` | 99,441 |
| `powerbi_order_items` | 112,650 |
| `powerbi_customers` | 93,358 |
| `monthly_metrics` | 25 |
| `cohort_retention_tidy` | 278 |
| `category_performance` | 74 |
| `category_growth_quality` | 74 |
| `seller_scorecard` | 2,970 |
| `state_performance` | 27 |
| `repurchase_by_first_delivery` | 3 |
| `repurchase_by_first_review` | 4 |

在Power Query中确认数据类型：

- 日期：`purchase_date`、`purchase_month`、`first_purchase`、`last_purchase`等；
- 整数：订单数、顾客数、件数、频次、`cohort_index`；
- 小数：金额、评分、天数和比例；
- 布尔值：`is_late`、`is_delivered`、`eligible_90d`、`repeat_within_90d`、`reliable_sample`、`comparable_sample`。

完成后点击“关闭并应用”。

## 检查点2：主题、日期表和关系

1. 当前版本在“设计 → 导入主题”导入`powerbi/olist-theme.json`；旧版本可能在“视图 → 主题”。
2. “建模 → 新建表”，复制`powerbi/date_table.dax`中的`Date = ...`完整公式。
3. 选中`Date`表，点击“表工具 → 标记为日期表”，日期列选择`Date[Date]`。
4. 选中`Date[Year Month]`，点击“列工具 → 按列排序 → Year Month Sort”。
5. 在模型视图建立三条活动关系：

| 一端 | 多端 | 基数 | 交叉筛选方向 |
|---|---|---|---|
| `Date[Date]` | `powerbi_orders[purchase_date]` | 一对多 | 单向 |
| `powerbi_customers[customer_unique_id]` | `powerbi_orders[customer_unique_id]` | 一对多 | 单向 |
| `powerbi_orders[order_id]` | `powerbi_order_items[order_id]` | 一对多 | 单向 |

月度、同期群、品类、商家、州和首单体验汇总表不建立关系。它们是已计算好的独立结果表，错误连接会产生多对多传播。

订单到商品关系必须单向。日期、州或订单状态可从订单表继续筛选商品表；商品品类不能反向筛选订单表并把整单GMV错误归给某个品类。

## 检查点3：DAX

1. “建模 → 新建表”，使用`Metrics = DATATABLE ( "Placeholder", STRING, { { "" } } )`建立度量值专用表。`Measures`在当前Power BI版本中是保留名称，不能用作表名。
2. 先在`Metrics`表中创建至少一个度量值，避免隐藏唯一字段后整张表暂时从报表字段列表消失。
3. 右键`Placeholder`并选择“隐藏”，然后逐个选中`Metrics`表，点击“建模 → 新建度量值”，复制`powerbi/measures.dax`中的其余度量值。
4. `Delivery Status Label`和`Seller Late Risk Band`使用“建模 → 新建列”，分别建立在`powerbi_orders`和`seller_scorecard`中。
5. 设置格式：GMV、金额和客单价为货币或小数；比例为百分比；订单和顾客为整数。

订单级评分保留小数；准时计数排除空白`is_late`；低评分分母排除无评分订单。
成交筛选使用`KEEPFILTERS`与所选订单状态取交集，选择取消订单时不能仍显示成交GMV。

先建立一张临时表格或卡片核对未筛选全量数据：

| 度量 | 期望值 |
|---|---:|
| Total Orders | 99,441 |
| Delivered Orders | 96,478 |
| Delivered GMV | 13,221,498.11 |
| Average Order Value | 137.04 |
| Purchasing Customers | 93,358 |
| Repeat Customers | 2,801 |
| Repeat Customer Rate | 3.00% |
| On-time Delivery Rate | 91.89% |
| Low-review Rate | 12.77% |

## 检查点4：页面1“经营总览”

页面画布使用16:9，建议上方为标题和筛选器，中间为6张卡片，下方为趋势、品类和州矩阵。

| 视觉对象 | 字段设置 | 关键筛选/格式 |
|---|---|---|
| 6张卡片 | `[Delivered GMV]`、`[Delivered Orders]`、`[Average Order Value]`、`[Purchasing Customers]`、`[Repeat Customer Rate]`、`[On-time Delivery Rate]` | 金额BRL；比例2位小数 |
| 折线和簇状柱形图 | X轴`Date[Year Month]`；柱Y轴`[Delivered GMV]`；线Y轴`[Delivered Orders]` | 视觉级筛选`Date[Is Complete Core Month] = True` |
| Top 10横向条形图 | Y轴`powerbi_order_items[category]`；X轴`[Item GMV]` | Top N=10，按Item GMV降序 |
| 州矩阵 | 行`powerbi_orders[customer_state]`；值`[Delivered GMV]`、`[Delivered Orders]`、`[Average Order Value]`、`[Late Delivery Rate]` | 按成交订单降序 |
| 3个切片器 | `Date[Year Month]`、`powerbi_orders[customer_state]`、`powerbi_orders[order_status]` | 首页页面筛选`Date[Is Complete Core Month]=True`；三个切片器默认所有 |

平台GMV卡片使用订单表；品类图必须使用`[Item GMV]`，不能使用`[Delivered GMV]`。

首页默认完整月份：GMV13,181,027.13、成交订单96,211、购买顾客93,104。
核对全窗口基准时清除该页面完整月份筛选；窗口改变后，复购顾客也按当前窗口重新统计。
州矩阵的行层级为`customer_state → customer_city`，使用“+”展开到城市。

## 检查点5：页面2“用户与复购”

本页不放日期切片器。总体复购、90天复购、RFM和同期群来自固定数据观察窗口，不能被任意日期范围混合解释。

| 视觉对象 | 字段设置 | 关键筛选/格式 |
|---|---|---|
| 4张卡片 | `[Purchasing Customers]`、`[Repeat Customer Rate]`、`[Eligible 90D Customers]`、`[90D Repeat Rate]` | 显示93,358、3.00%、75,563、2.27% |
| RFM簇状条形图 | 轴`powerbi_customers[segment]`；值`customer_unique_id`计数、`[RFM Customer Value]` | 顾客数降序；金额可放工具提示 |
| 同期群矩阵 | 行`cohort_retention_tidy[cohort_month]`；列`cohort_index`；值`retention_rate` | 值设百分比；背景色条件格式；可视筛选2017-01至2018-08 |
| 新老客折线图 | X轴`monthly_metrics[purchase_month]`；Y轴`new_customers`、`returning_customers` | `is_complete_core_month=True` |
| 购买频次柱形图 | X轴`powerbi_customers[frequency]`；Y轴`customer_unique_id`计数 | 1、2、3、4+；4+可用计算组或筛选合并 |
| 首单配送对比 | 轴`first_delivery_status`；值`repeat_90d_rate` | `reliable_sample=True` |
| 首单评分对比 | 轴`first_review_group`；值`repeat_90d_rate` | `reliable_sample=True` |

## 检查点6：页面3“物流与满意度”

| 视觉对象 | 字段设置 | 关键筛选/格式 |
|---|---|---|
| 4张卡片 | `[On-time Delivery Rate]`、`[Average Delivery Days]`、`[Average Review Score]`、`[Low-review Rate]` | 成交订单口径 |
| 评分簇状柱形图 | 轴`powerbi_orders[Delivery Status Label]`；值`[Average Review Score]` | 筛掉“配送信息缺失”；延迟红、准时蓝 |
| 低评分率柱形图 | 同上；值`[Low-review Rate]` | 延迟53.99%，准时9.19% |
| 州级矩阵 | `state_performance[customer_state]`、`orders`、`late_delivery_rate`、`low_review_rate`、`average_delivery_days` | 最终页面`orders>=300`；CSV的`reliable_sample`原门槛为500，二者不要混用 |
| 商家关注表 | `seller_id`、`orders`、`revenue`、`average_review_score`、`late_delivery_rate`、`low_review_rate` | `reliable_sample=True`，低评分率降序 |

## 检查点7：页面4“品类与商家”

| 视觉对象 | 字段设置 | 关键筛选/格式 |
|---|---|---|
| 品类矩阵 | `category_performance[category]`、`revenue`、`orders`、`average_review_score`、`low_review_rate`、`late_delivery_rate`、`freight_to_revenue_rate` | `reliable_sample=True`（至少300单） |
| 品类增长散点图 | X=`revenue_growth`；Y=`review_score_change`；大小=`revenue`；图例=`growth_quality_risk`；明细=`category` | `comparable_sample=True`（两个同期各至少100单） |
| 商家象限散点图 | X=`revenue`；Y=`average_review_score`；大小=`orders`；图例=`Seller Late Risk Band`；明细=`seller_id` | `reliable_sample=True`（至少30单） |
| 商品运费散点图 | X=`product_weight_g`平均值；Y=`freight_value`平均值；大小=`price`合计；明细=`category` | `is_delivered=True`且重量非空；体积可放工具提示 |

延迟统一使用红色`#DC2626`，准时统一使用蓝色`#2563EB`。

## 检查点8：交互、保存和截图

1. 使用“格式 → 编辑交互”逐个检查切片器是否筛选应受影响的视觉。
2. 汇总表页面不建立跨表交互；需要联动时使用同一张汇总表中的字段。
3. 为品类、州、商家视觉开启工具提示；最终首页使用“州 → 城市”层级。独立品类/商家汇总表不直接建立跨表下钻关系。
4. 保存为`powerbi/olist_ecommerce_analysis.pbix`。
5. 关闭PBIX，重新打开，点击“主页 → 刷新”，确认四页无报错或空白视觉。
6. 每页切换为“视图 → 页面视图 → 适应页面”，收起窗格并保存全页截图：

```text
reports/figures/powerbi_01_business_overview.png
reports/figures/powerbi_02_customer_repurchase.png
reports/figures/powerbi_03_delivery_satisfaction.png
reports/figures/powerbi_04_category_seller.png
```

## 最终验收

- 全量无筛选：99,441笔订单、96,478笔成交订单；
- GMV 13,221,498.11 BRL，客单价137.04 BRL；
- 成交顾客93,358人、复购顾客2,801人、复购率3.00%；
- 准时率91.89%，平台低评分率12.77%；
- 延迟订单低评分率53.99%，准时订单9.19%；
- 同期群第0月全部100%；
- 品类GMV来自商品金额，平台GMV来自订单金额；
- PBIX关闭后可重新打开、刷新，四页视觉无报错。
