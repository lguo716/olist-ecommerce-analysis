"""Build the Olist analytical model and generate portfolio-ready outputs.

The pipeline intentionally aggregates one-to-many tables before joining them to
orders. This prevents the most common error in this dataset: duplicated revenue
caused by joining items, payments and reviews at their raw grain.
"""

from __future__ import annotations

import csv
import hashlib
import math
import os
from pathlib import Path

_BOOTSTRAP_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_MPL_CONFIG_DIR = _BOOTSTRAP_PROJECT_ROOT / ".matplotlib"
_MPL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPL_CONFIG_DIR))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPORT_DIR = PROJECT_ROOT / "reports"
TABLE_DIR = REPORT_DIR / "tables"
FIGURE_DIR = REPORT_DIR / "figures"

FILES = {
    "customers": "olist_customers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "translation": "product_category_name_translation.csv",
}

EXPECTED_COLUMNS = {
    "customers": {
        "customer_id",
        "customer_unique_id",
        "customer_city",
        "customer_state",
    },
    "items": {"order_id", "order_item_id", "product_id", "seller_id", "price", "freight_value"},
    "payments": {"order_id", "payment_type", "payment_installments", "payment_value"},
    "reviews": {"order_id", "review_score"},
    "orders": {
        "order_id",
        "customer_id",
        "order_status",
        "order_purchase_timestamp",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    },
    "products": {"product_id", "product_category_name"},
    "sellers": {"seller_id", "seller_city", "seller_state"},
    "translation": {"product_category_name", "product_category_name_english"},
}

DATE_COLUMNS = {
    "orders": [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ],
    "items": ["shipping_limit_date"],
    "reviews": ["review_creation_date", "review_answer_timestamp"],
}


def ensure_directories() -> None:
    for directory in (PROCESSED_DIR, TABLE_DIR, FIGURE_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def count_csv_rows(path: Path) -> int:
    # csv.reader is required because review comments can contain embedded
    # newlines; counting physical lines would overstate the record count.
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return max(sum(1 for _ in csv.reader(handle)) - 1, 0)


def read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_files() -> pd.DataFrame:
    missing = [filename for filename in FILES.values() if not (RAW_DIR / filename).exists()]
    if missing:
        raise FileNotFoundError(
            "Missing source files: " + ", ".join(missing) + ". Run src/download_data.ps1 first."
        )

    records: list[dict[str, object]] = []
    for table, filename in FILES.items():
        path = RAW_DIR / filename
        columns = read_header(path)
        expected = EXPECTED_COLUMNS.get(table, set())
        absent = sorted(expected.difference(columns))
        if absent:
            raise ValueError(f"{filename} is missing required columns: {absent}")
        records.append(
            {
                "table": table,
                "file": filename,
                "rows": count_csv_rows(path),
                "columns": len(columns),
                "size_mb": round(path.stat().st_size / 1024**2, 2),
                "sha256": sha256_file(path),
                "schema_check": "PASS",
            }
        )
    return pd.DataFrame(records)


def load_tables() -> dict[str, pd.DataFrame]:
    # Geolocation contains about one million rows and is not required for the
    # state-level analysis. It is file-validated but deliberately not loaded.
    tables: dict[str, pd.DataFrame] = {}
    for table, filename in FILES.items():
        if table == "geolocation":
            continue
        tables[table] = pd.read_csv(
            RAW_DIR / filename,
            parse_dates=DATE_COLUMNS.get(table),
            low_memory=False,
        )
    return tables


def build_quality_report(tables: dict[str, pd.DataFrame], file_report: pd.DataFrame) -> pd.DataFrame:
    key_map = {
        "customers": ["customer_id"],
        "orders": ["order_id"],
        "items": ["order_id", "order_item_id"],
        "payments": ["order_id", "payment_sequential"],
        "reviews": ["review_id", "order_id"],
        "products": ["product_id"],
        "sellers": ["seller_id"],
        "translation": ["product_category_name"],
    }
    loaded_records: list[dict[str, object]] = []
    for table, frame in tables.items():
        keys = key_map.get(table)
        key_duplicates = int(frame.duplicated(keys).sum()) if keys else np.nan
        loaded_records.append(
            {
                "table": table,
                "duplicate_rows": int(frame.duplicated().sum()),
                "duplicate_business_keys": key_duplicates,
                "missing_cells": int(frame.isna().sum().sum()),
                "missing_cell_rate": float(frame.isna().sum().sum() / frame.size),
            }
        )
    loaded_report = pd.DataFrame(loaded_records)
    return file_report.merge(loaded_report, on="table", how="left")


def build_quality_checks(tables: dict[str, pd.DataFrame], order_model: pd.DataFrame) -> pd.DataFrame:
    """Return auditable relationship, value and timestamp quality checks."""

    customers = tables["customers"]
    orders = tables["orders"]
    items = tables["items"]
    payments = tables["payments"]
    reviews = tables["reviews"]
    products = tables["products"]
    sellers = tables["sellers"]
    checks: list[dict[str, object]] = []

    def add_check(
        check_name: str,
        failed_rows: int,
        severity: str,
        description: str,
        recommended_action: str,
    ) -> None:
        checks.append(
            {
                "check_name": check_name,
                "status": "PASS" if failed_rows == 0 else severity,
                "failed_rows": int(failed_rows),
                "severity": severity,
                "description": description,
                "recommended_action": recommended_action,
            }
        )

    add_check(
        "orders_without_customer",
        orders.loc[~orders["customer_id"].isin(customers["customer_id"])].shape[0],
        "ERROR",
        "订单无法关联顾客主表。",
        "检查 customer_id 来源，不直接删除订单。",
    )
    add_check(
        "items_without_order",
        items.loc[~items["order_id"].isin(orders["order_id"])].shape[0],
        "ERROR",
        "商品明细无法关联订单。",
        "核对订单抽取范围与明细抽取范围。",
    )
    add_check(
        "items_without_product",
        items.loc[~items["product_id"].isin(products["product_id"])].shape[0],
        "WARN",
        "商品明细无法关联商品主表。",
        "保留交易金额，将商品类别标记为 unknown。",
    )
    add_check(
        "items_without_seller",
        items.loc[~items["seller_id"].isin(sellers["seller_id"])].shape[0],
        "WARN",
        "商品明细无法关联商家主表。",
        "保留订单，商家维度分析单独标记未知。",
    )
    add_check(
        "payments_without_order",
        payments.loc[~payments["order_id"].isin(orders["order_id"])].shape[0],
        "ERROR",
        "支付记录无法关联订单。",
        "核对支付与订单数据的抽取范围。",
    )
    add_check(
        "reviews_without_order",
        reviews.loc[~reviews["order_id"].isin(orders["order_id"])].shape[0],
        "WARN",
        "评价记录无法关联订单。",
        "不将孤立评价纳入订单满意度分析。",
    )
    add_check(
        "negative_item_price",
        items["price"].lt(0).sum(),
        "ERROR",
        "商品价格为负数。",
        "确认是否为退款；在没有退款字段时不得直接冲减成交额。",
    )
    add_check(
        "negative_freight_value",
        items["freight_value"].lt(0).sum(),
        "ERROR",
        "运费为负数。",
        "检查源数据及运费补贴口径。",
    )
    add_check(
        "negative_payment_value",
        payments["payment_value"].lt(0).sum(),
        "ERROR",
        "支付金额为负数。",
        "确认退款与支付记录口径。",
    )
    add_check(
        "invalid_review_score",
        (~reviews["review_score"].between(1, 5)).sum(),
        "ERROR",
        "评分不在 1 至 5 分范围内。",
        "隔离异常记录并回查源数据。",
    )
    add_check(
        "approval_before_purchase",
        (
            orders["order_approved_at"].notna()
            & orders["order_purchase_timestamp"].notna()
            & orders["order_approved_at"].lt(orders["order_purchase_timestamp"])
        ).sum(),
        "WARN",
        "订单审批时间早于下单时间。",
        "作为时间异常保留在质量报告，不用于时长分析。",
    )
    add_check(
        "carrier_before_purchase",
        (
            orders["order_delivered_carrier_date"].notna()
            & orders["order_purchase_timestamp"].notna()
            & orders["order_delivered_carrier_date"].lt(orders["order_purchase_timestamp"])
        ).sum(),
        "WARN",
        "交给承运商的时间早于下单时间。",
        "作为时间异常保留在质量报告，不用于时长分析。",
    )
    add_check(
        "delivery_before_carrier",
        (
            orders["order_delivered_customer_date"].notna()
            & orders["order_delivered_carrier_date"].notna()
            & orders["order_delivered_customer_date"].lt(orders["order_delivered_carrier_date"])
        ).sum(),
        "WARN",
        "顾客收货时间早于交给承运商的时间。",
        "作为时间异常保留在质量报告，不用于履约分析。",
    )
    add_check(
        "delivery_before_purchase",
        order_model["delivery_days"].lt(0).sum(),
        "ERROR",
        "送达时间早于下单时间。",
        "从配送时长统计中排除并回查源数据。",
    )
    add_check(
        "duplicate_order_model_key",
        order_model["order_id"].duplicated().sum(),
        "ERROR",
        "订单分析宽表不是一单一行。",
        "检查一对多表是否先按 order_id 聚合。",
    )
    add_check(
        "missing_customer_unique_id",
        order_model["customer_unique_id"].isna().sum(),
        "ERROR",
        "订单缺少跨订单稳定的顾客标识。",
        "不将缺失记录纳入复购、RFM 和同期群分析。",
    )

    first_month = order_model["purchase_month"].min()
    last_month = order_model["purchase_month"].max()
    checks.append(
        {
            "check_name": "boundary_months",
            "status": "INFO",
            "failed_rows": 0,
            "severity": "INFO",
            "description": f"样本首月 {first_month:%Y-%m}、末月 {last_month:%Y-%m} 可能不是完整自然月。",
            "recommended_action": "核心趋势比较限定为 2017-01 至 2018-08。",
        }
    )
    return pd.DataFrame(checks)


def build_order_model(tables: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    customers = tables["customers"]
    orders = tables["orders"].copy()
    items = tables["items"]
    payments = tables["payments"]
    reviews = tables["reviews"]

    item_agg = (
        items.groupby("order_id", as_index=False)
        .agg(
            item_revenue=("price", "sum"),
            freight_value=("freight_value", "sum"),
            item_count=("order_item_id", "count"),
            unique_products=("product_id", "nunique"),
            seller_count=("seller_id", "nunique"),
        )
    )

    payment_agg = (
        payments.groupby("order_id", as_index=False)
        .agg(
            payment_value=("payment_value", "sum"),
            payment_records=("payment_sequential", "count"),
            max_installments=("payment_installments", "max"),
        )
    )
    primary_payment = (
        payments.groupby(["order_id", "payment_type"], as_index=False)["payment_value"]
        .sum()
        .sort_values(["order_id", "payment_value", "payment_type"], ascending=[True, False, True])
        .drop_duplicates("order_id")
        .rename(columns={"payment_type": "primary_payment_type"})[["order_id", "primary_payment_type"]]
    )
    payment_agg = payment_agg.merge(primary_payment, on="order_id", how="left", validate="one_to_one")

    review_agg = (
        reviews.groupby("order_id", as_index=False)
        .agg(
            review_score=("review_score", "mean"),
            review_records=("review_id", "count"),
            has_review_comment=("review_comment_message", lambda x: int(x.notna().any())),
        )
    )

    model = (
        orders.merge(customers, on="customer_id", how="left", validate="many_to_one")
        .merge(item_agg, on="order_id", how="left", validate="one_to_one")
        .merge(payment_agg, on="order_id", how="left", validate="one_to_one")
        .merge(review_agg, on="order_id", how="left", validate="one_to_one")
    )

    numeric_fill = [
        "item_revenue",
        "freight_value",
        "item_count",
        "unique_products",
        "seller_count",
        "payment_value",
        "payment_records",
    ]
    model[numeric_fill] = model[numeric_fill].fillna(0)
    model["purchase_date"] = model["order_purchase_timestamp"].dt.date
    model["purchase_month"] = model["order_purchase_timestamp"].dt.to_period("M").dt.to_timestamp()
    model["is_delivered"] = model["order_status"].eq("delivered")
    model["is_canceled"] = model["order_status"].eq("canceled")
    model["is_unavailable"] = model["order_status"].eq("unavailable")
    model["delivery_days"] = (
        model["order_delivered_customer_date"] - model["order_purchase_timestamp"]
    ).dt.total_seconds() / 86400
    model["delivery_delta_days"] = (
        model["order_delivered_customer_date"] - model["order_estimated_delivery_date"]
    ).dt.total_seconds() / 86400
    has_delivery_dates = model["order_delivered_customer_date"].notna() & model[
        "order_estimated_delivery_date"
    ].notna()
    model["is_late"] = pd.Series(pd.NA, index=model.index, dtype="boolean")
    model.loc[has_delivery_dates, "is_late"] = model.loc[has_delivery_dates, "delivery_delta_days"].gt(0)
    model["delivered_gmv"] = model["item_revenue"].where(model["is_delivered"], 0)
    model["delivered_freight"] = model["freight_value"].where(model["is_delivered"], 0)

    delivered = model[model["is_delivered"] & model["customer_unique_id"].notna()].copy()
    delivered = delivered.sort_values(["customer_unique_id", "order_purchase_timestamp", "order_id"])
    delivered["customer_order_number"] = delivered.groupby("customer_unique_id").cumcount() + 1
    delivered["is_repeat_order"] = delivered["customer_order_number"].gt(1)
    model = model.merge(
        delivered[["order_id", "customer_order_number", "is_repeat_order"]],
        on="order_id",
        how="left",
        validate="one_to_one",
    )
    model["is_repeat_order"] = model["is_repeat_order"].fillna(False).astype(bool)

    if model["order_id"].duplicated().any():
        raise AssertionError("Order model is not unique at order_id grain.")
    if not math.isclose(items["price"].sum(), item_agg["item_revenue"].sum(), rel_tol=1e-12):
        raise AssertionError("Item revenue changed during aggregation.")

    return model, item_agg


def build_kpis(order_model: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    delivered = order_model[order_model["is_delivered"]].copy()
    reviewed = delivered[delivered["review_score"].notna()]
    customer_frequency = delivered.groupby("customer_unique_id")["order_id"].nunique()
    delivery_known = delivered[delivered["is_late"].notna()]

    values = {
        "total_orders": float(order_model["order_id"].nunique()),
        "delivered_orders": float(delivered["order_id"].nunique()),
        "delivered_gmv": float(delivered["item_revenue"].sum()),
        "delivered_freight": float(delivered["freight_value"].sum()),
        "average_order_value": float(delivered["item_revenue"].sum() / delivered["order_id"].nunique()),
        "active_customers": float(customer_frequency.size),
        "repeat_customers": float(customer_frequency.ge(2).sum()),
        "repeat_customer_rate": float(customer_frequency.ge(2).mean()),
        "cancellation_rate": float(order_model["is_canceled"].mean()),
        "unavailable_rate": float(order_model["is_unavailable"].mean()),
        "on_time_delivery_rate": float((~delivery_known["is_late"].astype(bool)).mean()),
        "average_delivery_days": float(delivered["delivery_days"].mean()),
        "average_review_score": float(delivered["review_score"].mean()),
        "low_review_rate": float(reviewed["review_score"].le(2).mean()),
    }
    definitions = {
        "total_orders": ("总订单数", "orders", "全部状态的唯一订单数"),
        "delivered_orders": ("成交订单数", "orders", "状态为 delivered 的订单数"),
        "delivered_gmv": ("成交额", "BRL", "成交订单商品价格合计，不含运费"),
        "delivered_freight": ("成交运费", "BRL", "成交订单运费合计"),
        "average_order_value": ("客单价", "BRL/order", "成交额除以成交订单数"),
        "active_customers": ("购买顾客数", "customers", "至少一笔成交订单的顾客数"),
        "repeat_customers": ("复购顾客数", "customers", "至少两笔成交订单的顾客数"),
        "repeat_customer_rate": ("复购率", "rate", "复购顾客数除以购买顾客数"),
        "cancellation_rate": ("取消率", "rate", "canceled 订单占全部订单比例"),
        "unavailable_rate": ("缺货不可用率", "rate", "unavailable 订单占全部订单比例"),
        "on_time_delivery_rate": ("准时送达率", "rate", "实际送达不晚于预计日期的比例"),
        "average_delivery_days": ("平均履约天数", "days", "下单到实际送达的平均天数"),
        "average_review_score": ("平均评分", "score", "成交订单平均评价分数"),
        "low_review_rate": ("低评分率", "rate", "评价不高于 2 分的成交订单比例"),
    }
    rows = [
        {
            "metric": key,
            "metric_cn": definitions[key][0],
            "value": value,
            "unit": definitions[key][1],
            "definition": definitions[key][2],
        }
        for key, value in values.items()
    ]
    return pd.DataFrame(rows), values


def build_monthly_metrics(order_model: pd.DataFrame) -> pd.DataFrame:
    monthly_orders = (
        order_model.groupby("purchase_month", as_index=False)
        .agg(total_orders=("order_id", "nunique"))
        .sort_values("purchase_month")
    )
    delivered = order_model[order_model["is_delivered"]].copy()
    delivered_monthly = (
        delivered.groupby("purchase_month", as_index=False)
        .agg(
            delivered_orders=("is_delivered", "sum"),
            delivered_gmv=("delivered_gmv", "sum"),
            delivered_freight=("delivered_freight", "sum"),
            purchasing_customers=("customer_unique_id", "nunique"),
            average_review_score=("review_score", "mean"),
            average_delivery_days=("delivery_days", "mean"),
        )
    )
    monthly = monthly_orders.merge(delivered_monthly, on="purchase_month", how="left")
    customer_month = (
        delivered.groupby(["purchase_month", "customer_unique_id"], as_index=False)
        .agg(first_order_number=("customer_order_number", "min"))
    )
    customer_mix = (
        customer_month.assign(customer_type=np.where(customer_month["first_order_number"].eq(1), "new", "returning"))
        .pivot_table(
            index="purchase_month", columns="customer_type", values="customer_unique_id", aggfunc="nunique", fill_value=0
        )
        .reset_index()
    )
    for column in ("new", "returning"):
        if column not in customer_mix:
            customer_mix[column] = 0
    late_monthly = (
        delivered[delivered["is_late"].notna()]
        .groupby("purchase_month", as_index=False)
        .agg(on_time_delivery_rate=("is_late", lambda x: float((~x.astype(bool)).mean())))
    )
    monthly = monthly.merge(customer_mix, on="purchase_month", how="left").merge(
        late_monthly, on="purchase_month", how="left"
    )
    monthly = monthly.rename(columns={"new": "new_customers", "returning": "returning_customers"})
    monthly["average_order_value"] = monthly["delivered_gmv"] / monthly["delivered_orders"]
    monthly["is_complete_core_month"] = monthly["purchase_month"].between("2017-01-01", "2018-08-01")
    monthly["mom_gmv_growth"] = monthly["delivered_gmv"].pct_change(fill_method=None)
    previous_month = monthly["purchase_month"].shift(1)
    consecutive_month = monthly["purchase_month"].eq(previous_month + pd.offsets.MonthBegin(1))
    valid_mom = (
        monthly["is_complete_core_month"]
        & monthly["is_complete_core_month"].shift(1, fill_value=False)
        & consecutive_month
    )
    monthly.loc[~valid_mom, "mom_gmv_growth"] = np.nan
    return monthly


def quintile_score(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    ranked = series.rank(method="first", ascending=True)
    score = pd.qcut(ranked, 5, labels=[1, 2, 3, 4, 5]).astype(int)
    return score if higher_is_better else 6 - score


def assign_segment(row: pd.Series) -> str:
    frequency = row["frequency"]
    recency = row["recency_days"]
    if frequency >= 3 and recency <= 90:
        return "Champions"
    if frequency >= 2 and recency <= 180:
        return "Loyal"
    if frequency >= 2:
        return "At-risk repeat"
    if recency <= 90 and row["m_score"] >= 4:
        return "High-value new"
    if recency <= 90:
        return "New"
    if recency > 365:
        return "Hibernating"
    return "Need attention"


def build_rfm(order_model: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    delivered = order_model[order_model["is_delivered"]].copy()
    reference_date = delivered["order_purchase_timestamp"].max().normalize() + pd.Timedelta(days=1)
    rfm = (
        delivered.groupby("customer_unique_id", as_index=False)
        .agg(
            last_purchase=("order_purchase_timestamp", "max"),
            first_purchase=("order_purchase_timestamp", "min"),
            frequency=("order_id", "nunique"),
            monetary=("item_revenue", "sum"),
            freight=("freight_value", "sum"),
            average_review_score=("review_score", "mean"),
        )
    )
    rfm["recency_days"] = (reference_date - rfm["last_purchase"].dt.normalize()).dt.days
    rfm["r_score"] = quintile_score(rfm["recency_days"], higher_is_better=False)
    # Frequency is extremely concentrated at one order. Quantile scoring would
    # arbitrarily split tied one-time buyers, so use transparent count bands.
    rfm["f_score"] = np.select(
        [rfm["frequency"].ge(4), rfm["frequency"].eq(3), rfm["frequency"].eq(2)],
        [5, 4, 3],
        default=1,
    )
    rfm["m_score"] = quintile_score(rfm["monetary"], higher_is_better=True)
    rfm["rfm_score"] = rfm[["r_score", "f_score", "m_score"]].astype(str).agg("".join, axis=1)
    rfm["segment"] = rfm.apply(assign_segment, axis=1)
    segment_summary = (
        rfm.groupby("segment", as_index=False)
        .agg(
            customers=("customer_unique_id", "nunique"),
            revenue=("monetary", "sum"),
            average_orders=("frequency", "mean"),
            average_customer_value=("monetary", "mean"),
            average_recency_days=("recency_days", "mean"),
        )
        .sort_values("customers", ascending=False)
    )
    segment_summary["customer_share"] = segment_summary["customers"] / segment_summary["customers"].sum()
    segment_summary["revenue_share"] = segment_summary["revenue"] / segment_summary["revenue"].sum()
    return rfm, segment_summary


def build_repurchase_analysis(
    order_model: pd.DataFrame, item_detail: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], pd.DataFrame]:
    """Build a right-censoring-aware 90-day repurchase diagnostic.

    Only customers whose first purchase has at least 90 subsequent observation
    days are used when comparing first-order attributes. This makes recent and
    early cohorts comparable and avoids treating customers without enough
    follow-up time as non-repeat buyers.
    """

    delivered = order_model[
        order_model["is_delivered"] & order_model["customer_unique_id"].notna()
    ].copy()
    delivered = delivered.sort_values(["customer_unique_id", "order_purchase_timestamp", "order_id"])
    reference_date = delivered["order_purchase_timestamp"].max().normalize() + pd.Timedelta(days=1)

    first_orders = delivered.drop_duplicates("customer_unique_id", keep="first").copy()
    first_orders = first_orders.rename(
        columns={
            "order_id": "first_order_id",
            "order_purchase_timestamp": "first_purchase_at",
            "purchase_month": "first_purchase_month",
            "customer_state": "first_customer_state",
            "item_revenue": "first_order_value",
            "freight_value": "first_freight_value",
            "review_score": "first_review_score",
            "is_late": "first_is_late",
            "delivery_days": "first_delivery_days",
        }
    )
    first_orders = first_orders[
        [
            "customer_unique_id",
            "first_order_id",
            "first_purchase_at",
            "first_purchase_month",
            "first_customer_state",
            "first_order_value",
            "first_freight_value",
            "first_review_score",
            "first_is_late",
            "first_delivery_days",
        ]
    ]

    second_orders = delivered[delivered["customer_order_number"].eq(2)][
        ["customer_unique_id", "order_purchase_timestamp"]
    ].rename(columns={"order_purchase_timestamp": "second_purchase_at"})

    customer_lifetime = (
        delivered.groupby("customer_unique_id", as_index=False)
        .agg(
            lifetime_orders=("order_id", "nunique"),
            lifetime_revenue=("item_revenue", "sum"),
            last_purchase_at=("order_purchase_timestamp", "max"),
        )
    )

    first_item_categories = item_detail[
        item_detail["order_id"].isin(first_orders["first_order_id"])
    ].copy()
    first_primary_category = (
        first_item_categories.groupby(["order_id", "category"], as_index=False)["price"]
        .sum()
        .sort_values(["order_id", "price", "category"], ascending=[True, False, True])
        .drop_duplicates("order_id")
        .rename(
            columns={
                "order_id": "first_order_id",
                "category": "first_primary_category",
                "price": "first_primary_category_revenue",
            }
        )
    )

    customer_base = (
        first_orders.merge(second_orders, on="customer_unique_id", how="left", validate="one_to_one")
        .merge(customer_lifetime, on="customer_unique_id", how="left", validate="one_to_one")
        .merge(first_primary_category, on="first_order_id", how="left", validate="one_to_one")
    )
    customer_base["observation_days"] = (
        reference_date - customer_base["first_purchase_at"].dt.normalize()
    ).dt.days
    customer_base["eligible_90d"] = customer_base["observation_days"].ge(90)
    customer_base["repeat_within_90d"] = (
        customer_base["second_purchase_at"].notna()
        & customer_base["second_purchase_at"].le(
            customer_base["first_purchase_at"] + pd.Timedelta(days=90)
        )
    )
    customer_base["first_delivery_status"] = np.select(
        [
            customer_base["first_is_late"].eq(True).fillna(False).to_numpy(dtype=bool),
            customer_base["first_is_late"].eq(False).fillna(False).to_numpy(dtype=bool),
        ],
        ["Late", "On time"],
        default="Unknown",
    )
    customer_base["first_review_group"] = np.select(
        [
            customer_base["first_review_score"].le(2),
            customer_base["first_review_score"].gt(2) & customer_base["first_review_score"].lt(4),
            customer_base["first_review_score"].ge(4),
        ],
        ["Low (1-2)", "Neutral (>2,<4)", "High (4-5)"],
        default="Missing",
    )
    customer_base["first_order_value_score"] = quintile_score(
        customer_base["first_order_value"], higher_is_better=True
    )
    value_labels = {
        1: "Q1 lowest",
        2: "Q2",
        3: "Q3",
        4: "Q4",
        5: "Q5 highest",
    }
    customer_base["first_order_value_band"] = customer_base["first_order_value_score"].map(value_labels)

    eligible = customer_base[customer_base["eligible_90d"]].copy()

    def summarize(dimension: str, minimum_customers: int) -> pd.DataFrame:
        result = (
            eligible.groupby(dimension, dropna=False, as_index=False)
            .agg(
                customers=("customer_unique_id", "nunique"),
                repeat_90d_customers=("repeat_within_90d", "sum"),
                average_first_order_value=("first_order_value", "mean"),
                average_first_review_score=("first_review_score", "mean"),
            )
        )
        result["repeat_90d_rate"] = result["repeat_90d_customers"] / result["customers"]
        result["reliable_sample"] = result["customers"].ge(minimum_customers)
        return result.sort_values(["reliable_sample", "repeat_90d_rate", "customers"], ascending=False)

    summaries = {
        "repurchase_by_state": summarize("first_customer_state", 300),
        "repurchase_by_first_category": summarize("first_primary_category", 300),
        "repurchase_by_first_value_band": summarize("first_order_value_band", 100),
        "repurchase_by_first_delivery": summarize("first_delivery_status", 100),
        "repurchase_by_first_review": summarize("first_review_group", 100),
    }

    tests: list[dict[str, object]] = []
    for analysis_name, dimension, allowed_values in (
        ("First delivery status vs 90-day repeat", "first_delivery_status", ["Late", "On time"]),
        (
            "First review group vs 90-day repeat",
            "first_review_group",
            ["Low (1-2)", "Neutral (>2,<4)", "High (4-5)"],
        ),
        (
            "First order value band vs 90-day repeat",
            "first_order_value_band",
            ["Q1 lowest", "Q2", "Q3", "Q4", "Q5 highest"],
        ),
    ):
        analysis_frame = eligible[eligible[dimension].isin(allowed_values)]
        contingency = pd.crosstab(analysis_frame[dimension], analysis_frame["repeat_within_90d"])
        if contingency.shape[0] >= 2 and contingency.shape[1] == 2:
            statistic, p_value, degrees_freedom, _ = stats.chi2_contingency(contingency)
            cramers_v = math.sqrt(statistic / (contingency.to_numpy().sum() * (min(contingency.shape) - 1)))
        else:
            statistic = p_value = degrees_freedom = cramers_v = np.nan
        tests.append(
            {
                "analysis": analysis_name,
                "chi_square": statistic,
                "degrees_freedom": degrees_freedom,
                "p_value": p_value,
                "cramers_v": cramers_v,
                "customers": len(analysis_frame),
            }
        )

    return customer_base, summaries, pd.DataFrame(tests)


def build_cohorts(order_model: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    delivered = order_model[order_model["is_delivered"]].copy()
    delivered["order_month"] = delivered["order_purchase_timestamp"].dt.to_period("M")
    last_observed_month = delivered["order_month"].max()
    first_month = delivered.groupby("customer_unique_id")["order_month"].min().rename("cohort_month")
    activity = delivered[["customer_unique_id", "order_month"]].drop_duplicates().merge(
        first_month, on="customer_unique_id", how="left", validate="many_to_one"
    )
    activity["cohort_index"] = (
        (activity["order_month"].dt.year - activity["cohort_month"].dt.year) * 12
        + activity["order_month"].dt.month
        - activity["cohort_month"].dt.month
    )
    counts = (
        activity.groupby(["cohort_month", "cohort_index"], as_index=False)
        .agg(active_customers=("customer_unique_id", "nunique"))
    )
    sizes = counts[counts["cohort_index"].eq(0)][["cohort_month", "active_customers"]].rename(
        columns={"active_customers": "cohort_size"}
    )
    observable_grid = pd.concat(
        [
            pd.DataFrame(
                {
                    "cohort_month": cohort.cohort_month,
                    "cohort_index": range(
                        last_observed_month.ordinal - cohort.cohort_month.ordinal + 1
                    ),
                }
            )
            for cohort in sizes.itertuples(index=False)
        ],
        ignore_index=True,
    )
    tidy = observable_grid.merge(
        counts,
        on=["cohort_month", "cohort_index"],
        how="left",
        validate="one_to_one",
    ).merge(sizes, on="cohort_month", how="left", validate="many_to_one")
    tidy["active_customers"] = tidy["active_customers"].fillna(0).astype("int64")
    tidy["retention_rate"] = tidy["active_customers"] / tidy["cohort_size"]
    tidy["cohort_month"] = tidy["cohort_month"].astype(str)
    tidy = tidy.sort_values(["cohort_month", "cohort_index"], ignore_index=True)
    matrix = (
        tidy.pivot(index="cohort_month", columns="cohort_index", values="retention_rate")
        .sort_index()
        .sort_index(axis=1)
    )
    return tidy, matrix


def welch_mean_difference_ci(late: pd.Series, on_time: pd.Series) -> tuple[float, float, float]:
    difference = float(late.mean() - on_time.mean())
    variance = late.var(ddof=1) / len(late) + on_time.var(ddof=1) / len(on_time)
    standard_error = math.sqrt(variance)
    numerator = variance**2
    denominator = (late.var(ddof=1) / len(late)) ** 2 / (len(late) - 1) + (
        on_time.var(ddof=1) / len(on_time)
    ) ** 2 / (len(on_time) - 1)
    degrees_freedom = numerator / denominator
    critical = stats.t.ppf(0.975, degrees_freedom)
    return difference, difference - critical * standard_error, difference + critical * standard_error


def build_delivery_analysis(order_model: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    delivery = order_model[
        order_model["is_delivered"] & order_model["is_late"].notna() & order_model["review_score"].notna()
    ].copy()
    delivery["delivery_status"] = np.where(delivery["is_late"].astype(bool), "Late", "On time")
    summary = (
        delivery.groupby("delivery_status", as_index=False)
        .agg(
            orders=("order_id", "nunique"),
            average_review_score=("review_score", "mean"),
            low_review_rate=("review_score", lambda x: float(x.le(2).mean())),
            average_delivery_days=("delivery_days", "mean"),
            average_delta_days=("delivery_delta_days", "mean"),
        )
    )

    late_scores = delivery.loc[delivery["delivery_status"].eq("Late"), "review_score"]
    on_time_scores = delivery.loc[delivery["delivery_status"].eq("On time"), "review_score"]
    mean_diff, ci_low, ci_high = welch_mean_difference_ci(late_scores, on_time_scores)
    mann = stats.mannwhitneyu(late_scores, on_time_scores, alternative="two-sided")
    spearman = stats.spearmanr(delivery["delivery_delta_days"], delivery["review_score"], nan_policy="omit")
    tests = pd.DataFrame(
        [
            {
                "analysis": "Late minus on-time mean review score",
                "estimate": mean_diff,
                "ci_95_low": ci_low,
                "ci_95_high": ci_high,
                "statistic": np.nan,
                "p_value": np.nan,
            },
            {
                "analysis": "Mann-Whitney U: late vs on-time review score",
                "estimate": np.nan,
                "ci_95_low": np.nan,
                "ci_95_high": np.nan,
                "statistic": float(mann.statistic),
                "p_value": float(mann.pvalue),
            },
            {
                "analysis": "Spearman: delivery delta days vs review score",
                "estimate": float(spearman.statistic),
                "ci_95_low": np.nan,
                "ci_95_high": np.nan,
                "statistic": float(spearman.statistic),
                "p_value": float(spearman.pvalue),
            },
        ]
    )
    return summary, tests


def build_commercial_marts(
    tables: dict[str, pd.DataFrame], order_model: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    items = tables["items"]
    products = tables["products"].merge(
        tables["translation"], on="product_category_name", how="left", validate="many_to_one"
    )
    products["category"] = products["product_category_name_english"].fillna(
        products["product_category_name"].fillna("unknown")
    )
    products["product_volume_cm3"] = (
        products["product_length_cm"]
        * products["product_height_cm"]
        * products["product_width_cm"]
    )
    item_detail = (
        items.merge(
            products[
                [
                    "product_id",
                    "category",
                    "product_weight_g",
                    "product_length_cm",
                    "product_height_cm",
                    "product_width_cm",
                    "product_volume_cm3",
                ]
            ],
            on="product_id",
            how="left",
            validate="many_to_one",
        )
        .merge(
            tables["sellers"],
            on="seller_id",
            how="left",
            validate="many_to_one",
        )
        .merge(
            order_model[
                [
                    "order_id",
                    "customer_unique_id",
                    "customer_city",
                    "customer_state",
                    "order_purchase_timestamp",
                    "purchase_month",
                    "order_status",
                    "is_delivered",
                    "delivery_days",
                    "delivery_delta_days",
                    "is_late",
                    "review_score",
                ]
            ],
            on="order_id",
            how="left",
            validate="many_to_one",
        )
    )
    item_detail["category"] = item_detail["category"].fillna("unknown")
    delivered_items = item_detail[item_detail["is_delivered"]].copy()

    category_order = (
        delivered_items.groupby(["category", "order_id"], as_index=False)
        .agg(
            category_revenue=("price", "sum"),
            category_freight=("freight_value", "sum"),
            items=("order_item_id", "count"),
            customer_unique_id=("customer_unique_id", "first"),
            purchase_month=("purchase_month", "first"),
            review_score=("review_score", "first"),
            is_late=("is_late", "first"),
        )
    )
    category = (
        category_order.groupby("category", as_index=False)
        .agg(
            revenue=("category_revenue", "sum"),
            freight=("category_freight", "sum"),
            orders=("order_id", "nunique"),
            customers=("customer_unique_id", "nunique"),
            items=("items", "sum"),
            reviewed_orders=("review_score", "count"),
            low_review_orders=("review_score", lambda x: int(x.dropna().le(2).sum())),
            average_review_score=("review_score", "mean"),
            low_review_rate=("review_score", lambda x: float(x.dropna().le(2).mean())),
            late_delivery_rate=("is_late", lambda x: float(x.dropna().astype(bool).mean())),
        )
        .sort_values("revenue", ascending=False)
    )
    category["average_item_price"] = category["revenue"] / category["items"]
    category["freight_to_revenue_rate"] = category["freight"] / category["revenue"]
    reliable_category = category["orders"].ge(300)
    revenue_median = category.loc[reliable_category, "revenue"].median()
    rating_median = category.loc[reliable_category, "average_review_score"].median()
    category["portfolio_quadrant"] = np.select(
        [
            category["revenue"].ge(revenue_median) & category["average_review_score"].ge(rating_median),
            category["revenue"].ge(revenue_median) & category["average_review_score"].lt(rating_median),
            category["revenue"].lt(revenue_median) & category["average_review_score"].ge(rating_median),
        ],
        ["High revenue / High rating", "High revenue / Low rating", "Low revenue / High rating"],
        default="Low revenue / Low rating",
    )
    category["reliable_sample"] = reliable_category

    comparable = category_order[
        category_order["purchase_month"].dt.year.isin([2017, 2018])
        & category_order["purchase_month"].dt.month.le(8)
    ].copy()
    comparable["comparison_year"] = comparable["purchase_month"].dt.year
    category_year = (
        comparable.groupby(["category", "comparison_year"], as_index=False)
        .agg(
            revenue=("category_revenue", "sum"),
            orders=("order_id", "nunique"),
            average_review_score=("review_score", "mean"),
            late_delivery_rate=("is_late", lambda x: float(x.dropna().astype(bool).mean())),
        )
    )
    category_year_wide = category_year.pivot(index="category", columns="comparison_year").reset_index()
    category_year_wide.columns = [
        column if isinstance(column, str) else "_".join(str(part) for part in column if str(part))
        for column in category_year_wide.columns
    ]
    category_diagnostics = category[["category", "revenue", "orders", "portfolio_quadrant"]].merge(
        category_year_wide,
        on="category",
        how="left",
        validate="one_to_one",
    )
    rename_columns = {
        "revenue_2017": "revenue_2017_jan_aug",
        "revenue_2018": "revenue_2018_jan_aug",
        "orders_2017": "orders_2017_jan_aug",
        "orders_2018": "orders_2018_jan_aug",
        "average_review_score_2017": "average_review_score_2017_jan_aug",
        "average_review_score_2018": "average_review_score_2018_jan_aug",
        "late_delivery_rate_2017": "late_delivery_rate_2017_jan_aug",
        "late_delivery_rate_2018": "late_delivery_rate_2018_jan_aug",
    }
    category_diagnostics = category_diagnostics.rename(columns=rename_columns)
    category_diagnostics["revenue_growth"] = (
        category_diagnostics["revenue_2018_jan_aug"]
        / category_diagnostics["revenue_2017_jan_aug"].replace(0, np.nan)
        - 1
    )
    category_diagnostics["review_score_change"] = (
        category_diagnostics["average_review_score_2018_jan_aug"]
        - category_diagnostics["average_review_score_2017_jan_aug"]
    )
    category_diagnostics["late_rate_change"] = (
        category_diagnostics["late_delivery_rate_2018_jan_aug"]
        - category_diagnostics["late_delivery_rate_2017_jan_aug"]
    )
    category_diagnostics["comparable_sample"] = (
        category_diagnostics["orders_2017_jan_aug"].ge(100)
        & category_diagnostics["orders_2018_jan_aug"].ge(100)
    )
    category_diagnostics["growth_quality_risk"] = (
        category_diagnostics["comparable_sample"]
        & category_diagnostics["revenue_growth"].gt(0)
        & (
            category_diagnostics["review_score_change"].lt(-0.1)
            | category_diagnostics["late_rate_change"].gt(0.03)
        )
    )
    category_diagnostics = category_diagnostics.sort_values(
        ["growth_quality_risk", "revenue_growth", "revenue"], ascending=[False, False, False]
    )

    seller_order = (
        delivered_items.groupby(["seller_id", "order_id"], as_index=False)
        .agg(
            seller_revenue=("price", "sum"),
            seller_freight=("freight_value", "sum"),
            items=("order_item_id", "count"),
            seller_state=("seller_state", "first"),
            customer_state=("customer_state", "first"),
            review_score=("review_score", "first"),
            is_late=("is_late", "first"),
            delivery_days=("delivery_days", "first"),
        )
    )
    seller = (
        seller_order.groupby("seller_id", as_index=False)
        .agg(
            seller_state=("seller_state", "first"),
            orders=("order_id", "nunique"),
            revenue=("seller_revenue", "sum"),
            freight=("seller_freight", "sum"),
            items=("items", "sum"),
            reviewed_orders=("review_score", "count"),
            low_review_orders=("review_score", lambda x: int(x.dropna().le(2).sum())),
            average_review_score=("review_score", "mean"),
            low_review_rate=("review_score", lambda x: float(x.dropna().le(2).mean())),
            late_delivery_rate=("is_late", lambda x: float(x.dropna().astype(bool).mean())),
            average_delivery_days=("delivery_days", "mean"),
        )
        .sort_values("revenue", ascending=False)
    )
    seller["reliable_sample"] = seller["orders"].ge(30)
    seller["freight_to_revenue_rate"] = seller["freight"] / seller["revenue"]

    delivered_orders = order_model[order_model["is_delivered"]].copy()
    state = (
        delivered_orders.groupby("customer_state", as_index=False)
        .agg(
            orders=("order_id", "nunique"),
            customers=("customer_unique_id", "nunique"),
            revenue=("item_revenue", "sum"),
            freight=("freight_value", "sum"),
            reviewed_orders=("review_score", "count"),
            low_review_orders=("review_score", lambda x: int(x.dropna().le(2).sum())),
            average_review_score=("review_score", "mean"),
            low_review_rate=("review_score", lambda x: float(x.dropna().le(2).mean())),
            late_delivery_rate=("is_late", lambda x: float(x.dropna().astype(bool).mean())),
            average_delivery_days=("delivery_days", "mean"),
        )
        .sort_values("revenue", ascending=False)
    )
    state["average_order_value"] = state["revenue"] / state["orders"]
    state["freight_to_revenue_rate"] = state["freight"] / state["revenue"]
    state["reliable_sample"] = state["orders"].ge(500)

    return item_detail, category, category_diagnostics, seller, state


def save_tables(
    order_model: pd.DataFrame,
    item_detail: pd.DataFrame,
    rfm: pd.DataFrame,
    outputs: dict[str, pd.DataFrame],
) -> None:
    for name, frame in outputs.items():
        frame.to_csv(TABLE_DIR / f"{name}.csv", index=True if name == "cohort_retention_matrix" else False)

    order_columns = [
        "order_id",
        "customer_unique_id",
        "order_status",
        "order_purchase_timestamp",
        "purchase_date",
        "purchase_month",
        "customer_city",
        "customer_state",
        "item_revenue",
        "freight_value",
        "item_count",
        "unique_products",
        "seller_count",
        "payment_value",
        "primary_payment_type",
        "max_installments",
        "review_score",
        "delivery_days",
        "delivery_delta_days",
        "is_late",
        "customer_order_number",
        "is_repeat_order",
    ]
    order_model[order_columns].to_csv(PROCESSED_DIR / "powerbi_orders.csv", index=False)
    item_detail.to_csv(PROCESSED_DIR / "powerbi_order_items.csv", index=False)
    rfm.to_csv(PROCESSED_DIR / "powerbi_customers.csv", index=False)


def create_figures(
    monthly: pd.DataFrame,
    segment_summary: pd.DataFrame,
    cohort_matrix: pd.DataFrame,
    delivery_summary: pd.DataFrame,
    category: pd.DataFrame,
    repurchase_summaries: dict[str, pd.DataFrame],
    category_diagnostics: pd.DataFrame,
) -> None:
    sns.set_theme(style="whitegrid", context="talk")
    plt.rcParams["figure.dpi"] = 140

    core = monthly[monthly["is_complete_core_month"]].copy()
    fig, left = plt.subplots(figsize=(13, 6.5))
    left.plot(core["purchase_month"], core["delivered_gmv"], marker="o", color="#2563EB", linewidth=2)
    left.set_ylabel("Delivered merchandise value (BRL)", color="#2563EB")
    left.tick_params(axis="y", labelcolor="#2563EB")
    right = left.twinx()
    right.plot(core["purchase_month"], core["delivered_orders"], marker="s", color="#F97316", linewidth=2)
    right.set_ylabel("Delivered orders", color="#F97316")
    right.tick_params(axis="y", labelcolor="#F97316")
    left.set_title("Monthly GMV and delivered orders (complete months)")
    left.set_xlabel("")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "01_monthly_performance.png", bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 6))
    chart = segment_summary.sort_values("customers")
    sns.barplot(data=chart, x="customers", y="segment", hue="segment", legend=False, palette="Blues_r", ax=ax)
    ax.set_title("Customer segments")
    ax.set_xlabel("Customers")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "02_rfm_segments.png", bbox_inches="tight")
    plt.close(fig)

    cohort_chart = cohort_matrix.loc[cohort_matrix.index >= "2017-01"]
    visible_columns = [column for column in cohort_chart.columns if column <= 12]
    annotations = cohort_chart[visible_columns].map(
        lambda value: "" if pd.isna(value) else ("100%" if value == 1 else f"{value:.1%}")
    )
    fig, ax = plt.subplots(figsize=(13, 9))
    sns.heatmap(
        cohort_chart[visible_columns],
        cmap="Blues",
        vmin=0,
        vmax=max(0.1, float(cohort_chart[visible_columns].iloc[:, 1:].max().max())),
        fmt="",
        annot=annotations,
        linewidths=0.3,
        cbar_kws={"label": "Retention rate"},
        ax=ax,
    )
    ax.set_title("Monthly customer cohort retention (cohorts from 2017-01)")
    ax.set_xlabel("Months since first purchase")
    ax.set_ylabel("First purchase month")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "03_cohort_retention.png", bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    delivery_colors = {"Late": "#DC2626", "On time": "#2563EB"}
    sns.barplot(
        data=delivery_summary,
        x="delivery_status",
        y="average_review_score",
        hue="delivery_status",
        legend=False,
        palette=delivery_colors,
        ax=axes[0],
    )
    axes[0].set_ylim(0, 5)
    axes[0].set_title("Average review score")
    axes[0].set_xlabel("")
    axes[0].set_ylabel("Score")
    for container in axes[0].containers:
        axes[0].bar_label(container, fmt="%.2f", padding=3)
    sns.barplot(
        data=delivery_summary,
        x="delivery_status",
        y="low_review_rate",
        hue="delivery_status",
        legend=False,
        palette=delivery_colors,
        ax=axes[1],
    )
    axes[1].set_title("Low-review rate (score <= 2)")
    axes[1].set_xlabel("")
    axes[1].set_ylabel("Rate")
    axes[1].set_ylim(0, 0.65)
    axes[1].yaxis.set_major_formatter(plt.FuncFormatter(lambda value, _: f"{value:.0%}"))
    for container in axes[1].containers:
        labels = [f"{bar.get_height():.1%}" for bar in container]
        axes[1].bar_label(container, labels=labels, padding=3)
    fig.suptitle("Delivery performance and customer satisfaction", y=1.03)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "04_delivery_and_reviews.png", bbox_inches="tight")
    plt.close(fig)

    top_category = category.head(12).sort_values("revenue").copy()
    top_category["category_label"] = top_category["category"].str.replace("_", " ", regex=False)
    fig, ax = plt.subplots(figsize=(11, 7))
    sns.barplot(
        data=top_category,
        x="revenue",
        y="category_label",
        hue="category_label",
        legend=False,
        palette="viridis",
        ax=ax,
    )
    ax.set_title("Top product categories by delivered merchandise value")
    ax.set_xlabel("Revenue (BRL)")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "05_top_categories.png", bbox_inches="tight")
    plt.close(fig)

    delivery_repurchase = repurchase_summaries["repurchase_by_first_delivery"]
    delivery_repurchase = delivery_repurchase[
        delivery_repurchase["first_delivery_status"].isin(["Late", "On time"])
    ].copy()
    review_repurchase = repurchase_summaries["repurchase_by_first_review"]
    review_order = ["Low (1-2)", "Neutral (>2,<4)", "High (4-5)"]
    review_repurchase = review_repurchase[
        review_repurchase["first_review_group"].isin(review_order)
    ].copy()
    review_repurchase["first_review_group"] = pd.Categorical(
        review_repurchase["first_review_group"], categories=review_order, ordered=True
    )
    review_repurchase = review_repurchase.sort_values("first_review_group")

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    sns.barplot(
        data=delivery_repurchase,
        x="first_delivery_status",
        y="repeat_90d_rate",
        hue="first_delivery_status",
        legend=False,
        palette=delivery_colors,
        ax=axes[0],
    )
    axes[0].set_title("90-day repeat rate by first delivery")
    axes[0].set_xlabel("")
    axes[0].set_ylabel("90-day repeat rate")
    axes[0].yaxis.set_major_formatter(plt.FuncFormatter(lambda value, _: f"{value:.1%}"))
    for patch, row in zip(axes[0].patches, delivery_repurchase.itertuples()):
        axes[0].text(
            patch.get_x() + patch.get_width() / 2,
            patch.get_height(),
            f"{row.repeat_90d_rate:.2%}\n(n={row.customers:,})",
            ha="center",
            va="bottom",
            fontsize=10,
        )

    review_colors = {
        "Low (1-2)": "#DC2626",
        "Neutral (>2,<4)": "#F59E0B",
        "High (4-5)": "#2563EB",
    }
    sns.barplot(
        data=review_repurchase,
        x="first_review_group",
        y="repeat_90d_rate",
        hue="first_review_group",
        legend=False,
        palette=review_colors,
        ax=axes[1],
    )
    axes[1].set_title("90-day repeat rate by first review")
    axes[1].set_xlabel("")
    axes[1].set_ylabel("90-day repeat rate")
    axes[1].yaxis.set_major_formatter(plt.FuncFormatter(lambda value, _: f"{value:.1%}"))
    for patch, row in zip(axes[1].patches, review_repurchase.itertuples()):
        axes[1].text(
            patch.get_x() + patch.get_width() / 2,
            patch.get_height(),
            f"{row.repeat_90d_rate:.2%}\n(n={row.customers:,})",
            ha="center",
            va="bottom",
            fontsize=10,
        )
    max_rate = max(delivery_repurchase["repeat_90d_rate"].max(), review_repurchase["repeat_90d_rate"].max())
    for ax in axes:
        ax.set_ylim(0, max_rate * 1.35)
    fig.suptitle("First-order experience and observed 90-day repeat purchase", y=1.03)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "06_repurchase_first_experience.png", bbox_inches="tight")
    plt.close(fig)

    comparable_category = category_diagnostics[
        category_diagnostics["comparable_sample"]
        & category_diagnostics["revenue_growth"].notna()
        & category_diagnostics["review_score_change"].notna()
    ].copy()
    if not comparable_category.empty:
        revenue_scale = np.sqrt(comparable_category["revenue"].clip(lower=0))
        comparable_category["marker_size"] = 80 + 520 * revenue_scale / revenue_scale.max()
        fig, ax = plt.subplots(figsize=(12, 7))
        for is_risk, group in comparable_category.groupby("growth_quality_risk"):
            ax.scatter(
                group["revenue_growth"],
                group["review_score_change"],
                s=group["marker_size"],
                alpha=0.72,
                color="#DC2626" if is_risk else "#2563EB",
                edgecolor="white",
                linewidth=0.8,
                label="Growth with quality risk" if is_risk else "Other comparable categories",
            )
        ax.axvline(0, color="#6B7280", linewidth=1, linestyle="--")
        ax.axhline(0, color="#6B7280", linewidth=1, linestyle="--")
        labels = comparable_category[comparable_category["growth_quality_risk"]].head(8)
        for row in labels.itertuples():
            ax.annotate(
                row.category.replace("_", " "),
                (row.revenue_growth, row.review_score_change),
                xytext=(5, 5),
                textcoords="offset points",
                fontsize=9,
            )
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda value, _: f"{value:.0%}"))
        ax.set_title("Category growth versus change in customer rating")
        ax.set_xlabel("Revenue growth: Jan-Aug 2018 vs Jan-Aug 2017")
        ax.set_ylabel("Change in average review score")
        ax.legend(frameon=True, loc="best")
        fig.tight_layout()
        fig.savefig(FIGURE_DIR / "07_category_growth_quality.png", bbox_inches="tight")
        plt.close(fig)


def percent(value: float) -> str:
    return f"{value:.2%}"


def p_value_text(value: float) -> str:
    return "p<1e-300" if value == 0 else f"p={value:.3g}"


def write_findings(
    order_model: pd.DataFrame,
    kpi: dict[str, float],
    monthly: pd.DataFrame,
    cohort_tidy: pd.DataFrame,
    delivery_summary: pd.DataFrame,
    tests: pd.DataFrame,
    category: pd.DataFrame,
    category_diagnostics: pd.DataFrame,
    seller: pd.DataFrame,
    state: pd.DataFrame,
    customer_base: pd.DataFrame,
    repurchase_summaries: dict[str, pd.DataFrame],
    repurchase_tests: pd.DataFrame,
    quality_checks: pd.DataFrame,
) -> None:
    core = monthly[monthly["is_complete_core_month"]]
    peak = core.loc[core["delivered_gmv"].idxmax()]
    first_period = core[core["purchase_month"].dt.year.eq(2017) & core["purchase_month"].dt.month.le(8)][
        "delivered_gmv"
    ].sum()
    second_period = core[core["purchase_month"].dt.year.eq(2018) & core["purchase_month"].dt.month.le(8)][
        "delivered_gmv"
    ].sum()
    comparable_growth = second_period / first_period - 1

    eligible_m1 = cohort_tidy[cohort_tidy["cohort_index"].eq(1)]
    weighted_m1 = eligible_m1["active_customers"].sum() / eligible_m1["cohort_size"].sum()

    delivery_index = delivery_summary.set_index("delivery_status")
    late_rating = float(delivery_index.loc["Late", "average_review_score"])
    on_time_rating = float(delivery_index.loc["On time", "average_review_score"])
    late_low = float(delivery_index.loc["Late", "low_review_rate"])
    on_time_low = float(delivery_index.loc["On time", "low_review_rate"])
    mean_diff = tests.loc[tests["analysis"].str.startswith("Late minus"), "estimate"].iloc[0]
    ci_low = tests.loc[tests["analysis"].str.startswith("Late minus"), "ci_95_low"].iloc[0]
    ci_high = tests.loc[tests["analysis"].str.startswith("Late minus"), "ci_95_high"].iloc[0]
    mann_p = tests.loc[tests["analysis"].str.startswith("Mann"), "p_value"].iloc[0]
    spearman_row = tests.loc[tests["analysis"].str.startswith("Spearman")].iloc[0]

    high_volume_states = state[state["orders"].ge(500)].sort_values("late_delivery_rate", ascending=False).head(5)
    reliable_sellers = seller[seller["reliable_sample"]]
    seller_watchlist = reliable_sellers.sort_values(
        ["low_review_rate", "late_delivery_rate", "orders"], ascending=[False, False, False]
    ).head(5)

    top_categories = "、".join(
        f"{row.category}（{row.revenue:,.0f} BRL）" for row in category.head(5).itertuples()
    )
    state_watch = "、".join(
        f"{row.customer_state}（延迟率 {percent(row.late_delivery_rate)}）" for row in high_volume_states.itertuples()
    )
    seller_watch = "、".join(
        f"{row.seller_id[:8]}…（{int(row.orders)} 单，低评分率 {percent(row.low_review_rate)}）"
        for row in seller_watchlist.itertuples()
    )

    eligible_customers = customer_base[customer_base["eligible_90d"]]
    repeat_90d_rate = float(eligible_customers["repeat_within_90d"].mean())

    def lookup_rate(summary_name: str, dimension: str, value: str) -> float:
        summary = repurchase_summaries[summary_name].set_index(dimension)
        return float(summary.loc[value, "repeat_90d_rate"]) if value in summary.index else np.nan

    late_repeat = lookup_rate("repurchase_by_first_delivery", "first_delivery_status", "Late")
    on_time_repeat = lookup_rate("repurchase_by_first_delivery", "first_delivery_status", "On time")
    low_review_repeat = lookup_rate("repurchase_by_first_review", "first_review_group", "Low (1-2)")
    high_review_repeat = lookup_rate("repurchase_by_first_review", "first_review_group", "High (4-5)")
    low_value_repeat = lookup_rate("repurchase_by_first_value_band", "first_order_value_band", "Q1 lowest")
    high_value_repeat = lookup_rate("repurchase_by_first_value_band", "first_order_value_band", "Q5 highest")

    quality_issues = quality_checks[
        quality_checks["failed_rows"].gt(0) & quality_checks["status"].isin(["WARN", "ERROR"])
    ]
    if quality_issues.empty:
        quality_issue_text = "未发现会阻断分析的关系、金额或时间异常。"
    else:
        quality_issue_text = "；".join(
            f"{row.check_name}={int(row.failed_rows):,}" for row in quality_issues.itertuples()
        ) + "。这些记录保留在质量报告中，并按相应业务口径处理。"

    risk_categories = category_diagnostics[category_diagnostics["growth_quality_risk"]].head(5)
    if risk_categories.empty:
        category_risk_text = "在设定的样本量与变化阈值下，未发现同时满足‘增长且质量恶化’的品类。"
    else:
        category_risk_text = "、".join(
            f"{row.category}（收入 {percent(row.revenue_growth)}，评分变化 {row.review_score_change:+.2f}，延迟率变化 {row.late_rate_change:+.2%}）"
            for row in risk_categories.itertuples()
        )

    repurchase_test_text = "；".join(
        f"{row.analysis}：{p_value_text(float(row.p_value))}，Cramér's V={row.cramers_v:.3f}"
        for row in repurchase_tests.itertuples()
        if pd.notna(row.p_value)
    )

    date_min = order_model["order_purchase_timestamp"].min().date().isoformat()
    date_max = order_model["order_purchase_timestamp"].max().date().isoformat()
    mann_p_text = p_value_text(float(mann_p))
    spearman_p_text = p_value_text(float(spearman_row["p_value"]))
    report = f"""# 电商经营分析与复购诊断：主要结论

> 本报告由分析脚本基于公开匿名数据自动生成。金额单位为 BRL。观察性数据只支持相关关系，不直接支持因果结论。

## 1. 数据概况

- 订单观察期：{date_min} 至 {date_max}。
- 总订单 {int(kpi['total_orders']):,} 笔，其中成交订单 {int(kpi['delivered_orders']):,} 笔。
- 成交商品金额 {kpi['delivered_gmv']:,.2f} BRL，成交运费 {kpi['delivered_freight']:,.2f} BRL。
- 平均客单价 {kpi['average_order_value']:,.2f} BRL。
- 数据质量检查结论：{quality_issue_text}

## 2. 经营表现

- 在 2017-01 至 2018-08 的完整核心月份中，成交额峰值出现在 {peak['purchase_month']:%Y-%m}，当月成交额 {peak['delivered_gmv']:,.2f} BRL、成交订单 {int(peak['delivered_orders']):,} 笔。
- 2018 年 1—8 月成交额相较 2017 年同期变化 {percent(comparable_growth)}。
- 成交额最高的五个品类为：{top_categories}。

## 3. 用户与复购

- 数据窗口内共有 {int(kpi['active_customers']):,} 名成交顾客，其中 {int(kpi['repeat_customers']):,} 名完成至少两笔订单，复购率为 {percent(kpi['repeat_customer_rate'])}。
- 对拥有至少一个后续观察月的同期群加权计算，次月留存率约为 {percent(weighted_m1)}。
- 为控制样本末端顾客观察期不足的问题，90 天复购诊断只纳入首购后至少可观察 90 天的 {len(eligible_customers):,} 名顾客；其 90 天内复购率为 {percent(repeat_90d_rate)}。
- 首单准时顾客的 90 天复购率为 {percent(on_time_repeat)}，首单延迟顾客为 {percent(late_repeat)}；首单高评分顾客为 {percent(high_review_repeat)}，低评分顾客为 {percent(low_review_repeat)}。
- 首单金额最低五分位顾客的 90 天复购率为 {percent(low_value_repeat)}，最高五分位为 {percent(high_value_repeat)}。
- 分类变量与 90 天复购的卡方检验结果：{repurchase_test_text}。即使统计显著，效应量和潜在混杂因素仍需同时考虑。
- 当前复购率衡量的是匿名数据观察窗口内的再次购买，不代表完整生命周期复购率；越晚进入样本的顾客观察期越短。

## 4. 物流与满意度

- 准时送达率为 {percent(kpi['on_time_delivery_rate'])}，平均履约时间为 {kpi['average_delivery_days']:.2f} 天。
- 准时订单平均评分 {on_time_rating:.2f}，延迟订单平均评分 {late_rating:.2f}；延迟组比准时组低 {abs(mean_diff):.2f} 分，差异的 95% 置信区间为 [{ci_low:.2f}, {ci_high:.2f}]。
- 准时订单低评分率为 {percent(on_time_low)}，延迟订单为 {percent(late_low)}，后者约为前者的 {late_low / on_time_low:.2f} 倍。
- Mann–Whitney 检验结果为 {mann_p_text}；配送相对预计日期的延迟天数与评分的 Spearman 相关系数为 {spearman_row['estimate']:.3f}（{spearman_p_text}）。
- 大样本州中延迟率较高的地区包括：{state_watch}。

这些结果说明延迟订单与更低评分明显相关，但仍可能受到商品、商家、地区和订单复杂度等混杂因素影响，不能直接解释为因果效应。

## 5. 商家诊断

- 为降低小样本波动，商家关注清单仅纳入至少 30 笔成交订单的商家。
- 当前低评分率较高的候选商家包括：{seller_watch}。
- 多卖家订单的评分是订单级评价，无法完全归因给单个商家，因此清单应作为进一步调查线索，而不是处罚依据。

## 6. 品类增长与质量

- 使用 2017 年 1—8 月与 2018 年 1—8 月进行同口径比较，并要求两个期间各至少 100 笔成交订单。
- 同时出现成交额增长、评分下降超过 0.1 分或延迟率上升超过 3 个百分点的品类包括：{category_risk_text}
- 该清单用于确定下钻优先级；仍需结合商家、地区、价格带和订单复杂度进一步定位原因。

## 7. 业务建议

1. **优先治理延迟履约。** 对高延迟州和高交易量商家设置分层 SLA，按周监控延迟率、低评分率和订单量，避免只看平台平均值。
2. **建立顾客二次购买触发机制。** 在首单完成后的 30—60 天内，结合品类、RFM 和预估触达成本开展小规模分层召回；首单金额与复购的效应量很小，不能只按高客单筛选。没有真实实验数据时，不宣称转化提升。
3. **区分增长和质量目标。** 高成交额品类继续用于拉动规模，同时将评分、延迟率和运费率加入品类经营看板，避免单纯按 GMV 排序。
4. **用实验验证策略。** 对优惠、召回和物流补贴采用随机对照或分阶段试点，以增量复购和增量利润作为最终评价指标。

## 8. 局限性

- 数据是匿名历史样本，缺少获客渠道、营销触达、商品成本、退款和平台佣金等字段。
- 成交额为成交订单商品价格合计，并非平台收入或利润。
- 复购分析受到有限观察窗口和右删失影响。
- 本报告中的策略收益尚未经过线上实验或真实业务验证。
"""
    (REPORT_DIR / "findings.md").write_text(report, encoding="utf-8")


def write_portfolio_materials(
    kpi: dict[str, float],
    delivery_summary: pd.DataFrame,
    customer_base: pd.DataFrame,
) -> None:
    delivery_index = delivery_summary.set_index("delivery_status")
    late_low = float(delivery_index.loc["Late", "low_review_rate"])
    on_time_low = float(delivery_index.loc["On time", "low_review_rate"])
    eligible = customer_base[customer_base["eligible_90d"]]
    repeat_90d = float(eligible["repeat_within_90d"].mean())

    interview = f"""# 面试讲解稿

## 30 秒版本

我使用 Olist 公开数据完成了一次电商经营与复购诊断，项目采用SQL、Python和Power BI分层设计。SQL模块定义建表、质量检查、订单聚合视图和业务指标查询；Python完成自动化校验、RFM、同期群、统计检验与图表；Power BI提供四页经营看板。建模时先分别聚合商品、支付和评价，再连接到订单，保证一单一行。样本期共有 {int(kpi['delivered_orders']):,} 笔成交订单，成交额 {kpi['delivered_gmv']:,.0f} BRL；复购率为 {percent(kpi['repeat_customer_rate'])}，延迟订单低评分率为 {percent(late_low)}，约为准时订单的 {late_low / on_time_low:.2f} 倍。

## 3 分钟版本

### 1. 问题与口径

我把任务定义为一次经营诊断，而不是简单的数据可视化。核心问题是经营趋势、用户复购、履约体验以及品类和商家风险。成交订单限定为 delivered；成交额只计算商品价格，不含运费，也不把它解释为利润或财务收入。复购分析使用 customer_unique_id，因为 customer_id 是订单级编号。

### 2. 数据建模

原始数据包含 9 张表。订单商品、支付和评价都是一对多关系，如果直接连接会放大金额。我先分别按 order_id 聚合，再与订单和顾客表连接，得到一单一行的宽表；随后验证 order_id 唯一、商品金额聚合前后一致、孤儿记录、负金额和时间先后关系。

### 3. 分析方法

我在订单层建立经营 KPI，在顾客层建立 RFM 和同期群。总体复购率会受到样本截止日影响，所以首单体验与复购的比较只使用首购后至少可观察 90 天的 {len(eligible):,} 名顾客，90 天内复购率为 {percent(repeat_90d)}。物流与评分部分同时报告 Mann–Whitney U 检验、Spearman 相关、均值差异和 95% 置信区间，不只看 p 值。

### 4. 结论与建议

平台样本期复购率只有 {percent(kpi['repeat_customer_rate'])}，因此运营重点应放在首购后 30—60 天的第二单转化，而不是笼统发券。准时送达率为 {percent(kpi['on_time_delivery_rate'])}，但延迟订单低评分率达到 {percent(late_low)}，约为准时订单的 {late_low / on_time_low:.2f} 倍。建议对高交易量、高延迟的州和商家设置分层 SLA，同时对高价值新客、忠诚顾客和流失风险顾客采用不同触达策略。所有建议都需要用实验验证增量复购和利润，不能把相关性写成因果关系。

## 常见追问

1. **为什么不能直接连接所有表？** 因为一个订单可有多件商品、多次支付和多条评价，直接连接会产生笛卡尔放大；必须先聚合到共同粒度。
2. **为什么用 customer_unique_id？** 它是跨订单稳定标识；customer_id 只对应单次订单，使用后者会把复购顾客误判成新顾客。
3. **为什么要做 90 天可观察窗口？** 样本末端顾客没有足够时间产生第二单，直接归为未复购会造成右删失偏差。
4. **为什么不用 t 检验比较评分？** 评分是 1—5 的有序离散变量且分布偏斜，因此使用 Mann–Whitney U 比较分布，同时仍报告均值差和置信区间便于业务解释。
5. **为什么不能说延迟导致低评分？** 数据不是随机实验，地区、品类、商家和订单复杂度可能同时影响延迟和评分。
6. **项目最大的限制是什么？** 缺少成本、佣金、退款、营销触达和实验数据，无法计算利润或真实策略增量。
"""
    (REPORT_DIR / "interview_guide.md").write_text(interview, encoding="utf-8")

    resume = f"""# 简历项目描述

## 推荐版本

**电商经营分析与复购诊断｜SQL、Python、Power BI**

- 基于 Olist 9 张关系表、{int(kpi['total_orders']):,} 笔订单，分别聚合商品、支付与评价数据，构建一单一行分析模型，并完成主键、孤儿记录、金额守恒及时间逻辑校验。
- 使用 SQL/Python 搭建成交额、客单价、复购率、RFM 与同期群指标体系；识别 {int(kpi['active_customers']):,} 名成交顾客中的 {int(kpi['repeat_customers']):,} 名复购顾客，样本期复购率为 {percent(kpi['repeat_customer_rate'])}。
- 采用 Mann–Whitney U、Spearman 相关及 95% 置信区间评估履约体验；发现延迟订单低评分率 {percent(late_low)}，为准时订单的 {late_low / on_time_low:.2f} 倍，并输出 Power BI 数据模型、DAX 指标与四页经营看板方案。

## 真实性边界

- 不写“提升复购率”或“创造收入”，因为策略尚未在线实施。
- 不把成交额写成利润或平台财务收入。
- 不把物流与评分的相关性写成因果关系。
- 在真正完成 Power BI Desktop 页面前，使用“看板方案”而不是“上线看板”。
"""
    (REPORT_DIR / "resume_bullets.md").write_text(resume, encoding="utf-8")


def main() -> None:
    ensure_directories()
    print("[1/10] Validating source files...")
    file_report = validate_files()
    print("[2/10] Loading analytical tables...")
    tables = load_tables()
    quality = build_quality_report(tables, file_report)
    print("[3/10] Building the order-level analytical model...")
    order_model, _ = build_order_model(tables)
    quality_checks = build_quality_checks(tables, order_model)
    print("[4/10] Calculating business metrics and customer analytics...")
    kpi_table, kpi_values = build_kpis(order_model)
    monthly = build_monthly_metrics(order_model)
    rfm, segment_summary = build_rfm(order_model)
    cohort_tidy, cohort_matrix = build_cohorts(order_model)
    print("[5/10] Testing the delivery-satisfaction relationship...")
    delivery_summary, statistical_tests = build_delivery_analysis(order_model)
    print("[6/10] Building category, seller and state marts...")
    item_detail, category, category_diagnostics, seller, state = build_commercial_marts(tables, order_model)
    print("[7/10] Building right-censoring-aware repurchase diagnostics...")
    customer_base, repurchase_summaries, repurchase_tests = build_repurchase_analysis(
        order_model, item_detail
    )
    repurchase_customer_columns = [
        "customer_unique_id",
        "first_order_id",
        "first_purchase_at",
        "first_purchase_month",
        "first_customer_state",
        "first_primary_category",
        "first_order_value",
        "first_review_score",
        "first_delivery_status",
        "observation_days",
        "eligible_90d",
        "repeat_within_90d",
    ]
    rfm_enriched = rfm.merge(
        customer_base[repurchase_customer_columns],
        on="customer_unique_id",
        how="left",
        validate="one_to_one",
    )

    outputs = {
        "data_quality_summary": quality,
        "data_quality_checks": quality_checks,
        "kpi_summary": kpi_table,
        "monthly_metrics": monthly,
        "rfm_segment_summary": segment_summary,
        "cohort_retention_tidy": cohort_tidy,
        "cohort_retention_matrix": cohort_matrix,
        "delivery_review_summary": delivery_summary,
        "statistical_tests": statistical_tests,
        "category_performance": category,
        "category_growth_quality": category_diagnostics,
        "seller_scorecard": seller,
        "state_performance": state,
        "repurchase_customer_base": customer_base,
        "repurchase_statistical_tests": repurchase_tests,
    }
    outputs.update(repurchase_summaries)
    print("[8/10] Saving Power BI tables, summaries and figures...")
    save_tables(order_model, item_detail, rfm_enriched, outputs)
    create_figures(
        monthly,
        segment_summary,
        cohort_matrix,
        delivery_summary,
        category,
        repurchase_summaries,
        category_diagnostics,
    )
    print("[9/10] Writing findings and portfolio materials...")
    write_findings(
        order_model,
        kpi_values,
        monthly,
        cohort_tidy,
        delivery_summary,
        statistical_tests,
        category,
        category_diagnostics,
        seller,
        state,
        customer_base,
        repurchase_summaries,
        repurchase_tests,
        quality_checks,
    )
    write_portfolio_materials(kpi_values, delivery_summary, customer_base)
    print("[10/10] Verifying output invariants...")
    if not cohort_tidy.loc[cohort_tidy["cohort_index"].eq(0), "retention_rate"].eq(1).all():
        raise AssertionError("Cohort month zero retention must equal 100%.")
    rate_columns = [column for column in outputs["state_performance"].columns if column.endswith("rate")]
    for column in rate_columns:
        valid_values = outputs["state_performance"][column].dropna()
        if not valid_values.between(0, 1).all():
            raise AssertionError(f"{column} contains a value outside [0, 1].")
    print(f"Done. Open {REPORT_DIR / 'findings.md'}")


if __name__ == "__main__":
    main()
