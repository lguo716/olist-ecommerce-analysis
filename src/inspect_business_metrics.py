"""Explain and validate the stage-four business metrics.

This script is read-only. It builds the verified order model in memory, prints
the numerator and denominator of each major KPI, and summarizes the complete
monthly comparison window.
"""

from __future__ import annotations

import math
import sys

import pandas as pd

from run_analysis import build_kpis, build_monthly_metrics, build_order_model, load_tables


def heading(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def print_status_distribution(order_model: pd.DataFrame) -> None:
    heading("一、订单状态分布")
    status = order_model["order_status"].value_counts().rename_axis("订单状态").reset_index(name="订单数")
    status["占全部订单比例"] = status["订单数"] / len(order_model)
    status["占全部订单比例"] = status["占全部订单比例"].map(lambda x: f"{x:.2%}")
    print(status.to_string(index=False))


def print_kpi_formulas(order_model: pd.DataFrame, values: dict[str, float]) -> None:
    heading("二、核心指标的分子与分母")
    delivered = order_model[order_model["is_delivered"]]
    delivery_known = delivered[delivered["is_late"].notna()]
    reviewed = delivered[delivered["review_score"].notna()]

    rows = [
        ("总订单数", "不同order_id", len(order_model), None, values["total_orders"], "笔"),
        (
            "成交订单数",
            "状态为delivered的订单",
            len(delivered),
            None,
            values["delivered_orders"],
            "笔",
        ),
        (
            "成交GMV",
            "成交订单商品金额合计",
            delivered["item_revenue"].sum(),
            None,
            values["delivered_gmv"],
            "BRL",
        ),
        (
            "客单价",
            "成交GMV ÷ 成交订单数",
            delivered["item_revenue"].sum(),
            len(delivered),
            values["average_order_value"],
            "BRL/单",
        ),
        (
            "取消率",
            "取消订单 ÷ 全部订单",
            int(order_model["is_canceled"].sum()),
            len(order_model),
            values["cancellation_rate"],
            "%",
        ),
        (
            "不可用率",
            "unavailable订单 ÷ 全部订单",
            int(order_model["is_unavailable"].sum()),
            len(order_model),
            values["unavailable_rate"],
            "%",
        ),
        (
            "准时送达率",
            "准时订单 ÷ 可判断送达状态的成交订单",
            int((~delivery_known["is_late"].astype(bool)).sum()),
            len(delivery_known),
            values["on_time_delivery_rate"],
            "%",
        ),
        (
            "低评分率",
            "评分≤2订单 ÷ 有评分的成交订单",
            int(reviewed["review_score"].le(2).sum()),
            len(reviewed),
            values["low_review_rate"],
            "%",
        ),
    ]

    display_rows = []
    for metric, formula, numerator, denominator, result, unit in rows:
        if unit == "%":
            result_text = f"{result:.2%}"
        elif unit == "BRL":
            result_text = f"{result:,.2f} BRL"
        elif unit == "BRL/单":
            result_text = f"{result:,.2f} BRL/单"
        else:
            result_text = f"{int(result):,} 笔"
        display_rows.append(
            {
                "指标": metric,
                "公式": formula,
                "分子": f"{numerator:,.2f}" if isinstance(numerator, float) else f"{numerator:,}",
                "分母": "—" if denominator is None else f"{denominator:,}",
                "结果": result_text,
            }
        )
    print(pd.DataFrame(display_rows).to_string(index=False))
    print(f"平均履约天数：{values['average_delivery_days']:.2f} 天")
    print(f"有评分成交订单平均评分：{values['average_review_score']:.2f} 分")


def print_monthly_analysis(monthly: pd.DataFrame) -> None:
    heading("三、完整月份趋势")
    core = monthly[monthly["is_complete_core_month"]].copy()
    peak = core.loc[core["delivered_gmv"].idxmax()]
    first_period = core[
        core["purchase_month"].dt.year.eq(2017) & core["purchase_month"].dt.month.le(8)
    ]["delivered_gmv"].sum()
    second_period = core[
        core["purchase_month"].dt.year.eq(2018) & core["purchase_month"].dt.month.le(8)
    ]["delivered_gmv"].sum()
    growth = second_period / first_period - 1

    print(
        f"核心月份：{core['purchase_month'].min():%Y-%m} 至 "
        f"{core['purchase_month'].max():%Y-%m}，共 {len(core)} 个月"
    )
    print(
        f"成交额峰值：{peak['purchase_month']:%Y-%m}｜"
        f"GMV {peak['delivered_gmv']:,.2f} BRL｜"
        f"成交订单 {int(peak['delivered_orders']):,}｜"
        f"客单价 {peak['average_order_value']:,.2f} BRL"
    )
    print(f"2017年1—8月GMV：{first_period:,.2f} BRL")
    print(f"2018年1—8月GMV：{second_period:,.2f} BRL")
    print(f"同期间增长：{growth:.2%}")

    display = core[
        [
            "purchase_month",
            "delivered_orders",
            "delivered_gmv",
            "average_order_value",
            "mom_gmv_growth",
        ]
    ].copy()
    display["purchase_month"] = display["purchase_month"].dt.strftime("%Y-%m")
    display["mom_gmv_growth"] = display["mom_gmv_growth"].map(
        lambda x: "—" if pd.isna(x) else f"{x:.2%}"
    )
    display = display.rename(
        columns={
            "purchase_month": "月份",
            "delivered_orders": "成交订单",
            "delivered_gmv": "成交GMV",
            "average_order_value": "客单价",
            "mom_gmv_growth": "GMV月环比",
        }
    )
    print("\n核心月份明细：")
    print(display.to_string(index=False, formatters={"成交GMV": "{:,.2f}".format, "客单价": "{:,.2f}".format}))


def validate_results(order_model: pd.DataFrame, values: dict[str, float], monthly: pd.DataFrame) -> None:
    heading("四、阶段验收")
    delivered = order_model[order_model["is_delivered"]]
    reviewed = delivered[delivered["review_score"].notna()]
    core = monthly[monthly["is_complete_core_month"]]
    checks = {
        "总订单数为99,441": values["total_orders"] == 99_441,
        "成交订单数为96,478": values["delivered_orders"] == 96_478,
        "成交GMV基准一致": math.isclose(values["delivered_gmv"], 13_221_498.11, abs_tol=0.01),
        "低评分率只使用有评分订单": math.isclose(
            values["low_review_rate"], reviewed["review_score"].le(2).mean(), rel_tol=1e-12
        ),
        "完整核心月份共20个月": len(core) == 20,
        "2017-01月环比为空": pd.isna(
            monthly.loc[monthly["purchase_month"].eq("2017-01-01"), "mom_gmv_growth"].iloc[0]
        ),
    }
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'ERROR'}｜{name}")
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssertionError("经营指标检查失败：" + "、".join(failed))
    print("结论：总体指标、评分分母和月度时间窗口均符合既定口径。")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("第四阶段：经营指标与月度趋势分析")
    print("本脚本在内存中计算指标，不修改原始CSV。")

    tables = load_tables()
    order_model, _ = build_order_model(tables)
    _, values = build_kpis(order_model)
    monthly = build_monthly_metrics(order_model)

    print_status_distribution(order_model)
    print_kpi_formulas(order_model, values)
    print_monthly_analysis(monthly)
    validate_results(order_model, values, monthly)


if __name__ == "__main__":
    main()
