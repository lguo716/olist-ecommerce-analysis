"""Explain and validate stage-seven delivery and review analysis.

The script is read-only. It shows the sample funnel, descriptive group
differences, effect sizes, and the statistical tests used by the project.
"""

from __future__ import annotations

import math
import sys

import pandas as pd

from run_analysis import build_delivery_analysis, build_order_model, load_tables


def heading(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def build_analysis_sample(order_model: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    delivered = order_model[order_model["is_delivered"]].copy()
    analysis = delivered[
        delivered["is_late"].notna() & delivered["review_score"].notna()
    ].copy()
    analysis["delivery_status"] = analysis["is_late"].map(
        {True: "Late", False: "On time"}
    )
    return delivered, analysis


def print_stage_overview() -> None:
    heading("一、本阶段整体目标和工具")
    print("业务问题：延迟送达的订单是否伴随更低评分和更高低评分率？")
    print("Python+pandas：筛选样本并计算准时、延迟两组的描述指标。")
    print("SciPy：计算95%置信区间、Mann–Whitney U和Spearman相关。")
    print("Matplotlib/Seaborn：绘制两组平均评分和低评分率。")
    print("SQL：条件分组与聚合定义配送评分汇总；Python完成样本处理、统计检验与图表。")
    print("分析顺序：先确认样本，再看差异大小，最后看统计检验。")


def print_sample_funnel(delivered: pd.DataFrame, analysis: pd.DataFrame) -> None:
    heading("二、分析样本是怎样筛选出来的")
    delivery_known = delivered[delivered["is_late"].notna()]
    reviewed = delivered[delivered["review_score"].notna()]
    missing_both = delivered["is_late"].isna() & delivered["review_score"].isna()
    print(f"成交订单：{len(delivered):,}笔")
    print(f"有完整实际和预计送达时间：{len(delivery_known):,}笔")
    print(f"有评分：{len(reviewed):,}笔")
    print(f"同时能够判断配送状态并且有评分：{len(analysis):,}笔")
    print(f"缺配送判断：{delivered['is_late'].isna().sum():,}笔")
    print(f"缺评分：{delivered['review_score'].isna().sum():,}笔")
    print(f"两项同时缺失：{missing_both.sum():,}笔")
    print("结论：组间评分比较使用95,824笔订单，不把缺失评分填成0分。")


def print_field_definitions() -> None:
    heading("三、三个关键字段怎样计算")
    print("delivery_days = 实际送达时间 - 下单时间")
    print("delivery_delta_days = 实际送达时间 - 预计送达时间")
    print("delivery_delta_days > 0 → Late；否则 → On time")
    print("review_score <= 2 → 低评分")
    print("负的delivery_delta_days表示提前送达，不表示异常时长。")
    print(
        "承运时间早于下单或收货的警告不参与上述公式；"
        "只有分析承运商接货至收货时长时才需要排除。"
    )


def build_group_detail(analysis: pd.DataFrame) -> pd.DataFrame:
    return (
        analysis.groupby("delivery_status", as_index=False)
        .agg(
            orders=("order_id", "nunique"),
            average_review_score=("review_score", "mean"),
            median_review_score=("review_score", "median"),
            low_review_orders=("review_score", lambda values: int(values.le(2).sum())),
            low_review_rate=("review_score", lambda values: float(values.le(2).mean())),
            average_delivery_days=("delivery_days", "mean"),
            average_delta_days=("delivery_delta_days", "mean"),
        )
        .sort_values("delivery_status")
    )


def print_group_comparison(analysis: pd.DataFrame) -> pd.DataFrame:
    heading("四、准时和延迟订单的实际差异")
    detail = build_group_detail(analysis)
    display = detail.rename(
        columns={
            "delivery_status": "配送状态",
            "orders": "订单数",
            "average_review_score": "平均评分",
            "median_review_score": "评分中位数",
            "low_review_orders": "低评分订单",
            "low_review_rate": "低评分率",
            "average_delivery_days": "平均履约天数",
            "average_delta_days": "平均配送偏差天数",
        }
    ).copy()
    display["低评分率"] = display["低评分率"].map(lambda value: f"{value:.2%}")
    print(
        display.to_string(
            index=False,
            formatters={
                "平均评分": "{:.2f}".format,
                "评分中位数": "{:.0f}".format,
                "平均履约天数": "{:.2f}".format,
                "平均配送偏差天数": "{:.2f}".format,
            },
        )
    )

    review_group = pd.Series("Neutral (>2,<4)", index=analysis.index)
    review_group.loc[analysis["review_score"].le(2)] = "Low (<=2)"
    review_group.loc[analysis["review_score"].ge(4)] = "High (>=4)"
    score_distribution = pd.crosstab(
        analysis["delivery_status"],
        review_group,
        normalize="index",
    ).reindex(
        index=["Late", "On time"],
        columns=["Low (<=2)", "Neutral (>2,<4)", "High (>=4)"],
        fill_value=0,
    )
    fractional_scores = int(analysis["review_score"].mod(1).ne(0).sum())
    print("\n评分分组分布（每行合计100%）：")
    print(score_distribution.map(lambda value: f"{value:.2%}").to_string())
    print(
        f"说明：{fractional_scores}笔订单有多条评价，聚合后的订单平均分为小数，"
        "因此这里按低分、中等和高分区间展示。"
    )
    return detail


def print_effect_sizes(detail: pd.DataFrame) -> None:
    heading("五、差异到底有多大")
    indexed = detail.set_index("delivery_status")
    late = indexed.loc["Late"]
    on_time = indexed.loc["On time"]
    percentage_point_gap = float(late["low_review_rate"] - on_time["low_review_rate"])
    risk_ratio = float(late["low_review_rate"] / on_time["low_review_rate"])
    rating_gap = float(late["average_review_score"] - on_time["average_review_score"])
    print(f"低评分率差：{percentage_point_gap:.2%}，即相差{percentage_point_gap * 100:.2f}个百分点。")
    print(f"低评分风险比：{risk_ratio:.2f}倍。")
    print(f"平均评分差（延迟减准时）：{rating_gap:.2f}分。")
    print("这些指标描述业务差异大小，不能只用p值代替。")


def p_value_text(value: float) -> str:
    return "p < 1e-300" if value < 1e-300 else f"p = {value:.3g}"


def print_statistical_tests(tests: pd.DataFrame) -> None:
    heading("六、三种统计方法分别回答什么")
    indexed = tests.set_index("analysis")
    difference = indexed.loc["Late minus on-time mean review score"]
    mann = indexed.loc["Mann-Whitney U: late vs on-time review score"]
    spearman = indexed.loc["Spearman: delivery delta days vs review score"]
    print(
        "Welch 95%置信区间：平均评分差为"
        f"{difference['estimate']:.4f}，区间"
        f"[{difference['ci_95_low']:.4f}, {difference['ci_95_high']:.4f}]。"
    )
    print(
        "Mann–Whitney U：比较两组来源于1—5分原始评价的订单级评分分布，"
        f"U={mann['statistic']:,.1f}，{p_value_text(float(mann['p_value']))}。"
    )
    print(
        "Spearman相关：配送偏差天数越大，评分总体越低，"
        f"ρ={spearman['estimate']:.4f}，{p_value_text(float(spearman['p_value']))}。"
    )
    print(
        "分组差异大而相关系数较弱并不矛盾：延迟分组只判断是否越过预计日期，"
        "Spearman则使用全部配送偏差天数的排序。"
    )
    print("p值显示差异并非随机波动的有力证据；效应大小仍由评分差和低评分率差表达。")


def validate_results(
    delivered: pd.DataFrame,
    analysis: pd.DataFrame,
    detail: pd.DataFrame,
    summary: pd.DataFrame,
    tests: pd.DataFrame,
) -> None:
    heading("七、阶段验收")
    detail_index = detail.set_index("delivery_status")
    summary_index = summary.set_index("delivery_status")
    test_index = tests.set_index("analysis")
    difference = test_index.loc["Late minus on-time mean review score"]
    mann = test_index.loc["Mann-Whitney U: late vs on-time review score"]
    spearman = test_index.loc["Spearman: delivery delta days vs review score"]
    checks = {
        "成交订单为96,478笔": len(delivered) == 96_478,
        "分析样本为95,824笔且订单唯一": (
            len(analysis) == 95_824 and analysis["order_id"].nunique() == 95_824
        ),
        "延迟订单为7,661笔": int(detail_index.loc["Late", "orders"]) == 7_661,
        "准时订单为88,163笔": int(detail_index.loc["On time", "orders"]) == 88_163,
        "延迟低评分订单为4,136笔": (
            int(detail_index.loc["Late", "low_review_orders"]) == 4_136
        ),
        "准时低评分订单为8,100笔": (
            int(detail_index.loc["On time", "low_review_orders"]) == 8_100
        ),
        "正式汇总与学习计算一致": all(
            math.isclose(
                float(summary_index.loc[group, metric]),
                float(detail_index.loc[group, metric]),
            )
            for group in ("Late", "On time")
            for metric in (
                "orders",
                "average_review_score",
                "low_review_rate",
                "average_delivery_days",
                "average_delta_days",
            )
        ),
        "平均评分差及区间稳定": (
            math.isclose(float(difference["estimate"]), -1.7277863340342652)
            and math.isclose(float(difference["ci_95_low"]), -1.7656776527827003)
            and math.isclose(float(difference["ci_95_high"]), -1.68989501528583)
        ),
        "置信区间完全低于0": float(difference["ci_95_high"]) < 0,
        "Mann–Whitney U稳定": (
            math.isclose(float(mann["statistic"]), 150_680_825.5)
            and float(mann["p_value"]) < 1e-300
        ),
        "Spearman相关稳定": (
            math.isclose(float(spearman["estimate"]), -0.17566941207881423)
            and float(spearman["p_value"]) < 1e-300
        ),
        "所有比例位于0至100%": summary["low_review_rate"].between(0, 1).all(),
    }
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'ERROR'}｜{name}")
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssertionError("物流与评分检查失败：" + "、".join(failed))
    print("结论：样本、描述差异、效应大小和统计检验全部通过验收。")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("第七阶段：物流履约与用户评分分析")
    print("本脚本只在内存中读取和计算数据，不修改原始CSV。")
    order_model, _ = build_order_model(load_tables())
    delivered, analysis = build_analysis_sample(order_model)
    summary, tests = build_delivery_analysis(order_model)

    print_stage_overview()
    print_sample_funnel(delivered, analysis)
    print_field_definitions()
    detail = print_group_comparison(analysis)
    print_effect_sizes(detail)
    print_statistical_tests(tests)
    validate_results(delivered, analysis, detail, summary, tests)


if __name__ == "__main__":
    main()
