"""Explain and validate stage-six monthly cohort retention analysis.

The script is read-only. It reconstructs customer-month activity, demonstrates
cohort assignment with real records, and checks the tidy and matrix outputs.
"""

from __future__ import annotations

import math
import sys

import pandas as pd

from run_analysis import build_cohorts, build_order_model, load_tables


def heading(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def build_customer_month_activity(
    order_model: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    delivered = order_model[order_model["is_delivered"]].copy()
    delivered["order_month"] = delivered["order_purchase_timestamp"].dt.to_period("M")
    first_month = (
        delivered.groupby("customer_unique_id")["order_month"]
        .min()
        .rename("cohort_month")
    )
    activity = delivered[["customer_unique_id", "order_month"]].drop_duplicates().merge(
        first_month,
        on="customer_unique_id",
        how="left",
        validate="many_to_one",
    )
    activity["cohort_index"] = (
        (activity["order_month"].dt.year - activity["cohort_month"].dt.year) * 12
        + activity["order_month"].dt.month
        - activity["cohort_month"].dt.month
    )
    return delivered, activity


def print_stage_overview() -> None:
    heading("一、本阶段整体目标和工具")
    print("业务问题：同一首购月份的顾客，在之后各个月份有多少人再次购买？")
    print("Python+pandas：确定首购月、月份差、活跃顾客数和留存率。")
    print("Matplotlib/Seaborn：将留存矩阵绘制成热力图。")
    print("SQL：MIN、TIMESTAMPDIFF、分组和条件连接定义同期群口径；Python构建留存矩阵并验证观察窗口。")
    print("unittest：验证人数、月份边界、0%与不可观察空白。")
    print("口径：这里计算的是每个自然月的复购活跃率，不是累计留存率。")


def print_customer_example(delivered: pd.DataFrame, activity: pd.DataFrame) -> None:
    heading("二、用真实顾客理解cohort_index")
    distinct_months = activity.groupby("customer_unique_id")["order_month"].nunique()
    example_id = distinct_months[distinct_months.ge(3)].sort_index().index[0]
    orders = delivered.loc[
        delivered["customer_unique_id"].eq(example_id),
        ["customer_unique_id", "order_id", "order_purchase_timestamp", "order_month"],
    ].sort_values("order_purchase_timestamp")
    example_activity = activity[activity["customer_unique_id"].eq(example_id)].sort_values(
        "order_month"
    )
    print("真实成交订单：")
    print(orders.to_string(index=False))
    print("\n转换为顾客月份活动：")
    print(example_activity.to_string(index=False))
    print("解释：该顾客2017-03首购，所以2017-03、2017-11、2018-05分别是第0、8、14月。")


def print_month_deduplication(delivered: pd.DataFrame) -> None:
    heading("三、为什么要去除同一顾客同月重复")
    monthly_orders = delivered.groupby(["customer_unique_id", "order_month"]).size()
    customer_id, order_month = monthly_orders[monthly_orders.gt(1)].sort_index().index[0]
    example = delivered.loc[
        delivered["customer_unique_id"].eq(customer_id)
        & delivered["order_month"].eq(order_month),
        ["customer_unique_id", "order_id", "order_purchase_timestamp", "order_month"],
    ].sort_values("order_purchase_timestamp")
    print(example.to_string(index=False))
    print(
        f"这名顾客在{order_month}有{len(example)}笔成交订单，"
        "但同期群分析统计活跃顾客，因此这个月只计1人。"
    )


def weighted_retention(tidy: pd.DataFrame, cohort_index: int) -> tuple[int, int, int, float]:
    observed = tidy[tidy["cohort_index"].eq(cohort_index)]
    active = int(observed["active_customers"].sum())
    cohort_size = int(observed["cohort_size"].sum())
    return len(observed), active, cohort_size, active / cohort_size


def print_cohort_results(tidy: pd.DataFrame, matrix: pd.DataFrame) -> None:
    heading("四、同期群结果和加权留存")
    month_zero = tidy[tidy["cohort_index"].eq(0)]
    print(
        f"同期群数量：{len(month_zero)}个，范围{month_zero['cohort_month'].min()}"
        f"至{month_zero['cohort_month'].max()}。"
    )
    print(f"同期群覆盖顾客：{int(month_zero['cohort_size'].sum()):,}人。")
    for index in (1, 2):
        cohorts, active, base, rate = weighted_retention(tidy, index)
        print(
            f"第{index}月：{cohorts}个可观察同期群，"
            f"{active:,}名活跃顾客 ÷ {base:,}名同期群顾客 = {rate:.4%}。"
        )

    print("\n留存矩阵节选（2017年同期群，第0—6月）：")
    excerpt = matrix.loc["2017-01":"2017-06", list(range(7))].copy()
    print(excerpt.map(lambda value: "" if pd.isna(value) else f"{value:.2%}").to_string())
    print("矩阵要横向阅读：每一行是一批首购月份相同的顾客。")


def print_zero_and_unobserved(matrix: pd.DataFrame) -> None:
    heading("五、0%和空白不是一回事")
    october_m1 = matrix.loc["2016-10", 1]
    august_m1 = matrix.loc["2018-08", 1]
    print(f"2016-10同期群第1月：{october_m1:.2%}。该月已经可以观察，但无人复购。")
    print(
        "2018-08同期群第1月："
        f"{'空白' if pd.isna(august_m1) else f'{august_m1:.2%}'}。"
        "数据在2018-08结束，第1个月尚未到来。"
    )
    print("因此，0%是分析结果；尚不可观察的空白不是0%，也不能进入分母。")


def validate_results(
    delivered: pd.DataFrame,
    activity: pd.DataFrame,
    tidy: pd.DataFrame,
    matrix: pd.DataFrame,
) -> None:
    heading("六、阶段验收")
    month_zero = tidy[tidy["cohort_index"].eq(0)]
    month_one = tidy[tidy["cohort_index"].eq(1)]
    month_two = tidy[tidy["cohort_index"].eq(2)]
    matrix_matches = all(
        math.isclose(
            float(row.retention_rate),
            float(matrix.loc[row.cohort_month, row.cohort_index]),
        )
        for row in tidy.itertuples(index=False)
    )
    checks = {
        "只使用成交订单": len(delivered) == 96_478,
        "顾客月份活动没有重复": not activity.duplicated(
            ["customer_unique_id", "order_month"]
        ).any(),
        "cohort_index没有负数": activity["cohort_index"].ge(0).all(),
        "同期群覆盖93,358名顾客": int(month_zero["cohort_size"].sum()) == 93_358,
        "共有23个同期群": len(month_zero) == 23,
        "第0月全部为100%": month_zero["retention_rate"].eq(1).all(),
        "所有留存率位于0至100%": tidy["retention_rate"].between(0, 1).all(),
        "第1月基准为421/87,214": (
            len(month_one) == 22
            and int(month_one["active_customers"].sum()) == 421
            and int(month_one["cohort_size"].sum()) == 87_214
        ),
        "第2月基准为273/81,265": (
            len(month_two) == 21
            and int(month_two["active_customers"].sum()) == 273
            and int(month_two["cohort_size"].sum()) == 81_265
        ),
        "已观察零活动记录为0%": matrix.loc["2016-10", 1] == 0,
        "未来不可观察月份为空": pd.isna(matrix.loc["2018-08", 1]),
        "长表与矩阵逐项一致": matrix_matches,
    }
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'ERROR'}｜{name}")
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssertionError("同期群留存检查失败：" + "、".join(failed))
    print("结论：顾客归群、月份去重、观察窗口、留存率和矩阵全部通过验收。")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("第六阶段：同期群留存分析")
    print("本脚本只在内存中读取和计算数据，不修改原始CSV。")
    order_model, _ = build_order_model(load_tables())
    delivered, activity = build_customer_month_activity(order_model)
    tidy, matrix = build_cohorts(order_model)

    print_stage_overview()
    print_customer_example(delivered, activity)
    print_month_deduplication(delivered)
    print_cohort_results(tidy, matrix)
    print_zero_and_unobserved(matrix)
    validate_results(delivered, activity, tidy, matrix)


if __name__ == "__main__":
    main()
