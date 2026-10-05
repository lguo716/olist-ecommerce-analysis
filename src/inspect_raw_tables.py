"""Inspect the Olist source tables for the first learning stage.

This script is intentionally read-only. It prints table grain, key uniqueness,
and one real example of why one-to-many tables must be aggregated before they
are joined.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "raw"

TABLE_SPECS = (
    ("olist_orders_dataset.csv", ("order_id",), "一行一笔订单", "业务键"),
    (
        "olist_customers_dataset.csv",
        ("customer_id",),
        "一行一个订单级顾客编号",
        "业务键",
    ),
    (
        "olist_order_items_dataset.csv",
        ("order_id", "order_item_id"),
        "一行一个订单商品行",
        "业务键",
    ),
    (
        "olist_order_payments_dataset.csv",
        ("order_id", "payment_sequential"),
        "一行一次支付记录",
        "业务键",
    ),
    (
        "olist_order_reviews_dataset.csv",
        ("review_id", "order_id"),
        "一行一条订单评价",
        "业务键",
    ),
    ("olist_products_dataset.csv", ("product_id",), "一行一个商品", "业务键"),
    ("olist_sellers_dataset.csv", ("seller_id",), "一行一个商家", "业务键"),
    (
        "product_category_name_translation.csv",
        ("product_category_name",),
        "一行一个葡语品类",
        "业务键",
    ),
    (
        "olist_geolocation_dataset.csv",
        ("geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng"),
        "一行一个邮编坐标记录",
        "重复检查字段（该表无唯一业务键）",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="包含九张 Olist CSV 的目录",
    )
    return parser.parse_args()


def require_files(data_dir: Path) -> None:
    missing = [name for name, _, _, _ in TABLE_SPECS if not (data_dir / name).exists()]
    if missing:
        formatted = "\n".join(f"- {name}" for name in missing)
        raise FileNotFoundError(f"缺少以下原始文件：\n{formatted}")


def print_table_inventory(data_dir: Path) -> None:
    print("\n一、九张原始表的规模、粒度和主键\n")
    for filename, key_columns, grain, key_label in TABLE_SPECS:
        path = data_dir / filename
        frame = pd.read_csv(path, usecols=list(key_columns))
        duplicate_keys = int(frame.duplicated(list(key_columns)).sum())
        print(
            f"{filename}\n"
            f"  粒度：{grain}\n"
            f"  行数：{len(frame):,}\n"
            f"  {key_label}：{', '.join(key_columns)}\n"
            f"  上述字段组合的重复行数：{duplicate_keys:,}"
        )


def print_customer_identity_check(data_dir: Path) -> None:
    customers = pd.read_csv(
        data_dir / "olist_customers_dataset.csv",
        usecols=["customer_id", "customer_unique_id"],
    )
    print("\n二、订单级顾客编号与自然人编号\n")
    print(f"customer_id 数量：{customers['customer_id'].nunique():,}")
    print(f"customer_unique_id 数量：{customers['customer_unique_id'].nunique():,}")
    print(
        "结论：customer_id 对应一次订单关系；复购、RFM 和同期群必须使用 "
        "customer_unique_id。"
    )


def print_join_multiplication_example(data_dir: Path) -> None:
    items = pd.read_csv(
        data_dir / "olist_order_items_dataset.csv",
        usecols=["order_id", "order_item_id", "price"],
    )
    payments = pd.read_csv(
        data_dir / "olist_order_payments_dataset.csv",
        usecols=["order_id", "payment_sequential", "payment_value"],
    )
    reviews = pd.read_csv(
        data_dir / "olist_order_reviews_dataset.csv",
        usecols=["order_id", "review_id", "review_score"],
    )

    row_counts = pd.concat(
        [
            items.groupby("order_id").size().rename("item_rows"),
            payments.groupby("order_id").size().rename("payment_rows"),
            reviews.groupby("order_id").size().rename("review_rows"),
        ],
        axis=1,
    ).fillna(0).astype(int)

    candidates = row_counts[
        (row_counts["item_rows"] > 1)
        & (row_counts["payment_rows"] > 1)
        & (row_counts["review_rows"] > 1)
    ]
    if candidates.empty:
        candidates = row_counts[
            (row_counts["item_rows"] > 1) & (row_counts["payment_rows"] > 1)
        ]

    order_id = candidates.sort_values(
        ["item_rows", "payment_rows", "review_rows"], ascending=False
    ).index[0]
    order_items = items[items["order_id"] == order_id]
    order_payments = payments[payments["order_id"] == order_id]
    order_reviews = reviews[reviews["order_id"] == order_id]

    naive_join = order_items.merge(order_payments, on="order_id").merge(
        order_reviews, on="order_id", how="left"
    )

    print("\n三、直接连接导致金额放大的真实案例\n")
    print(f"order_id：{order_id}")
    print(
        f"商品行 {len(order_items)} × 支付行 {len(order_payments)} × "
        f"评价行 {len(order_reviews)} = 直接连接后 {len(naive_join)} 行"
    )
    print(f"正确商品金额：{order_items['price'].sum():.2f} BRL")
    print(f"错误连接后的商品金额：{naive_join['price'].sum():.2f} BRL")
    print(f"正确支付金额：{order_payments['payment_value'].sum():.2f} BRL")
    print(f"错误连接后的支付金额：{naive_join['payment_value'].sum():.2f} BRL")
    print("结论：商品、支付和评价必须先分别聚合到一单一行，再连接 orders。")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    data_dir = args.data_dir.resolve()
    require_files(data_dir)
    print(f"原始数据目录：{data_dir}")
    print_table_inventory(data_dir)
    print_customer_identity_check(data_dir)
    print_join_multiplication_example(data_dir)


if __name__ == "__main__":
    main()
