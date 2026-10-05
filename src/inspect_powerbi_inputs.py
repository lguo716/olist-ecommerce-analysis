"""Preflight the eleven CSV inputs used by the stage-nine Power BI report.

The script is read-only. It verifies file/schema completeness, table grains,
diagnostic denominator fields, and the benchmark values that the PBIX must
reproduce after import.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class InputSpec:
    path: str
    rows: int
    required_columns: tuple[str, ...]


INPUT_SPECS: dict[str, InputSpec] = {
    "powerbi_orders": InputSpec(
        "data/processed/powerbi_orders.csv",
        99_441,
        (
            "order_id",
            "customer_unique_id",
            "order_status",
            "purchase_date",
            "purchase_month",
            "customer_state",
            "item_revenue",
            "freight_value",
            "review_score",
            "delivery_days",
            "delivery_delta_days",
            "is_late",
        ),
    ),
    "powerbi_order_items": InputSpec(
        "data/processed/powerbi_order_items.csv",
        112_650,
        (
            "order_id",
            "order_item_id",
            "product_id",
            "seller_id",
            "price",
            "freight_value",
            "category",
            "product_weight_g",
            "product_volume_cm3",
            "order_status",
            "is_delivered",
        ),
    ),
    "powerbi_customers": InputSpec(
        "data/processed/powerbi_customers.csv",
        93_358,
        (
            "customer_unique_id",
            "frequency",
            "monetary",
            "segment",
            "eligible_90d",
            "repeat_within_90d",
        ),
    ),
    "monthly_metrics": InputSpec(
        "reports/tables/monthly_metrics.csv",
        25,
        (
            "purchase_month",
            "delivered_orders",
            "delivered_gmv",
            "new_customers",
            "returning_customers",
            "is_complete_core_month",
        ),
    ),
    "cohort_retention_tidy": InputSpec(
        "reports/tables/cohort_retention_tidy.csv",
        278,
        (
            "cohort_month",
            "cohort_index",
            "active_customers",
            "cohort_size",
            "retention_rate",
        ),
    ),
    "category_performance": InputSpec(
        "reports/tables/category_performance.csv",
        74,
        (
            "category",
            "revenue",
            "orders",
            "reviewed_orders",
            "low_review_orders",
            "average_review_score",
            "low_review_rate",
            "late_delivery_rate",
            "freight_to_revenue_rate",
            "reliable_sample",
        ),
    ),
    "category_growth_quality": InputSpec(
        "reports/tables/category_growth_quality.csv",
        74,
        (
            "category",
            "revenue_growth",
            "review_score_change",
            "late_rate_change",
            "comparable_sample",
            "growth_quality_risk",
        ),
    ),
    "seller_scorecard": InputSpec(
        "reports/tables/seller_scorecard.csv",
        2_970,
        (
            "seller_id",
            "orders",
            "revenue",
            "reviewed_orders",
            "low_review_orders",
            "average_review_score",
            "low_review_rate",
            "late_delivery_rate",
            "reliable_sample",
        ),
    ),
    "state_performance": InputSpec(
        "reports/tables/state_performance.csv",
        27,
        (
            "customer_state",
            "orders",
            "revenue",
            "reviewed_orders",
            "low_review_orders",
            "average_review_score",
            "low_review_rate",
            "late_delivery_rate",
            "reliable_sample",
        ),
    ),
    "repurchase_by_first_delivery": InputSpec(
        "reports/tables/repurchase_by_first_delivery.csv",
        3,
        (
            "first_delivery_status",
            "customers",
            "repeat_90d_customers",
            "repeat_90d_rate",
            "reliable_sample",
        ),
    ),
    "repurchase_by_first_review": InputSpec(
        "reports/tables/repurchase_by_first_review.csv",
        4,
        (
            "first_review_group",
            "customers",
            "repeat_90d_customers",
            "repeat_90d_rate",
            "reliable_sample",
        ),
    ),
}


def heading(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def load_inputs(root: Path = PROJECT_ROOT) -> dict[str, pd.DataFrame]:
    """Load the Power BI inputs after confirming every file exists."""
    missing = [spec.path for spec in INPUT_SPECS.values() if not (root / spec.path).is_file()]
    if missing:
        raise FileNotFoundError("Power BI输入文件缺失：" + "、".join(missing))
    return {
        name: pd.read_csv(root / spec.path, low_memory=False)
        for name, spec in INPUT_SPECS.items()
    }


def _check(name: str, passed: bool, actual: str, expected: str) -> dict[str, object]:
    return {
        "check": name,
        "status": "PASS" if passed else "ERROR",
        "actual": actual,
        "expected": expected,
    }


def build_preflight_checks(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Return all structural and business baseline checks."""
    checks: list[dict[str, object]] = []

    for name, spec in INPUT_SPECS.items():
        frame = frames[name]
        missing_columns = sorted(set(spec.required_columns) - set(frame.columns))
        checks.append(
            _check(
                f"{name}行数",
                len(frame) == spec.rows,
                f"{len(frame):,}",
                f"{spec.rows:,}",
            )
        )
        checks.append(
            _check(
                f"{name}必需字段",
                not missing_columns,
                "完整" if not missing_columns else "缺少：" + ", ".join(missing_columns),
                "完整",
            )
        )

    orders = frames["powerbi_orders"]
    items = frames["powerbi_order_items"]
    customers = frames["powerbi_customers"]
    cohort = frames["cohort_retention_tidy"]

    checks.extend(
        [
            _check(
                "订单表一单一行",
                not orders["order_id"].duplicated().any(),
                f"重复{int(orders['order_id'].duplicated().sum()):,}行",
                "重复0行",
            ),
            _check(
                "商品表业务键唯一",
                not items.duplicated(["order_id", "order_item_id"]).any(),
                f"重复{int(items.duplicated(['order_id', 'order_item_id']).sum()):,}行",
                "重复0行",
            ),
            _check(
                "顾客表一人一行",
                not customers["customer_unique_id"].duplicated().any(),
                f"重复{int(customers['customer_unique_id'].duplicated().sum()):,}行",
                "重复0行",
            ),
        ]
    )

    delivered = orders[orders["order_status"].eq("delivered")]
    reviewed = delivered[delivered["review_score"].notna()]
    known_delivery = delivered[delivered["is_late"].notna()]
    repeat_customers = delivered.groupby("customer_unique_id")["order_id"].nunique().ge(2)

    total_orders = len(orders)
    delivered_orders = len(delivered)
    delivered_gmv = float(delivered["item_revenue"].sum())
    average_order_value = delivered_gmv / delivered_orders
    purchasing_customers = delivered["customer_unique_id"].nunique()
    repeated = int(repeat_customers.sum())
    repeat_rate = repeated / purchasing_customers
    on_time_orders = int(known_delivery["is_late"].eq(False).sum())
    on_time_rate = on_time_orders / len(known_delivery)
    low_review_orders = int(reviewed["review_score"].le(2).sum())
    low_review_rate = low_review_orders / len(reviewed)

    baseline_checks = [
        ("总订单", total_orders == 99_441, f"{total_orders:,}", "99,441"),
        ("成交订单", delivered_orders == 96_478, f"{delivered_orders:,}", "96,478"),
        (
            "成交GMV",
            math.isclose(delivered_gmv, 13_221_498.11, abs_tol=0.01),
            f"{delivered_gmv:,.2f}",
            "13,221,498.11 BRL",
        ),
        (
            "客单价",
            math.isclose(average_order_value, 137.0415857501192),
            f"{average_order_value:.2f}",
            "137.04 BRL",
        ),
        (
            "成交顾客",
            purchasing_customers == 93_358,
            f"{purchasing_customers:,}",
            "93,358",
        ),
        ("复购顾客", repeated == 2_801, f"{repeated:,}", "2,801"),
        (
            "总体复购率",
            math.isclose(repeat_rate, 0.03000278497825575),
            f"{repeat_rate:.2%}",
            "3.00%",
        ),
        (
            "准时送达",
            on_time_orders == 88_644 and len(known_delivery) == 96_470,
            f"{on_time_orders:,}/{len(known_delivery):,} = {on_time_rate:.2%}",
            "88,644/96,470 = 91.89%",
        ),
        (
            "平台低评分",
            low_review_orders == 12_237 and len(reviewed) == 95_832,
            f"{low_review_orders:,}/{len(reviewed):,} = {low_review_rate:.2%}",
            "12,237/95,832 = 12.77%",
        ),
        (
            "90天可观察顾客",
            int(customers["eligible_90d"].eq(True).sum()) == 75_563,
            f"{int(customers['eligible_90d'].eq(True).sum()):,}",
            "75,563",
        ),
    ]
    checks.extend(_check(name, passed, actual, expected) for name, passed, actual, expected in baseline_checks)

    month_zero = cohort[cohort["cohort_index"].eq(0)]
    checks.append(
        _check(
            "同期群第0月留存",
            len(month_zero) == 23 and month_zero["retention_rate"].eq(1).all(),
            f"{len(month_zero)}个同期群，100%单元格{int(month_zero['retention_rate'].eq(1).sum())}个",
            "23个同期群全部100%",
        )
    )

    analysis_sample = delivered[
        delivered["is_late"].notna() & delivered["review_score"].notna()
    ]
    late = analysis_sample[analysis_sample["is_late"].eq(True)]
    on_time = analysis_sample[analysis_sample["is_late"].eq(False)]
    late_low_rate = late["review_score"].le(2).mean()
    on_time_low_rate = on_time["review_score"].le(2).mean()
    checks.extend(
        [
            _check(
                "延迟订单低评分率",
                len(late) == 7_661 and math.isclose(late_low_rate, 0.5398773006134969),
                f"{late['review_score'].le(2).sum():,}/{len(late):,} = {late_low_rate:.2%}",
                "4,136/7,661 = 53.99%",
            ),
            _check(
                "准时订单低评分率",
                len(on_time) == 88_163 and math.isclose(on_time_low_rate, 0.09187527647652644),
                f"{on_time['review_score'].le(2).sum():,}/{len(on_time):,} = {on_time_low_rate:.2%}",
                "8,100/88,163 = 9.19%",
            ),
        ]
    )

    for table_name in ("category_performance", "seller_scorecard", "state_performance"):
        frame = frames[table_name]
        fields = {"reviewed_orders", "low_review_orders", "low_review_rate"}
        checks.append(
            _check(
                f"{table_name}评分分母字段",
                fields.issubset(frame.columns),
                "完整" if fields.issubset(frame.columns) else "不完整",
                "完整",
            )
        )

    return pd.DataFrame(checks)


def print_stage_overview() -> None:
    heading("一、本阶段整体目标和工具")
    print("业务目标：把前八阶段的模型和结果做成四页可筛选、可下钻的经营看板。")
    print("Python+pandas：在导入前验证11张CSV、表粒度和核心数字。")
    print("Power BI Desktop：建立关系、DAX度量、交互图表并保存本地PBIX。")
    print("DAX：让经营指标按日期、州等筛选上下文动态重新计算。")
    print("本脚本只读CSV，不修改原始数据或分析结果。")


def print_inventory(frames: dict[str, pd.DataFrame]) -> None:
    heading("二、11张Power BI输入表")
    rows = []
    for name, spec in INPUT_SPECS.items():
        frame = frames[name]
        rows.append(
            {
                "表名": name,
                "行数": f"{len(frame):,}",
                "列数": len(frame.columns),
                "用途": {
                    "powerbi_orders": "订单KPI、日期趋势、物流与评分",
                    "powerbi_order_items": "品类、商家、商品重量体积与运费",
                    "powerbi_customers": "RFM、购买频次、90天复购",
                    "monthly_metrics": "新客与复购顾客月度趋势",
                    "cohort_retention_tidy": "同期群留存热力矩阵",
                    "category_performance": "品类经营矩阵",
                    "category_growth_quality": "品类增长质量散点图",
                    "seller_scorecard": "商家关注表和象限图",
                    "state_performance": "州级经营与履约矩阵",
                    "repurchase_by_first_delivery": "首单物流与90天复购",
                    "repurchase_by_first_review": "首单评分与90天复购",
                }[name],
                "文件": spec.path,
            }
        )
    print(pd.DataFrame(rows).to_string(index=False))


def print_model_rules() -> None:
    heading("三、Power BI模型规则")
    print("Date[Date] 1 → * powerbi_orders[purchase_date]，单向。")
    print("powerbi_customers[customer_unique_id] 1 → * powerbi_orders[customer_unique_id]，单向。")
    print("powerbi_orders[order_id] 1 → * powerbi_order_items[order_id]，单向。")
    print("月度、同期群、州、品类、商家和首单体验汇总表保持独立。")
    print("平台GMV使用订单表item_revenue；品类GMV使用商品表price或品类汇总表revenue。")


def validate_results(checks: pd.DataFrame) -> None:
    heading("四、导入前验收")
    for row in checks.itertuples(index=False):
        print(f"{row.status}｜{row.check}｜实际：{row.actual}｜期望：{row.expected}")
    failed = checks[checks["status"].eq("ERROR")]
    if not failed.empty:
        raise AssertionError("Power BI输入预检失败：" + "、".join(failed["check"]))
    print(f"\n结论：{len(checks)}项检查全部通过，可以导入Power BI Desktop。")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("第九阶段：Power BI四页经营看板——输入预检")
    frames = load_inputs()
    checks = build_preflight_checks(frames)
    print_stage_overview()
    print_inventory(frames)
    print_model_rules()
    validate_results(checks)


if __name__ == "__main__":
    main()
