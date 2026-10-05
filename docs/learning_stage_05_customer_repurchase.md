# 学习阶段 5：用户复购与RFM分层

## 1. 本阶段整体要做什么

前四个阶段解决了数据、订单模型和经营指标。本阶段把分析粒度从订单切换到顾客，回答：

```text
有多少顾客购买过
→ 有多少顾客再次购买
→ 如何公平比较不同时间进入样本的顾客
→ 哪些顾客值得维护、召回或继续观察
→ 首单体验与后续复购是否存在明显关系
```

## 2. 本阶段使用什么工具

| 工具 | 本阶段的作用 |
|---|---|
| Python + pandas | 排序顾客订单、构建顾客底表、计算复购与RFM |
| SciPy | 进行卡方检验 |
| Matplotlib/Seaborn | 绘制RFM分层和首单体验复购图 |
| PowerShell | 运行学习脚本和自动化测试 |
| SQL | 使用`ROW_NUMBER`等窗口函数定义首购、第二次购买与90天样本 |
| unittest | 验证顾客唯一、观察窗口和金额守恒 |

SQL复购查询位于`sql/05_repurchase_analysis.sql`；Python完成RFM、复购诊断、统计检验和自动化校验。同期群留存留到下一阶段。

## 3. 运行第五阶段脚本

```powershell
cd D:\resume\projects\olist-ecommerce-analysis
.\.venv\Scripts\python.exe src\inspect_customer_repurchase.py
```

## 4. 顾客标识和有效购买

复购必须使用`customer_unique_id`。`customer_id`对应一次订单关系，同一个自然人在不同订单中可能拥有不同的`customer_id`。

本阶段只使用：

```text
order_status = delivered
```

取消、不可用和未完成订单不代表顾客完成了一次购买。

## 5. 数据窗口内总体复购率

先按顾客统计成交订单数：

```python
customer_frequency = (
    delivered.groupby("customer_unique_id")["order_id"].nunique()
)
```

总体复购率定义为：

```text
至少完成2笔成交订单的顾客数
÷ 至少完成1笔成交订单的顾客数
```

当前结果：

```text
2,801 ÷ 93,358 = 3.00%
```

购买频次高度集中：90,557名顾客只有一笔成交订单，占全部购买顾客约97%。

## 6. 为什么还需要90天复购率

总体复购率存在观察窗口不公平问题。例如：

- 2017年初首购的顾客有一年以上机会再次购买；
- 2018年8月首购的顾客可能只有几天观察时间。

不能把观察时间不足的顾客直接判断为“没有复购”。这种问题称为右删失。

项目将参考日期设为最后一笔成交订单日期的下一天：

```text
2018-08-30
```

顾客首购后至少还有90天数据，才进入90天复购分母：

```python
observation_days = reference_date - first_purchase_at
eligible_90d = observation_days >= 90
```

当前结果：

```text
可观察90天顾客：75,563人
观察不足90天：17,795人
90天内复购顾客：1,718人
90天复购率：1,718 ÷ 75,563 = 2.27%
```

总体复购率3.00%和90天复购率2.27%没有冲突，它们使用不同时间范围和分母。

## 7. 顾客级复购底表

最终顾客底表保持：

```text
一行 = 一名customer_unique_id
```

主要字段包括：

| 字段 | 含义 |
|---|---|
| `first_order_id` | 第一笔成交订单 |
| `first_purchase_at` | 首购时间 |
| `second_purchase_at` | 第二次购买时间 |
| `lifetime_orders` | 数据窗口内累计成交订单数 |
| `lifetime_revenue` | 累计成交金额 |
| `observation_days` | 首购后的可观察天数 |
| `eligible_90d` | 是否拥有完整90天观察期 |
| `repeat_within_90d` | 是否在首购后90天内复购 |
| `first_delivery_status` | 首单是否延迟 |
| `first_review_group` | 首单评分分组 |
| `first_order_value_band` | 首单金额五分位 |

## 8. RFM是什么

RFM从三个维度描述顾客：

| 字母 | 英文 | 本项目定义 | 判断方向 |
|---|---|---|---|
| R | Recency | 距参考日期的最近购买天数 | 越小越好 |
| F | Frequency | 成交订单数量 | 越大越好 |
| M | Monetary | 累计商品成交金额 | 越大越好 |

参考日期仍为2018-08-30，不是当前日期。

因为绝大多数顾客只有一笔订单，Frequency不能直接用普通五分位切分，否则相同的一次购买顾客会被任意分到不同等级。本项目使用透明的订单数区间：

```text
1笔 → F=1
2笔 → F=3
3笔 → F=4
4笔及以上 → F=5
```

## 9. RFM分层结果

| 分层 | 顾客数 | 含义 |
|---|---:|---|
| Champions | 59 | 近期购买且至少3笔订单 |
| Loyal | 1,171 | 至少2笔订单且最近180天内购买 |
| At-risk repeat | 1,571 | 有复购历史但较久未购买 |
| High-value new | 7,001 | 近期首购且金额较高 |
| New | 10,778 | 近期首购顾客 |
| Need attention | 52,468 | 一次购买且需要进一步观察或触达 |
| Hibernating | 20,310 | 超过365天未购买 |

分层累计覆盖93,358名购买顾客，累计金额等于成交GMV 13,221,498.11 BRL。

这些名称是分析规则产生的运营标签，不是模型预测结果。

## 10. 首单体验和90天复购

只使用75,563名拥有完整90天观察期的顾客。

### 首单配送

| 首单状态 | 顾客数 | 90天复购率 |
|---|---:|---:|
| 准时 | 68,950 | 2.29% |
| 延迟 | 6,611 | 2.06% |

### 首单评分

| 首单评分 | 顾客数 | 90天复购率 |
|---|---:|---:|
| 高评分4—5 | 58,382 | 2.27% |
| 中等评分 | 6,491 | 2.40% |
| 低评分1—2 | 10,157 | 2.22% |
| 缺失评分 | 533 | 2.25% |

这些比例之间的差异很小，不能只看排序就断言首单体验导致复购变化。

## 11. 卡方检验和Cramér's V

卡方检验回答“不同分组的复购比例是否存在统计差异”；Cramér's V回答“差异有多大”。

| 比较 | p值 | Cramér's V | 解释 |
|---|---:|---:|---|
| 首单配送与90天复购 | 0.233 | 0.004 | 未发现统计差异 |
| 首单评分与90天复购 | 0.722 | 0.003 | 未发现统计差异 |
| 首单金额分组与90天复购 | 0.000072 | 0.018 | 统计显著，但实际差异极小 |

样本量很大时，很小的比例差异也可能得到很小的p值，所以必须同时看效应量。

## 12. 输出文件

- `reports/tables/rfm_segment_summary.csv`；
- `reports/tables/repurchase_customer_base.csv`；
- `reports/tables/repurchase_by_first_delivery.csv`；
- `reports/tables/repurchase_by_first_review.csv`；
- `reports/tables/repurchase_by_first_value_band.csv`；
- `reports/tables/repurchase_by_state.csv`；
- `reports/tables/repurchase_by_first_category.csv`；
- `reports/tables/repurchase_statistical_tests.csv`；
- `reports/figures/02_rfm_segments.png`；
- `reports/figures/06_repurchase_first_experience.png`。

## 13. 本阶段通过标准

进入同期群阶段前，应当能解释：

1. 为什么复购必须使用`customer_unique_id`？
2. 总体复购率与90天复购率有什么区别？
3. 什么是观察窗口不足和右删失？
4. R、F、M分别表示什么？
5. 为什么Frequency没有直接使用普通五分位？
6. 为什么p值很小仍然不能说明业务影响很大？

下一阶段将按首购月份建立同期群，观察同一批顾客在第1个月、第2个月等月份是否再次购买。
