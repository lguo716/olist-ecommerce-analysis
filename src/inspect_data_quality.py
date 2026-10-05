"""Run and explain the stage-two Olist data-quality checks.

This entry point is read-only: it validates the source CSV files, summarizes
duplicates and missing values, and prints the relationship, value, timestamp,
and model checks already defined in ``run_analysis.py``.
"""

from __future__ import annotations

import sys

import pandas as pd

from run_analysis import (
    build_order_model,
    build_quality_checks,
    build_quality_report,
    load_tables,
    validate_files,
)


CHECK_GROUPS = {
    "四、表关系完整性": [
        "orders_without_customer",
        "items_without_order",
        "items_without_product",
        "items_without_seller",
        "payments_without_order",
        "reviews_without_order",
    ],
    "五、数值范围": [
        "negative_item_price",
        "negative_freight_value",
        "negative_payment_value",
        "invalid_review_score",
    ],
    "六、时间顺序": [
        "approval_before_purchase",
        "carrier_before_purchase",
        "delivery_before_carrier",
        "delivery_before_purchase",
        "boundary_months",
    ],
    "七、订单模型前置条件": [
        "duplicate_order_model_key",
        "missing_customer_unique_id",
    ],
}

MISSING_ACTIONS = {
    ("reviews", "review_comment_title"): "可接受：顾客未填写评价标题，不删除评价。",
    ("reviews", "review_comment_message"): "可接受：顾客未填写评价正文，不删除评价。",
    ("products", "product_category_name"): "保留交易，后续将品类标记为 unknown。",
    ("products", "product_name_lenght"): "与缺失品类对应，不影响订单金额。",
    ("products", "product_description_lenght"): "与缺失品类对应，不影响订单金额。",
    ("products", "product_photos_qty"): "与缺失品类对应，不影响订单金额。",
    ("products", "product_weight_g"): "保留交易，仅从重量相关分析中排除。",
    ("products", "product_length_cm"): "保留交易，仅从体积相关分析中排除。",
    ("products", "product_height_cm"): "保留交易，仅从体积相关分析中排除。",
    ("products", "product_width_cm"): "保留交易，仅从体积相关分析中排除。",
    ("orders", "order_approved_at"): "结合订单状态判断，不统一填补。",
    ("orders", "order_delivered_carrier_date"): "结合订单状态判断，不统一填补。",
    ("orders", "order_delivered_customer_date"): "结合订单状态判断，不统一填补。",
}


def heading(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def print_file_checks(file_report: pd.DataFrame) -> None:
    heading("一、文件与字段完整性")
    display = file_report[["table", "rows", "columns", "size_mb", "sha256", "schema_check"]].copy()
    display["sha256"] = display["sha256"].str.slice(0, 12) + "..."
    display = display.rename(
        columns={
            "table": "表",
            "rows": "行数",
            "columns": "列数",
            "size_mb": "大小MB",
            "sha256": "SHA256前缀",
            "schema_check": "字段检查",
        }
    )
    print(display.to_string(index=False))
    print("结论：九张CSV均存在，必需字段检查全部通过。")


def print_duplicate_checks(quality_report: pd.DataFrame) -> None:
    heading("二、完整重复行与业务键重复")
    display = quality_report[
        ["table", "duplicate_rows", "duplicate_business_keys"]
    ].copy()
    display["duplicate_business_keys"] = display["duplicate_business_keys"].apply(
        lambda value: "仅文件验证" if pd.isna(value) else f"{int(value):,}"
    )
    display["duplicate_rows"] = display["duplicate_rows"].apply(
        lambda value: "仅文件验证" if pd.isna(value) else f"{int(value):,}"
    )
    display = display.rename(
        columns={
            "table": "表",
            "duplicate_rows": "完整重复行",
            "duplicate_business_keys": "重复业务键",
        }
    )
    print(display.to_string(index=False))
    print("说明：地理表约100万行，本项目只做文件验证，州级分析不加载该表。")


def print_missing_values(tables: dict[str, pd.DataFrame]) -> None:
    heading("三、缺失值及处理原则")
    found_missing = False
    for table_name, frame in tables.items():
        missing = frame.isna().sum()
        missing = missing[missing.gt(0)].sort_values(ascending=False)
        for column, count in missing.items():
            found_missing = True
            action = MISSING_ACTIONS.get(
                (table_name, column), "需要结合字段用途和业务状态人工判断。"
            )
            print(
                f"{table_name}.{column}: {int(count):,} 行 "
                f"({count / len(frame):.2%})｜{action}"
            )
    if not found_missing:
        print("已加载表中没有缺失值。")
    print("结论：缺失不等于错误；不能统一删除，也不能统一填0。")


def print_check_group(title: str, checks: pd.DataFrame, names: list[str]) -> None:
    heading(title)
    group = checks.set_index("check_name").loc[names].reset_index()
    display = group[
        ["check_name", "status", "failed_rows", "description", "recommended_action"]
    ].rename(
        columns={
            "check_name": "检查项",
            "status": "状态",
            "failed_rows": "异常行数",
            "description": "含义",
            "recommended_action": "处理原则",
        }
    )
    print(display.to_string(index=False))


def print_summary(checks: pd.DataFrame) -> None:
    heading("八、严重级别与阶段结论")
    status_counts = checks.groupby("status", dropna=False).size().to_dict()
    for status in ("PASS", "WARN", "INFO", "ERROR"):
        print(f"{status}: {status_counts.get(status, 0)} 项")

    blocking = checks.loc[
        checks["severity"].eq("ERROR") & checks["failed_rows"].gt(0)
    ]
    if blocking.empty:
        print("阶段结论：没有阻断级数据质量错误，可以进入订单模型构建。")
    else:
        failed = ", ".join(blocking["check_name"])
        raise AssertionError(f"存在阻断级数据质量错误：{failed}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("第二阶段：Olist原始数据质量检查")
    print("本脚本只读取原始CSV，不修改、删除或填补任何原始记录。")

    file_report = validate_files()
    tables = load_tables()
    order_model, _ = build_order_model(tables)
    quality_report = build_quality_report(tables, file_report)
    checks = build_quality_checks(tables, order_model)

    print_file_checks(file_report)
    print_duplicate_checks(quality_report)
    print_missing_values(tables)
    for title, names in CHECK_GROUPS.items():
        print_check_group(title, checks, names)
    print_summary(checks)


if __name__ == "__main__":
    main()
