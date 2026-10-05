"""Explain and validate the stage-three one-row-per-order model.

The script is read-only. It shows how the item, payment, and review tables are
aggregated before they are joined to the order table, then verifies that row
counts and monetary totals are conserved.
"""

from __future__ import annotations

import math
import sys

import pandas as pd

from run_analysis import build_order_model, load_tables


SAMPLE_ORDER_ID = "3df55fc07ff463109ce0422439693aee"


def heading(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def print_source_grains(tables: dict[str, pd.DataFrame]) -> None:
    heading("一、连接前的表粒度")
    print(f"orders：{len(tables['orders']):,} 行；一行一笔订单")
    for table_name, label in (
        ("items", "商品行"),
        ("payments", "支付记录"),
        ("reviews", "评价记录"),
    ):
        counts = tables[table_name].groupby("order_id").size()
        print(
            f"{table_name}：{len(tables[table_name]):,} 行；"
            f"{counts.gt(1).sum():,} 笔订单有多个{label}；"
            f"单笔最多 {counts.max():,} 行"
        )


def print_sample_order(tables: dict[str, pd.DataFrame], model: pd.DataFrame) -> None:
    heading("二、真实订单从多行到一行")
    items = tables["items"].loc[
        tables["items"]["order_id"].eq(SAMPLE_ORDER_ID),
        ["order_id", "order_item_id", "product_id", "seller_id", "price", "freight_value"],
    ]
    payments = tables["payments"].loc[
        tables["payments"]["order_id"].eq(SAMPLE_ORDER_ID),
        ["order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"],
    ]
    reviews = tables["reviews"].loc[
        tables["reviews"]["order_id"].eq(SAMPLE_ORDER_ID),
        ["order_id", "review_id", "review_score", "review_comment_message"],
    ]

    print("\n原始商品行：")
    print(items.to_string(index=False))
    print("\n原始支付行：")
    print(payments.to_string(index=False))
    print("\n原始评价行：")
    print(reviews.to_string(index=False))

    final_columns = [
        "order_id",
        "order_status",
        "item_revenue",
        "freight_value",
        "item_count",
        "unique_products",
        "seller_count",
        "payment_value",
        "payment_records",
        "max_installments",
        "primary_payment_type",
        "review_score",
        "review_records",
        "has_review_comment",
        "delivery_days",
        "delivery_delta_days",
        "is_late",
    ]
    print("\n连接后的订单模型：")
    print(
        model.loc[model["order_id"].eq(SAMPLE_ORDER_ID), final_columns].to_string(
            index=False
        )
    )


def print_conservation_checks(
    tables: dict[str, pd.DataFrame], model: pd.DataFrame
) -> None:
    heading("三、粒度与守恒检查")
    checks = [
        (
            "订单行数保持不变",
            len(tables["orders"]),
            len(model),
            len(tables["orders"]) == len(model),
        ),
        (
            "order_id保持唯一",
            len(tables["orders"]),
            model["order_id"].nunique(),
            len(model) == model["order_id"].nunique(),
        ),
        (
            "商品金额守恒",
            tables["items"]["price"].sum(),
            model["item_revenue"].sum(),
            math.isclose(
                tables["items"]["price"].sum(),
                model["item_revenue"].sum(),
                rel_tol=1e-12,
            ),
        ),
        (
            "运费守恒",
            tables["items"]["freight_value"].sum(),
            model["freight_value"].sum(),
            math.isclose(
                tables["items"]["freight_value"].sum(),
                model["freight_value"].sum(),
                rel_tol=1e-12,
            ),
        ),
        (
            "商品行数守恒",
            len(tables["items"]),
            model["item_count"].sum(),
            int(model["item_count"].sum()) == len(tables["items"]),
        ),
        (
            "支付记录数守恒",
            len(tables["payments"]),
            model["payment_records"].sum(),
            int(model["payment_records"].sum()) == len(tables["payments"]),
        ),
        (
            "评价记录数守恒",
            len(tables["reviews"]),
            model["review_records"].fillna(0).sum(),
            int(model["review_records"].fillna(0).sum()) == len(tables["reviews"]),
        ),
    ]
    for name, raw_value, model_value, passed in checks:
        status = "PASS" if passed else "ERROR"
        print(f"{status}｜{name}｜聚合前={raw_value:,.2f}｜模型={model_value:,.2f}")
    failed = [name for name, _, _, passed in checks if not passed]
    if failed:
        raise AssertionError("订单模型检查失败：" + "、".join(failed))
    print("结论：最终模型一单一行，金额和子表记录数均未因连接而改变。")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("第三阶段：建立一单一行的订单分析模型")
    print("本脚本只读取原始CSV并在内存中建模，不修改原始文件。")

    tables = load_tables()
    model, _ = build_order_model(tables)
    print_source_grains(tables)
    print_sample_order(tables, model)
    print_conservation_checks(tables, model)


if __name__ == "__main__":
    main()
