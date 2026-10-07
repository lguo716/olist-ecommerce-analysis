# 电商经营分析与复购诊断

基于 Olist 巴西电商公开数据构建的端到端数据分析项目。项目覆盖原始数据校验、订单级数据建模、经营指标分析、RFM 用户分层、同期群留存、物流履约诊断、商家与品类分析，以及已完成的四页 Power BI 交互看板。

技术栈：**SQL（MySQL 8） · Python · Power BI**。

## 技术路线

```text
原始关系数据 → 数据质量检查 → 订单级分析模型
→ 经营指标与用户分析 → 统计检验与问题定位 → Power BI经营看板
```

| 技术模块 | 职责 | 项目入口 |
|---|---|---|
| SQL / MySQL | 建表、质量规则、明细聚合、关联视图、经营与复购指标查询 | `sql/01_mysql_schema.sql`至`sql/06_commercial_diagnostics.sql` |
| Python | 自动化数据检查、分析结果生成、RFM、同期群、统计检验与图表 | `src/run_analysis.py`与各阶段学习脚本 |
| Power BI | 语义模型、DAX动态指标、筛选、下钻和四页经营看板 | `powerbi/olist_ecommerce_analysis.pbix` |

三类模块使用统一的订单粒度、顾客标识和指标口径；分析结果通过CSV接口进入Power BI。

## 看板预览

![经营总览](reports/figures/powerbi_01_business_overview.png)

四页完整截图见[验收记录](reports/project_acceptance.md)。

## 最终交付

- [完整项目流程与每一步解释](docs/project_complete_walkthrough.md)：从业务问题到经营建议，包含计算方法、实际结果、工具分工和重新运行方式。
- [最终 Power BI 看板](powerbi/olist_ecommerce_analysis.pbix)：经营总览、用户与复购、物流与满意度、品类与商家四页，已实际保存、关闭重开并刷新验证。
- [可编辑 Power BI 源项目](powerbi/Olist.pbip)：与相邻的 `Olist.Report` 和 `Olist.SemanticModel` 目录一起保留。
- [项目验收记录与四页截图](reports/project_acceptance.md)：31项Python测试、41项输入检查、45项实际DAX核对全部通过。

首页默认使用2017-01至2018-08完整月份，因此GMV显示 **13,181,027.13 BRL**；全数据窗口GMV为 **13,221,498.11 BRL**。全窗口核对需清除首页“完整月份”页面筛选，详细说明见完整流程文档。

## 学习入口

如果目标是不只运行现有代码，而是从业务问题开始理解整个项目，请按以下顺序学习：

1. [学习阶段 1：业务问题与原始数据](docs/learning_stage_01_business_and_data.md)

```powershell
.\.venv\Scripts\python.exe src\inspect_raw_tables.py
```

2. [学习阶段 2：数据质量检查](docs/learning_stage_02_data_quality.md)

```powershell
.\.venv\Scripts\python.exe src\inspect_data_quality.py
```

3. [学习阶段 3：建立一单一行的订单模型](docs/learning_stage_03_order_model.md)

```powershell
.\.venv\Scripts\python.exe src\inspect_order_model.py
```

4. [学习阶段 4：经营指标与月度趋势](docs/learning_stage_04_business_metrics.md)

```powershell
.\.venv\Scripts\python.exe src\inspect_business_metrics.py
```

5. [学习阶段 5：用户复购与RFM分层](docs/learning_stage_05_customer_repurchase.md)

```powershell
.\.venv\Scripts\python.exe src\inspect_customer_repurchase.py
```

6. [学习阶段 6：同期群留存分析](docs/learning_stage_06_cohort_retention.md)

```powershell
.\.venv\Scripts\python.exe src\inspect_cohort_retention.py
```

7. [学习阶段 7：物流履约与用户评分分析](docs/learning_stage_07_delivery_satisfaction.md)

```powershell
.\.venv\Scripts\python.exe src\inspect_delivery_satisfaction.py
```

8. [学习阶段 8：州、品类与商家经营诊断](docs/learning_stage_08_commercial_diagnostics.md)

```powershell
.\.venv\Scripts\python.exe src\inspect_commercial_diagnostics.py
```

9. [学习阶段 9：Power BI四页经营看板](docs/learning_stage_09_powerbi_dashboard.md)

```powershell
.\.venv\Scripts\python.exe src\inspect_powerbi_inputs.py
```

Power BI看板已经完成；需要复习或亲自重建时，按[`powerbi/build_checklist.md`](powerbi/build_checklist.md)逐个检查点学习。现有结果作为核对答案，不代替亲自理解和验证。

## 业务问题

本项目围绕四个管理问题展开：

1. 平台的订单、成交额、客单价和复购表现如何变化？
2. 哪些用户值得重点维护或召回？
3. 物流延迟是否与用户低评分显著相关？
4. 哪些州、品类和商家的经营或履约表现需要关注？

## 数据来源

- 官方项目说明：<https://github.com/olist/work-at-olist-data>
- Kaggle 数据页：<https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce>
- 范围：2016—2018 年约 10 万笔匿名订单，含顾客、订单、商品、支付、评价、卖家及地理位置等 9 张关系表。

原始数据仅用于非商业分析。请遵守数据来源页面标注的许可条款。

## 项目结构

```text
olist-ecommerce-analysis/
├── data/
│   ├── raw/                 # 原始 CSV，不提交版本库
│   └── processed/           # 分析及 Power BI 输出表
├── docs/
│   ├── data_model.md        # 数据模型与连接粒度
│   ├── data_dictionary.md   # 原始字段与输出表字典
│   ├── implementation_roadmap.md
│   ├── metric_definitions.md
│   ├── project_complete_walkthrough.md # 完整项目流程与学习复盘
│   └── powerbi_design.md
├── reports/
│   ├── figures/             # 自动生成的图表
│   ├── tables/              # 汇总结果
│   ├── findings.md          # 自动生成的分析结论
│   └── project_acceptance.md # 最终验收与四页截图
├── powerbi/
│   ├── date_table.dax       # 日期表
│   ├── measures.dax         # 核心度量值
│   ├── build_checklist.md   # 四页看板逐项搭建与验收
│   ├── olist_ecommerce_analysis.pbix # 已完成的本地四页看板
│   ├── Olist.pbip           # 可编辑源项目，配套Report和SemanticModel目录
│   ├── desktop_verification.json # 实际Power BI模型的DAX核对结果
│   └── olist-theme.json     # 看板主题
├── sql/
│   ├── 01_mysql_schema.sql
│   ├── 02_quality_checks.sql
│   ├── 03_business_metrics.sql
│   ├── 04_powerbi_views.sql
│   ├── 05_repurchase_analysis.sql
│   └── 06_commercial_diagnostics.sql
├── src/
│   ├── download_data.ps1
│   ├── inspect_powerbi_inputs.py
│   └── run_analysis.py
└── requirements.txt
```

## 快速运行

在克隆后的仓库目录打开PowerShell。原始CSV不随仓库上传，先从Olist官方仓库下载，再生成处理表；已有本地数据时可跳过下载。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File .\src\download_data.ps1
.\.venv\Scripts\python.exe src\run_analysis.py
.\.venv\Scripts\python.exe src\inspect_powerbi_inputs.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

PBIX包含已导入的匿名公开数据，可直接打开查看。重新刷新时，先生成CSV，再在Power Query中将11张输入表的本机路径调整为当前克隆目录。SQL模块使用MySQL 8，按`sql/`目录编号依次建表、导入CSV、检查数据并建立分析视图；Python自动化分析入口如上。

上传范围：代码、SQL、文档、汇总结果、11张静态/看板截图、最终PBIX和可编辑PBIP源文件。原始CSV、行级派生CSV、虚拟环境、缓存及备份不上传。数据来源与第三方声明见[NOTICE.md](NOTICE.md)。

运行完成后：

- `reports/findings.md`：主要业务结论与统计检验结果；
- `reports/figures/`：分析图与看板截图；
- `reports/tables/`：核心汇总结果；
- `data/processed/powerbi_*.csv`：可直接导入 Power BI 的数据表。
- `powerbi/build_checklist.md`：从导入、关系到四页图表的精确搭建清单。
- `powerbi/olist_ecommerce_analysis.pbix`：最终看板；更新CSV后在Power BI中点击“主页 → 刷新”，再保存。

## 指标口径说明

- 成交订单：状态为 `delivered` 的订单。
- 成交额：成交订单商品价格之和，不包含运费；属于离线数据集口径，不等同于企业财务确认收入。
- 客单价：成交额 ÷ 成交订单数。
- 复购率：至少完成 2 笔成交订单的顾客数 ÷ 至少完成 1 笔成交订单的顾客数。
- 准时送达率：实际送达时间不晚于预计送达时间的成交订单数 ÷ 有完整送达信息的成交订单数。

完整口径见 [docs/metric_definitions.md](docs/metric_definitions.md)。

## 设计原则

- 先分别聚合商品、支付和评价数据，再连接到订单表，避免多对多连接导致金额重复。
- 用户分析使用跨订单稳定的 `customer_unique_id`，而不是单次订单使用的 `customer_id`。
- 时间趋势默认标注首尾不完整月份，避免将残缺月份误判为业务下滑。
- 公开观察性数据只能说明相关关系；“物流延迟导致低评分”等因果结论不会被直接宣称。

## 当前状态

- [x] 下载并保留 9 张原始表
- [x] 建立指标口径与订单级模型
- [x] 编写自动化分析与质量校验脚本
- [x] 编写 MySQL 建表、质量校验与业务查询脚本
- [x] 生成并复核实际分析结果
- [x] 输出 Power BI 数据集、主题、DAX 度量及四页搭建清单
- [x] 在 Power BI Desktop 中生成四页 `.pbix` 并保存页面截图
- [x] 关闭重开、刷新数据，核对实际DAX和筛选/州城市下钻
- [x] 完整流程总结、业务建议和最终验收记录

项目采用SQL、Python与Power BI分层设计，数据建模、分析验证与交互展示共享同一套业务口径。
