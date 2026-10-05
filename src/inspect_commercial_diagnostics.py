"""Explain and validate stage-eight category, state, and seller diagnostics.

The script is read-only. It shows the analytical grain, revenue reconciliation,
sample thresholds, comparison periods, and the resulting attention lists.
"""

from __future__ import annotations

import math
import sys

import pandas as pd

from run_analysis import build_commercial_marts, build_order_model, load_tables


def heading(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def format_percent_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    display = frame.copy()
    for column in columns:
        display[column] = display[column].map(
            lambda value: "" if pd.isna(value) else f"{value:.2%}"
        )
    return display


def print_stage_overview() -> None:
    heading("一、本阶段整体目标和工具")
    print("业务问题：平台平均值背后，问题集中在哪些品类、州和商家？")
    print("Python+pandas：建立三个分析维度的汇总表和关注清单。")
    print("Matplotlib/Seaborn：展示品类成交额以及增长与评分变化。")
    print("SQL：商品行预聚合、条件聚合与同期比较定义经营诊断口径；Python生成诊断结果与图表。")
    print("unittest：验证成交额守恒、评分分母、样本门槛和关注清单。")
    print("分析原则：先确认粒度和样本量，再比较比例，最后形成调查优先级。")


def print_grains_and_reconciliation(
    order_model: pd.DataFrame,
    item_detail: pd.DataFrame,
    category: pd.DataFrame,
    seller: pd.DataFrame,
    state: pd.DataFrame,
) -> None:
    heading("二、三个维度为什么使用不同粒度")
    delivered_orders = order_model[order_model["is_delivered"]]
    delivered_items = item_detail[item_detail["is_delivered"]]
    platform_gmv = float(delivered_orders["item_revenue"].sum())
    print("品类：先汇总为一行=一个品类在一笔订单中的商品金额，再汇总到品类。")
    print("商家：先汇总为一行=一名商家在一笔订单中的商品金额，再汇总到商家。")
    print("州：订单模型已经一单一行，可以直接按顾客收货州汇总。")
    print(f"成交订单：{len(delivered_orders):,}笔；成交商品行：{len(delivered_items):,}行。")
    print(f"平台成交额：{platform_gmv:,.2f} BRL")
    print(f"品类成交额合计：{category['revenue'].sum():,.2f} BRL")
    print(f"商家成交额合计：{seller['revenue'].sum():,.2f} BRL")
    print(f"州成交额合计：{state['revenue'].sum():,.2f} BRL")
    print("结论：订单数在多品类或多商家场景可能重复归属，但商品金额必须保持守恒。")


def print_review_denominator(
    order_model: pd.DataFrame,
    seller: pd.DataFrame,
    state: pd.DataFrame,
) -> None:
    heading("三、低评分率为什么必须使用有评分订单")
    delivered = order_model[order_model["is_delivered"]]
    reviewed = delivered[delivered["review_score"].notna()]
    print(f"成交订单：{len(delivered):,}笔")
    print(f"有评分订单：{len(reviewed):,}笔")
    print(f"低评分订单：{reviewed['review_score'].le(2).sum():,}笔")
    print(f"平台低评分率：{reviewed['review_score'].le(2).mean():.2%}")
    print(
        f"州表评分样本对账：{int(state['reviewed_orders'].sum()):,}笔有评分订单，"
        f"{int(state['low_review_orders'].sum()):,}笔低评分订单。"
    )

    example = seller.set_index("seller_id").loc["1ca7077d890b907f89be8c954a02686a"]
    old_denominator_rate = example["low_review_orders"] / example["orders"]
    print("\n商家分母示例：")
    print(
        f"1ca7077d…共有{int(example['orders'])}笔成交订单，其中"
        f"{int(example['reviewed_orders'])}笔有评分、{int(example['low_review_orders'])}笔低评分。"
    )
    print(
        f"正确口径：{int(example['low_review_orders'])} ÷ {int(example['reviewed_orders'])} "
        f"= {example['low_review_rate']:.2%}；"
        f"若错误使用全部订单作分母则为{old_denominator_rate:.2%}。"
    )


def print_category_diagnostics(
    category: pd.DataFrame,
    diagnostics: pd.DataFrame,
) -> None:
    heading("四、品类：规模、质量和同期增长")
    top = category.head(5)[
        [
            "category",
            "revenue",
            "orders",
            "average_review_score",
            "low_review_rate",
            "late_delivery_rate",
            "freight_to_revenue_rate",
        ]
    ].copy()
    top = format_percent_columns(
        top,
        ["low_review_rate", "late_delivery_rate", "freight_to_revenue_rate"],
    )
    print("成交额最高的五个品类：")
    print(
        top.to_string(
            index=False,
            formatters={
                "revenue": "{:,.2f}".format,
                "average_review_score": "{:.2f}".format,
            },
        )
    )
    print(
        f"\n共{len(category)}个品类，其中{int(category['reliable_sample'].sum())}个"
        "达到至少300笔订单的经营象限门槛。"
    )
    print(
        f"2017年1—8月与2018年1—8月各至少100单的可比品类："
        f"{int(diagnostics['comparable_sample'].sum())}个。"
    )
    risks = diagnostics[diagnostics["growth_quality_risk"]].head(5)[
        ["category", "revenue_growth", "review_score_change", "late_rate_change"]
    ].copy()
    risks = format_percent_columns(risks, ["revenue_growth", "late_rate_change"])
    print(f"满足增长质量风险规则的品类：{int(diagnostics['growth_quality_risk'].sum())}个。")
    print("优先查看的五个品类：")
    print(
        risks.to_string(
            index=False,
            formatters={"review_score_change": "{:+.2f}".format},
        )
    )


def print_state_diagnostics(state: pd.DataFrame) -> None:
    heading("五、州：顾客收货地区的履约差异")
    reliable = state[state["reliable_sample"]]
    watchlist = reliable.sort_values("late_delivery_rate", ascending=False).head(5)[
        [
            "customer_state",
            "orders",
            "revenue",
            "average_review_score",
            "low_review_rate",
            "late_delivery_rate",
            "average_delivery_days",
            "freight_to_revenue_rate",
        ]
    ].copy()
    watchlist = format_percent_columns(
        watchlist,
        ["low_review_rate", "late_delivery_rate", "freight_to_revenue_rate"],
    )
    print(f"共{len(state)}个顾客州，其中{len(reliable)}个达到至少500笔成交订单。")
    print("可靠样本中延迟率最高的五个州：")
    print(
        watchlist.to_string(
            index=False,
            formatters={
                "revenue": "{:,.2f}".format,
                "average_review_score": "{:.2f}".format,
                "average_delivery_days": "{:.2f}".format,
            },
        )
    )
    print("这里的州是顾客收货州，不是商家注册地址。")


def print_seller_diagnostics(seller: pd.DataFrame) -> None:
    heading("六、商家：建立有样本门槛的关注清单")
    reliable = seller[seller["reliable_sample"]]
    watchlist = reliable.sort_values(
        ["low_review_rate", "late_delivery_rate", "orders"],
        ascending=[False, False, False],
    ).head(5)[
        [
            "seller_id",
            "orders",
            "reviewed_orders",
            "low_review_orders",
            "low_review_rate",
            "late_delivery_rate",
            "average_review_score",
            "revenue",
        ]
    ].copy()
    watchlist["seller_id"] = watchlist["seller_id"].str[:8] + "…"
    watchlist = format_percent_columns(watchlist, ["low_review_rate", "late_delivery_rate"])
    print(f"成交商家共{len(seller):,}名，其中{len(reliable):,}名达到至少30笔成交订单。")
    print("按低评分率、延迟率和订单数依次排序的前五名：")
    print(
        watchlist.to_string(
            index=False,
            formatters={
                "average_review_score": "{:.2f}".format,
                "revenue": "{:,.2f}".format,
            },
        )
    )
    print("多商家订单共享订单级评价，因此清单是调查入口，不是单独归责结论。")


def rates_match_denominators(frame: pd.DataFrame) -> bool:
    expected = frame["low_review_orders"] / frame["reviewed_orders"].where(
        frame["reviewed_orders"].ne(0)
    )
    return bool(
        all(
            (pd.isna(actual) and pd.isna(target))
            or math.isclose(float(actual), float(target))
            for actual, target in zip(frame["low_review_rate"], expected)
        )
    )


def validate_results(
    order_model: pd.DataFrame,
    category: pd.DataFrame,
    diagnostics: pd.DataFrame,
    seller: pd.DataFrame,
    state: pd.DataFrame,
) -> None:
    heading("七、阶段验收")
    delivered_gmv = float(
        order_model.loc[order_model["is_delivered"], "item_revenue"].sum()
    )
    seller_watchlist = seller[seller["reliable_sample"]].sort_values(
        ["low_review_rate", "late_delivery_rate", "orders"],
        ascending=[False, False, False],
    ).head(5)
    state_watchlist = state[state["reliable_sample"]].sort_values(
        "late_delivery_rate", ascending=False
    ).head(5)
    risk_categories = diagnostics[diagnostics["growth_quality_risk"]].head(5)
    checks = {
        "平台成交额为13,221,498.11 BRL": math.isclose(
            delivered_gmv, 13_221_498.11, abs_tol=0.01
        ),
        "品类成交额与平台守恒": math.isclose(
            float(category["revenue"].sum()), delivered_gmv, rel_tol=1e-12
        ),
        "商家成交额与平台守恒": math.isclose(
            float(seller["revenue"].sum()), delivered_gmv, rel_tol=1e-12
        ),
        "州成交额与平台守恒": math.isclose(
            float(state["revenue"].sum()), delivered_gmv, rel_tol=1e-12
        ),
        "74个品类、32个可靠样本": (
            len(category) == 74 and int(category["reliable_sample"].sum()) == 32
        ),
        "28个同期可比品类、24个风险品类": (
            int(diagnostics["comparable_sample"].sum()) == 28
            and int(diagnostics["growth_quality_risk"].sum()) == 24
        ),
        "2,970名商家、627名可靠样本": (
            len(seller) == 2_970 and int(seller["reliable_sample"].sum()) == 627
        ),
        "27个州、17个可靠样本": (
            len(state) == 27 and int(state["reliable_sample"].sum()) == 17
        ),
        "三个维度低评分分母正确": all(
            rates_match_denominators(frame) for frame in (category, seller, state)
        ),
        "商家关注清单稳定": seller_watchlist["seller_id"].tolist()
        == [
            "1ca7077d890b907f89be8c954a02686a",
            "2eb70248d66e0e3ef83659f71b244378",
            "972d0f9cf61b499a4812cf0bfa3ad3c4",
            "a49928bcdf77c55c6d6e05e09a9b4ca5",
            "54965bbe3e4f07ae045b90b0b8541f52",
        ],
        "州关注清单稳定": state_watchlist["customer_state"].tolist()
        == ["MA", "CE", "BA", "RJ", "PA"],
        "增长质量关注品类稳定": risk_categories["category"].tolist()
        == ["baby", "stationery", "electronics", "watches_gifts", "health_beauty"],
    }
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'ERROR'}｜{name}")
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssertionError("经营诊断检查失败：" + "、".join(failed))
    print("结论：粒度、金额、评分分母、样本门槛和关注清单全部通过验收。")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("第八阶段：州、品类与商家经营诊断")
    print("本脚本只在内存中读取和计算数据，不修改原始CSV。")
    tables = load_tables()
    order_model, _ = build_order_model(tables)
    item_detail, category, diagnostics, seller, state = build_commercial_marts(
        tables, order_model
    )

    print_stage_overview()
    print_grains_and_reconciliation(order_model, item_detail, category, seller, state)
    print_review_denominator(order_model, seller, state)
    print_category_diagnostics(category, diagnostics)
    print_state_diagnostics(state)
    print_seller_diagnostics(seller)
    validate_results(order_model, category, diagnostics, seller, state)


if __name__ == "__main__":
    main()
