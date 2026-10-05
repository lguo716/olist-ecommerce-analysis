# 学习阶段 4：经营指标与月度趋势

## 1. 本阶段整体要做什么

第三阶段得到了一单一行的订单模型。本阶段把订单记录转换为管理者能够理解的经营指标，回答：

```text
平台有多少订单
→ 多少订单真正完成交易
→ 成交金额是多少
→ 每笔成交订单平均多少钱
→ 取消、不可用和延迟情况如何
→ 经营表现随月份怎样变化
```

## 2. 本阶段使用什么工具

| 工具 | 本阶段的作用 |
|---|---|
| Python + pandas | 筛选成交订单、计算总体KPI和月度指标 |
| Matplotlib/Seaborn | 绘制成交额与订单量趋势图 |
| PowerShell | 运行学习脚本和自动化测试 |
| VS Code | 阅读指标代码、CSV结果和图表 |
| SQL | 使用`WHERE`、`COUNT`、`SUM`和`GROUP BY`定义经营指标查询 |
| unittest | 固定指标分子、分母和时间窗口 |

SQL经营查询位于`sql/03_business_metrics.sql`；Python学习入口展示指标公式、分子分母和月度结果。

## 3. 运行第四阶段学习脚本

```powershell
cd D:\resume\projects\olist-ecommerce-analysis
.\.venv\Scripts\python.exe src\inspect_business_metrics.py
```

脚本会显示订单状态、每个指标的分子和分母、完整月份趋势以及最终验收结果。

## 4. 先区分总订单和成交订单

总订单包括所有状态：

```python
total_orders = order_model["order_id"].nunique()
```

成交订单限定为`delivered`：

```python
delivered = order_model[order_model["is_delivered"]]
delivered_orders = delivered["order_id"].nunique()
```

当前主要状态：

| 状态 | 订单数 |
|---|---:|
| delivered | 96,478 |
| shipped | 1,107 |
| canceled | 625 |
| unavailable | 609 |
| invoiced | 314 |
| processing | 301 |

`shipped`只表示已经发货，不能计入成交订单。

## 5. 成交额和成交运费

```python
delivered_gmv = delivered["item_revenue"].sum()
delivered_freight = delivered["freight_value"].sum()
```

本项目的GMV定义为：

```text
状态为delivered的订单商品价格合计
```

结果为：

| 指标 | 结果 |
|---|---:|
| 成交GMV | 13,221,498.11 BRL |
| 成交运费 | 2,202,965.54 BRL |

GMV不包含运费，也不等于平台利润或佣金收入。

## 6. 客单价

```text
客单价 = 成交GMV ÷ 成交订单数
```

```python
average_order_value = delivered_gmv / delivered_orders
```

当前结果：

```text
13,221,498.11 ÷ 96,478 = 137.04 BRL/单
```

客单价描述一笔成交订单的平均商品金额，不是单件商品平均价格。

## 7. 取消率和不可用率

```text
取消率 = canceled订单数 ÷ 全部订单数
不可用率 = unavailable订单数 ÷ 全部订单数
```

| 指标 | 分子 | 分母 | 结果 |
|---|---:|---:|---:|
| 取消率 | 625 | 99,441 | 0.63% |
| 不可用率 | 609 | 99,441 | 0.61% |

这两个指标使用全部订单为分母，因为它们衡量订单进入系统后未正常完成的比例。

## 8. 准时送达率

不是所有成交订单都有完整的预计和实际送达时间，因此分母必须限定为可以判断是否延迟的成交订单。

```text
准时送达率
= 准时送达订单数
÷ 有完整送达判断信息的成交订单数
```

当前结果：

```text
88,644 ÷ 96,470 = 91.89%
```

缺少送达信息的8笔成交订单不进入分母。

## 9. 平均评分和低评分率

低评分定义为评分不高于2分：

```text
低评分率
= 评分≤2的成交订单数
÷ 有评分的成交订单数
```

当前有646笔成交订单没有评分，因此不能把全部96,478笔成交订单作为分母。

```text
12,237 ÷ 95,832 = 12.77%
```

没有评分表示未知，不等于“不是低评分”。平均评分也只使用有评分订单。

## 10. 月度指标

Python使用`purchase_month`分组：

```python
delivered.groupby("purchase_month", as_index=False).agg(
    delivered_orders=("is_delivered", "sum"),
    delivered_gmv=("delivered_gmv", "sum"),
    purchasing_customers=("customer_unique_id", "nunique"),
)
```

月度结果包括：

- 总订单和成交订单；
- 成交GMV与成交运费；
- 购买顾客、新客和复购顾客；
- 客单价；
- 准时送达率；
- 平均评分和履约天数；
- GMV月环比。

## 11. 完整月份和月环比

原始观察期为2016-09至2018-10，但首尾月份不完整。核心比较范围为：

```text
2017-01至2018-08，共20个连续完整月份
```

月环比定义为：

```text
本月GMV ÷ 上月GMV - 1
```

只有本月和上月都是连续完整月份时才计算。因此：

- 2017-01没有有效上月，环比为空；
- 2017-02至2018-08可以计算；
- 边界月份环比保持为空。

## 12. 趋势结果

完整月份成交额峰值出现在2017-11：

```text
成交GMV：987,765.37 BRL
成交订单：7,289笔
客单价：135.51 BRL
```

同期间比较：

```text
2017年1—8月GMV：2,993,456.13 BRL
2018年1—8月GMV：7,218,125.12 BRL
增长率：141.13%
```

分析增长来源时，要同时比较订单量和客单价。GMV增长不一定代表每笔订单金额提高，也可能主要来自订单数量增加。

## 13. 输出文件

- `reports/tables/kpi_summary.csv`：总体经营指标；
- `reports/tables/monthly_metrics.csv`：月度经营指标；
- `reports/figures/01_monthly_performance.png`：月度成交额与订单量趋势图。

## 14. 本阶段通过标准

进入用户与复购阶段前，应当能解释：

1. 总订单与成交订单有什么区别？
2. 为什么GMV只统计`delivered`订单？
3. 客单价的分子和分母是什么？
4. 为什么取消率使用全部订单作为分母？
5. 为什么低评分率不能把无评分订单计入分母？
6. 为什么2017-01的月环比应该为空？
7. 为什么同比应比较相同月份范围？

下一阶段将详细分析总体复购、90天复购、RFM用户分层和首单体验。
