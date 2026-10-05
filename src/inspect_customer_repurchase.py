"""Explain and validate stage-five customer repurchase and RFM analysis.

The script is read-only. It contrasts lifetime-window and 90-day repurchase,
prints purchase-frequency and RFM segments, and summarizes first-order
experience comparisons with their statistical tests.
"""

from __future__ import annotations

import math
import sys

import pandas as pd

from run_analysis import (
    build_commercial_marts,
    build_kpis,
    build_order_model,
    build_repurchase_analysis,
    build_rfm,
    load_tables,
)


def heading(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def print_repurchase_overview(
    order_model: pd.DataFrame,
    customer_base: pd.DataFrame,
    kpi_values: dict[str, float],
) -> None:
    heading("一、总体复购与90天复购")
    delivered = order_model[order_model["is_delivered"]]
    reference_date = delivered["order_purchase_timestamp"].max().normalize() + pd.Timedelta(days=1)
    eligible = customer_base[customer_base["eligible_90d"]]
    repeat_90d = int(eligible["repeat_within_90d"].sum())

    print(f"数据参考日期：{reference_date:%Y-%m-%d}")
    print(
        f"总体复购：{int(kpi_values['repeat_customers']):,}名复购顾客 ÷ "
        f"{int(kpi_values['active_customers']):,}名购买顾客 "
        f"= {kpi_values['repeat_customer_rate']:.2%}"
    )
    print(
        f"90天复购：{repeat_90d:,}名90天内复购顾客 ÷ "
        f"{len(eligible):,}名拥有完整90天观察期的顾客 "
        f"= {eligible['repeat_within_90d'].mean():.2%}"
    )
    print(f"观察期不足90天、未进入90天分母：{(~customer_base['eligible_90d']).sum():,}人")
    print("结论：两个复购率使用不同观察窗口和分母，不能互相替代。")


def print_frequency_and_rfm(rfm: pd.DataFrame, segment_summary: pd.DataFrame) -> None:
    heading("二、购买频次与RFM分层")
    frequency = (
        rfm["frequency"]
        .value_counts()
        .sort_index()
        .rename_axis("成交订单数")
        .reset_index(name="顾客数")
    )
    frequency["顾客占比"] = frequency["顾客数"] / len(rfm)
    frequency["顾客占比"] = frequency["顾客占比"].map(lambda x: f"{x:.2%}")
    print("购买频次分布：")
    print(frequency.to_string(index=False))

    display = segment_summary[
        [
            "segment",
            "customers",
            "customer_share",
            "revenue",
            "revenue_share",
            "average_orders",
            "average_recency_days",
        ]
    ].copy()
    display["customer_share"] = display["customer_share"].map(lambda x: f"{x:.2%}")
    display["revenue_share"] = display["revenue_share"].map(lambda x: f"{x:.2%}")
    display = display.rename(
        columns={
            "segment": "分层",
            "customers": "顾客数",
            "customer_share": "顾客占比",
            "revenue": "累计金额",
            "revenue_share": "金额占比",
            "average_orders": "平均订单数",
            "average_recency_days": "平均最近购买天数",
        }
    )
    print("\nRFM分层：")
    print(
        display.to_string(
            index=False,
            formatters={
                "累计金额": "{:,.2f}".format,
                "平均订单数": "{:.2f}".format,
                "平均最近购买天数": "{:.1f}".format,
            },
        )
    )


def format_summary(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    display = frame[
        [dimension, "customers", "repeat_90d_customers", "repeat_90d_rate"]
    ].copy()
    display["repeat_90d_rate"] = display["repeat_90d_rate"].map(lambda x: f"{x:.2%}")
    return display.rename(
        columns={
            dimension: "分组",
            "customers": "顾客数",
            "repeat_90d_customers": "90天复购顾客",
            "repeat_90d_rate": "90天复购率",
        }
    )


def print_first_order_comparisons(summaries: dict[str, pd.DataFrame]) -> None:
    heading("三、首单体验与90天复购")
    print("首单配送状态：")
    print(
        format_summary(
            summaries["repurchase_by_first_delivery"], "first_delivery_status"
        ).to_string(index=False)
    )
    print("\n首单评分：")
    print(
        format_summary(
            summaries["repurchase_by_first_review"], "first_review_group"
        ).to_string(index=False)
    )
    print("\n首单金额五分位：")
    print(
        format_summary(
            summaries["repurchase_by_first_value_band"], "first_order_value_band"
        ).to_string(index=False)
    )


def print_statistical_tests(tests: pd.DataFrame) -> None:
    heading("四、统计检验与效应量")
    display = tests[["analysis", "customers", "p_value", "cramers_v"]].copy()
    display["统计判断"] = display["p_value"].map(
        lambda x: "存在统计差异" if x < 0.05 else "未发现统计差异"
    )
    display["实际差异"] = display["cramers_v"].map(
        lambda x: "极小" if x < 0.05 else "需要结合业务判断"
    )
    display = display.rename(
        columns={
            "analysis": "比较项目",
            "customers": "检验样本",
            "p_value": "p值",
            "cramers_v": "Cramér's V",
        }
    )
    print(display.to_string(index=False))
    print("结论：首单金额分组达到统计显著，但效应量仍然极小。")


def validate_results(
    order_model: pd.DataFrame,
    customer_base: pd.DataFrame,
    rfm: pd.DataFrame,
    segment_summary: pd.DataFrame,
    tests: pd.DataFrame,
) -> None:
    heading("五、阶段验收")
    delivered = order_model[order_model["is_delivered"]]
    eligible = customer_base[customer_base["eligible_90d"]]
    test_index = tests.set_index("analysis")
    checks = {
        "顾客级底表唯一": not customer_base["customer_unique_id"].duplicated().any(),
        "购买顾客为93,358人": len(customer_base) == 93_358,
        "总体复购顾客为2,801人": int(customer_base["lifetime_orders"].ge(2).sum()) == 2_801,
        "90天可观察顾客为75,563人": len(eligible) == 75_563,
        "90天复购顾客为1,718人": int(eligible["repeat_within_90d"].sum()) == 1_718,
        "RFM覆盖全部购买顾客": len(rfm) == 93_358,
        "RFM金额等于成交GMV": math.isclose(
            rfm["monetary"].sum(), delivered["item_revenue"].sum(), rel_tol=1e-12
        ),
        "RFM顾客占比合计100%": math.isclose(segment_summary["customer_share"].sum(), 1.0),
        "RFM金额占比合计100%": math.isclose(segment_summary["revenue_share"].sum(), 1.0),
        "首单金额检验样本为75,563人": int(
            test_index.loc["First order value band vs 90-day repeat", "customers"]
        )
        == 75_563,
    }
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'ERROR'}｜{name}")
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssertionError("用户复购检查失败：" + "、".join(failed))
    print("结论：总体复购、90天观察窗口、RFM和统计检验均通过验收。")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("第五阶段：用户复购与RFM分层")
    print("本脚本在内存中完成顾客级分析，不修改原始CSV。")

    tables = load_tables()
    order_model, _ = build_order_model(tables)
    item_detail, _, _, _, _ = build_commercial_marts(tables, order_model)
    _, kpi_values = build_kpis(order_model)
    rfm, segment_summary = build_rfm(order_model)
    customer_base, summaries, tests = build_repurchase_analysis(order_model, item_detail)

    print_repurchase_overview(order_model, customer_base, kpi_values)
    print_frequency_and_rfm(rfm, segment_summary)
    print_first_order_comparisons(summaries)
    print_statistical_tests(tests)
    validate_results(order_model, customer_base, rfm, segment_summary, tests)


if __name__ == "__main__":
    main()
