# 学习阶段 6：同期群留存分析

## 1. 本阶段整体要做什么

第五阶段回答了“有多少顾客复购”，第六阶段进一步回答：

```text
同一批时间进入平台的顾客
→ 首购发生在哪个月
→ 首购后的第1、第2、第3个月还有多少人购买
→ 不同首购月份的顾客留存表现是否不同
```

“同期群”是拥有同一特征的一批对象。本项目按照顾客的**首购月份**分组：2017-01首次购买的顾客属于2017-01同期群，2017-02首次购买的顾客属于2017-02同期群。

核心公式是：

```text
第N月留存率
= 该同期群在首购后第N个月购买的顾客数
÷ 该同期群首购顾客数
```

## 2. 本阶段使用什么工具

| 工具 | 本阶段的作用 |
|---|---|
| Python + pandas | 计算首购月、顾客活动月、月份差、活跃人数和留存率 |
| Matplotlib/Seaborn | 将留存矩阵绘制成热力图 |
| PowerShell | 运行学习脚本、完整分析和自动化测试 |
| SQL | 使用`MIN`、`TIMESTAMPDIFF`、分组和连接定义同期群与月份差 |
| unittest | 验证顾客归群、观察窗口、0%与空白的区别 |

SQL定义首购月份与活动月份的聚合口径；Python构建留存矩阵、处理观察窗口并制作热力图。

## 3. 运行第六阶段脚本

```powershell
cd D:\resume\projects\olist-ecommerce-analysis
.\.venv\Scripts\python.exe src\inspect_cohort_retention.py
```

脚本依次展示真实顾客示例、同月去重、同期群结果、加权留存、留存矩阵以及验收结果。

## 4. 第一步：只保留有效购买

同期群研究的是购买行为，因此只使用：

```text
order_status = delivered
```

顾客标识必须使用跨订单稳定的`customer_unique_id`，不能使用每笔订单对应的`customer_id`。

```python
delivered = order_model[order_model["is_delivered"]].copy()
delivered["order_month"] = (
    delivered["order_purchase_timestamp"].dt.to_period("M")
)
```

`order_month`只保留年月。例如2017-03-15和2017-03-28都会转换成2017-03。

## 5. 第二步：确定顾客的首购月份

对每名顾客取最早成交月份：

```python
first_month = (
    delivered.groupby("customer_unique_id")["order_month"]
    .min()
    .rename("cohort_month")
)
```

`cohort_month`就是顾客所属的同期群。同一名顾客只能有一个首购月份，因此只能属于一个同期群。

## 6. 第三步：同一顾客同一个月只计算一次

同期群留存统计的是“活跃顾客数”，不是订单数：

```python
activity = delivered[
    ["customer_unique_id", "order_month"]
].drop_duplicates()
```

真实数据中，顾客`00cc12...`在2017-03有两笔成交订单。计算2017-03活跃顾客时，这两笔订单只能计作一名顾客，否则购买次数多的顾客会被重复放大。

## 7. 第四步：计算cohort_index

`cohort_index`表示活动月距离首购月多少个月：

```python
activity["cohort_index"] = (
    (activity["order_month"].dt.year - activity["cohort_month"].dt.year) * 12
    + activity["order_month"].dt.month
    - activity["cohort_month"].dt.month
)
```

例如真实顾客`041caba...`有三次跨月购买：

| 活动月份 | 首购月份 | cohort_index |
|---|---|---:|
| 2017-03 | 2017-03 | 0 |
| 2017-11 | 2017-03 | 8 |
| 2018-05 | 2017-03 | 14 |

这里计算的是自然月差，不是相隔天数。2017-01-31首购、2017-02-01再次购买，仍然属于第1月。

## 8. 第五步：计算活跃人数和同期群人数

按“首购月 + cohort_index”统计去重顾客数：

```python
counts = (
    activity.groupby(["cohort_month", "cohort_index"], as_index=False)
    .agg(active_customers=("customer_unique_id", "nunique"))
)
```

第0月活跃人数就是同期群人数：

```text
cohort_size = cohort_index为0时的active_customers
```

所以第0月留存率一定是100%。这是一项结构校验，不是“平台首月表现特别好”的业务结论。

## 9. 第六步：建立完整的可观察月份

数据中的最后成交月份是2018-08。每个同期群能够观察的月份数量不同：

- 2018-08同期群只能观察第0月；
- 2018-07同期群可以观察第0月和第1月；
- 2017-01同期群可以观察更长时间。

必须先为每个同期群建立截至2018-08的可观察月份，再连接真实活动人数：

```text
可观察月份存在，但没有活动记录 → active_customers = 0
数据截止时月份尚未到来       → 不生成记录，矩阵保持空白
```

例如：

- 2016-10同期群第1月已经可以观察，但无人购买，所以是0%；
- 2018-08同期群第1月尚未来到，所以是空白，不是0%。

这是本阶段最重要的数据处理规则。把两者都显示为空，会分不清“没有顾客回来”和“还没有观察机会”。

## 10. 第七步：计算留存率

```python
tidy["retention_rate"] = (
    tidy["active_customers"] / tidy["cohort_size"]
)
```

项目当前基准结果：

| 指标 | 结果 |
|---|---:|
| 成交顾客 | 93,358人 |
| 有顾客的首购月份 | 23个 |
| 第1月可观察同期群 | 22个 |
| 第1月活跃顾客 | 421人 |
| 第1月同期群顾客 | 87,214人 |
| 加权第1月留存率 | 0.4827% |
| 第2月活跃顾客 | 273人 |
| 第2月同期群顾客 | 81,265人 |
| 加权第2月留存率 | 0.3360% |

加权留存率要先汇总活跃人数和同期群人数，再做除法：

```text
421 ÷ 87,214 = 0.4827%
```

不能直接对22个同期群的留存率求普通平均，否则小同期群和大同期群会拥有相同权重。

## 11. 当月留存不是累计留存

本项目的第N月留存含义是：顾客是否在**那个自然月**购买。

一名顾客可能第1月没有购买、第2月又回来购买。因此：

- 第2月留存可以高于第1月；
- 每行留存率不要求持续下降；
- 不能把它解释成“仍然存活且从未流失的顾客比例”。

## 12. 长表和矩阵分别有什么用

`cohort_retention_tidy.csv`是一行一个同期群月份组合：

| cohort_month | cohort_index | active_customers | cohort_size | retention_rate |
|---|---:|---:|---:|---:|
| 2017-01 | 0 | 717 | 717 | 100.00% |
| 2017-01 | 1 | 2 | 717 | 0.28% |
| 2017-01 | 2 | 2 | 717 | 0.28% |

长表适合筛选、分组、Power BI和SQL对账。

`cohort_retention_matrix.csv`把`cohort_index`展开成列，适合绘制热力图。阅读方式为：

```text
纵向：顾客的首购月份
横向：首购后第几个月
颜色：该月留存率
```

热力图聚焦2017-01至2018-08同期群。2016-09和2016-12同期群都只有1名顾客，仍保留在数据表中，但不适合用来比较整体规律。

## 13. SQL如何表达同一逻辑

Python中的`groupby().min()`，在SQL中可以使用窗口函数：

```sql
MIN(order_month) OVER (
    PARTITION BY customer_unique_id
) AS cohort_month
```

月份差使用：

```sql
TIMESTAMPDIFF(MONTH, cohort_month, order_month) AS cohort_index
```

完整SQL位于`sql/03_business_metrics.sql`。查询会先建立可观察月份网格，再用`LEFT JOIN`连接真实活动人数：

```sql
COALESCE(active_customers, 0)
```

`COALESCE`只对已经可以观察的月份补0，未来月份不会进入网格，所以仍然保持空白。

## 14. 输出文件

- `reports/tables/cohort_retention_tidy.csv`：同期群长表；
- `reports/tables/cohort_retention_matrix.csv`：同期群矩阵；
- `reports/figures/03_cohort_retention.png`：留存热力图。

## 15. 本阶段通过标准

完成后应当能独立解释：

1. 同期群是什么，为什么按首购月份分组？
2. `cohort_month`与`cohort_index`分别表示什么？
3. 为什么同一顾客同一个月购买多次只能计算一次？
4. 为什么所有同期群第0月都等于100%？
5. 为什么0%与空白的含义不同？
6. 为什么越新的同期群可观察月份越少？
7. 为什么当月留存率不一定持续下降？
8. 为什么总体留存要按人数加权，而不是直接平均各同期群比例？

下一阶段将分析物流延迟与评价之间的关系，并学习置信区间、Mann–Whitney U检验和Spearman相关。
