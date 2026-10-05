from __future__ import annotations

import math
import unittest

import pandas as pd

from src.run_analysis import (
    build_cohorts,
    build_commercial_marts,
    build_delivery_analysis,
    build_kpis,
    build_monthly_metrics,
    build_order_model,
    build_quality_checks,
    build_quality_report,
    build_repurchase_analysis,
    build_rfm,
    load_tables,
    validate_files,
)


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.file_report = validate_files()
        cls.tables = load_tables()
        cls.order_model, _ = build_order_model(cls.tables)
        (
            cls.item_detail,
            cls.category,
            cls.category_diagnostics,
            cls.seller,
            cls.state,
        ) = build_commercial_marts(cls.tables, cls.order_model)
        cls.customer_base, cls.repurchase_summaries, cls.repurchase_tests = build_repurchase_analysis(
            cls.order_model, cls.item_detail
        )
        cls.rfm, cls.segment_summary = build_rfm(cls.order_model)
        cls.cohort_tidy, cls.cohort_matrix = build_cohorts(cls.order_model)
        cls.delivery_summary, cls.delivery_tests = build_delivery_analysis(cls.order_model)

    def test_required_files_pass_schema_validation(self) -> None:
        self.assertEqual(len(self.file_report), 9)
        self.assertTrue(self.file_report["schema_check"].eq("PASS").all())

    def test_order_model_is_unique_at_order_grain(self) -> None:
        self.assertEqual(len(self.order_model), self.order_model["order_id"].nunique())
        self.assertEqual(len(self.order_model), len(self.tables["orders"]))

    def test_item_revenue_is_conserved(self) -> None:
        raw_total = float(self.tables["items"]["price"].sum())
        modeled_total = float(self.order_model["item_revenue"].sum())
        self.assertTrue(math.isclose(raw_total, modeled_total, rel_tol=1e-12))

    def test_freight_and_child_record_counts_are_conserved(self) -> None:
        raw_freight = float(self.tables["items"]["freight_value"].sum())
        modeled_freight = float(self.order_model["freight_value"].sum())
        self.assertTrue(math.isclose(raw_freight, modeled_freight, rel_tol=1e-12))
        self.assertEqual(int(self.order_model["item_count"].sum()), len(self.tables["items"]))
        self.assertEqual(
            int(self.order_model["payment_records"].sum()), len(self.tables["payments"])
        )
        self.assertEqual(
            int(self.order_model["review_records"].fillna(0).sum()),
            len(self.tables["reviews"]),
        )

    def test_core_rates_are_valid(self) -> None:
        _, values = build_kpis(self.order_model)
        for metric in (
            "repeat_customer_rate",
            "cancellation_rate",
            "unavailable_rate",
            "on_time_delivery_rate",
            "low_review_rate",
        ):
            self.assertGreaterEqual(values[metric], 0)
            self.assertLessEqual(values[metric], 1)

    def test_verified_kpi_baselines_and_review_denominator(self) -> None:
        _, values = build_kpis(self.order_model)
        self.assertEqual(values["total_orders"], 99_441)
        self.assertEqual(values["delivered_orders"], 96_478)
        self.assertTrue(math.isclose(values["delivered_gmv"], 13_221_498.11, abs_tol=0.01))
        self.assertTrue(math.isclose(values["average_order_value"], 137.0415857501192))

        delivered = self.order_model[self.order_model["is_delivered"]]
        reviewed = delivered[delivered["review_score"].notna()]
        expected_low_review_rate = reviewed["review_score"].le(2).mean()
        self.assertEqual(len(reviewed), 95_832)
        self.assertEqual(int(reviewed["review_score"].le(2).sum()), 12_237)
        self.assertTrue(math.isclose(values["low_review_rate"], expected_low_review_rate))

    def test_complete_month_window_and_monthly_benchmarks(self) -> None:
        monthly = build_monthly_metrics(self.order_model)
        core = monthly[monthly["is_complete_core_month"]].copy()
        self.assertEqual(len(core), 20)
        self.assertEqual(core["purchase_month"].min(), pd.Timestamp("2017-01-01"))
        self.assertEqual(core["purchase_month"].max(), pd.Timestamp("2018-08-01"))
        expected_months = pd.date_range("2017-01-01", "2018-08-01", freq="MS")
        self.assertTrue(core["purchase_month"].reset_index(drop=True).equals(pd.Series(expected_months)))
        self.assertTrue(pd.isna(core.iloc[0]["mom_gmv_growth"]))
        self.assertTrue(core.iloc[1:]["mom_gmv_growth"].notna().all())
        self.assertTrue(monthly.loc[~monthly["is_complete_core_month"], "mom_gmv_growth"].isna().all())

        peak = core.loc[core["delivered_gmv"].idxmax()]
        self.assertEqual(peak["purchase_month"], pd.Timestamp("2017-11-01"))
        self.assertTrue(math.isclose(float(peak["delivered_gmv"]), 987_765.37, abs_tol=0.01))

        first_period = core[
            core["purchase_month"].dt.year.eq(2017) & core["purchase_month"].dt.month.le(8)
        ]["delivered_gmv"].sum()
        second_period = core[
            core["purchase_month"].dt.year.eq(2018) & core["purchase_month"].dt.month.le(8)
        ]["delivered_gmv"].sum()
        self.assertTrue(math.isclose(second_period / first_period - 1, 1.4113014544161704))

    def test_cohort_month_zero_retention_is_one(self) -> None:
        month_zero = self.cohort_tidy[self.cohort_tidy["cohort_index"].eq(0)]
        self.assertEqual(len(month_zero), 23)
        self.assertEqual(int(month_zero["cohort_size"].sum()), 93_358)
        self.assertTrue((month_zero["active_customers"] == month_zero["cohort_size"]).all())
        self.assertEqual(month_zero["cohort_month"].min(), "2016-09")
        self.assertEqual(month_zero["cohort_month"].max(), "2018-08")
        month_zero = month_zero["retention_rate"]
        self.assertTrue(month_zero.eq(1).all())

    def test_cohort_activity_is_unique_and_indices_are_valid(self) -> None:
        delivered = self.order_model[self.order_model["is_delivered"]].copy()
        delivered["order_month"] = delivered["order_purchase_timestamp"].dt.to_period("M")
        activity = delivered[["customer_unique_id", "order_month"]].drop_duplicates()
        first_month = activity.groupby("customer_unique_id")["order_month"].min()
        assigned_cohorts = activity[["customer_unique_id"]].drop_duplicates().merge(
            first_month.rename("cohort_month"),
            on="customer_unique_id",
            how="left",
            validate="one_to_one",
        )
        activity = activity.merge(
            first_month.rename("cohort_month"),
            on="customer_unique_id",
            how="left",
            validate="many_to_one",
        )
        cohort_index = (
            (activity["order_month"].dt.year - activity["cohort_month"].dt.year) * 12
            + activity["order_month"].dt.month
            - activity["cohort_month"].dt.month
        )

        self.assertFalse(activity.duplicated(["customer_unique_id", "order_month"]).any())
        self.assertFalse(assigned_cohorts["customer_unique_id"].duplicated().any())
        self.assertEqual(len(assigned_cohorts), 93_358)
        self.assertTrue(cohort_index.ge(0).all())

    def test_cohort_zero_activity_and_future_months_are_distinct(self) -> None:
        october_m1 = self.cohort_tidy[
            self.cohort_tidy["cohort_month"].eq("2016-10")
            & self.cohort_tidy["cohort_index"].eq(1)
        ].iloc[0]
        self.assertEqual(int(october_m1["active_customers"]), 0)
        self.assertEqual(float(october_m1["retention_rate"]), 0)
        self.assertEqual(float(self.cohort_matrix.loc["2016-10", 1]), 0)

        august_future = self.cohort_tidy[
            self.cohort_tidy["cohort_month"].eq("2018-08")
            & self.cohort_tidy["cohort_index"].eq(1)
        ]
        self.assertTrue(august_future.empty)
        self.assertTrue(pd.isna(self.cohort_matrix.loc["2018-08", 1]))
        self.assertFalse(
            self.cohort_tidy[
                self.cohort_tidy["cohort_month"].eq("2018-07")
                & self.cohort_tidy["cohort_index"].eq(1)
            ].empty
        )

    def test_cohort_baselines_and_matrix_reconciliation(self) -> None:
        self.assertFalse(self.cohort_tidy.duplicated(["cohort_month", "cohort_index"]).any())
        self.assertTrue(self.cohort_tidy["cohort_index"].ge(0).all())
        self.assertTrue(self.cohort_tidy["retention_rate"].between(0, 1).all())

        month_one = self.cohort_tidy[self.cohort_tidy["cohort_index"].eq(1)]
        self.assertEqual(len(month_one), 22)
        self.assertEqual(int(month_one["active_customers"].sum()), 421)
        self.assertEqual(int(month_one["cohort_size"].sum()), 87_214)
        self.assertTrue(math.isclose(month_one["active_customers"].sum() / month_one["cohort_size"].sum(), 0.004827206641135597))

        month_two = self.cohort_tidy[self.cohort_tidy["cohort_index"].eq(2)]
        self.assertEqual(len(month_two), 21)
        self.assertEqual(int(month_two["active_customers"].sum()), 273)
        self.assertEqual(int(month_two["cohort_size"].sum()), 81_265)
        self.assertTrue(math.isclose(month_two["active_customers"].sum() / month_two["cohort_size"].sum(), 0.0033593798068048976))

        for row in self.cohort_tidy.itertuples(index=False):
            self.assertTrue(
                math.isclose(
                    float(row.retention_rate),
                    float(self.cohort_matrix.loc[row.cohort_month, row.cohort_index]),
                )
            )

    def test_delivery_review_sample_funnel_and_order_grain(self) -> None:
        delivered = self.order_model[self.order_model["is_delivered"]]
        delivery_known = delivered[delivered["is_late"].notna()]
        reviewed = delivered[delivered["review_score"].notna()]
        analysis_sample = delivered[
            delivered["is_late"].notna() & delivered["review_score"].notna()
        ]

        self.assertEqual(len(delivered), 96_478)
        self.assertEqual(len(delivery_known), 96_470)
        self.assertEqual(len(reviewed), 95_832)
        self.assertEqual(len(analysis_sample), 95_824)
        self.assertEqual(analysis_sample["order_id"].nunique(), 95_824)
        self.assertEqual(int(delivered["is_late"].isna().sum()), 8)
        self.assertEqual(int(delivered["review_score"].isna().sum()), 646)
        self.assertEqual(
            int((delivered["is_late"].isna() & delivered["review_score"].isna()).sum()),
            0,
        )

    def test_delivery_review_group_baselines(self) -> None:
        summary = self.delivery_summary.set_index("delivery_status")
        late = summary.loc["Late"]
        on_time = summary.loc["On time"]
        analysis_sample = self.order_model[
            self.order_model["is_delivered"]
            & self.order_model["is_late"].notna()
            & self.order_model["review_score"].notna()
        ]

        self.assertEqual(int(late["orders"]), 7_661)
        self.assertEqual(int(on_time["orders"]), 88_163)
        self.assertTrue(math.isclose(float(late["average_review_score"]), 2.566505678109907))
        self.assertTrue(math.isclose(float(on_time["average_review_score"]), 4.294292012144172))
        self.assertTrue(math.isclose(float(late["low_review_rate"]), 0.5398773006134969))
        self.assertTrue(math.isclose(float(on_time["low_review_rate"]), 0.09187527647652644))
        self.assertTrue(math.isclose(float(late["average_delivery_days"]), 31.378792643233886))
        self.assertTrue(math.isclose(float(on_time["average_delivery_days"]), 10.877732901016469))
        self.assertTrue(math.isclose(float(late["average_delta_days"]), 9.445928825109863))
        self.assertTrue(math.isclose(float(on_time["average_delta_days"]), -13.010580821519147))

        late_scores = analysis_sample.loc[analysis_sample["is_late"].astype(bool), "review_score"]
        on_time_scores = analysis_sample.loc[~analysis_sample["is_late"].astype(bool), "review_score"]
        self.assertEqual(float(late_scores.median()), 2)
        self.assertEqual(float(on_time_scores.median()), 5)
        self.assertEqual(int(late_scores.le(2).sum()), 4_136)
        self.assertEqual(int(on_time_scores.le(2).sum()), 8_100)
        self.assertTrue(self.delivery_summary["low_review_rate"].between(0, 1).all())

    def test_delivery_review_statistical_baselines(self) -> None:
        tests = self.delivery_tests.set_index("analysis")
        difference = tests.loc["Late minus on-time mean review score"]
        mann = tests.loc["Mann-Whitney U: late vs on-time review score"]
        spearman = tests.loc["Spearman: delivery delta days vs review score"]

        self.assertTrue(math.isclose(float(difference["estimate"]), -1.7277863340342652))
        self.assertTrue(math.isclose(float(difference["ci_95_low"]), -1.7656776527827003))
        self.assertTrue(math.isclose(float(difference["ci_95_high"]), -1.68989501528583))
        self.assertLess(float(difference["ci_95_high"]), 0)
        self.assertLessEqual(float(difference["ci_95_low"]), float(difference["estimate"]))
        self.assertGreaterEqual(float(difference["ci_95_high"]), float(difference["estimate"]))

        self.assertTrue(math.isclose(float(mann["statistic"]), 150_680_825.5))
        self.assertLess(float(mann["p_value"]), 1e-300)
        self.assertTrue(math.isclose(float(spearman["estimate"]), -0.17566941207881423))
        self.assertLess(float(spearman["p_value"]), 1e-300)

    def test_no_blocking_data_quality_failures(self) -> None:
        checks = build_quality_checks(self.tables, self.order_model)
        blocking = checks[checks["severity"].eq("ERROR")]
        self.assertTrue(blocking["failed_rows"].eq(0).all())

    def test_review_composite_business_key_is_unique(self) -> None:
        quality = build_quality_report(self.tables, self.file_report)
        review_row = quality.loc[quality["table"].eq("reviews")].iloc[0]
        self.assertEqual(int(review_row["duplicate_business_keys"]), 0)

    def test_expected_timestamp_warnings_are_stable(self) -> None:
        checks = build_quality_checks(self.tables, self.order_model).set_index("check_name")
        self.assertEqual(int(checks.loc["carrier_before_purchase", "failed_rows"]), 166)
        self.assertEqual(int(checks.loc["delivery_before_carrier", "failed_rows"]), 23)

    def test_repurchase_base_is_unique_and_right_censoring_aware(self) -> None:
        self.assertFalse(self.customer_base["customer_unique_id"].duplicated().any())
        eligible = self.customer_base[self.customer_base["eligible_90d"]]
        self.assertTrue(eligible["observation_days"].ge(90).all())
        repeat = eligible[eligible["repeat_within_90d"]]
        elapsed_days = (repeat["second_purchase_at"] - repeat["first_purchase_at"]).dt.total_seconds() / 86400
        self.assertTrue(elapsed_days.between(0, 90).all())

    def test_verified_repurchase_baselines(self) -> None:
        eligible = self.customer_base[self.customer_base["eligible_90d"]]
        self.assertEqual(len(self.customer_base), 93_358)
        self.assertEqual(int(self.customer_base["lifetime_orders"].ge(2).sum()), 2_801)
        self.assertTrue(
            math.isclose(self.customer_base["lifetime_orders"].ge(2).mean(), 0.03000278497825575)
        )
        self.assertEqual(len(eligible), 75_563)
        self.assertEqual(int((~self.customer_base["eligible_90d"]).sum()), 17_795)
        self.assertEqual(int(eligible["repeat_within_90d"].sum()), 1_718)
        self.assertTrue(math.isclose(eligible["repeat_within_90d"].mean(), 0.022735995129891613))

    def test_rfm_coverage_and_revenue_are_conserved(self) -> None:
        delivered_gmv = self.order_model.loc[
            self.order_model["is_delivered"], "item_revenue"
        ].sum()
        self.assertEqual(len(self.rfm), 93_358)
        self.assertFalse(self.rfm["customer_unique_id"].duplicated().any())
        self.assertTrue(math.isclose(self.rfm["monetary"].sum(), delivered_gmv, rel_tol=1e-12))
        self.assertTrue(math.isclose(self.segment_summary["customer_share"].sum(), 1.0))
        self.assertTrue(math.isclose(self.segment_summary["revenue_share"].sum(), 1.0))

    def test_repurchase_statistical_test_baselines(self) -> None:
        tests = self.repurchase_tests.set_index("analysis")
        expected = {
            "First delivery status vs 90-day repeat": (75_561, 0.23288608871227717, 0.004339863377853628),
            "First review group vs 90-day repeat": (75_030, 0.7219033341642946, 0.002947241610976627),
            "First order value band vs 90-day repeat": (75_563, 7.200590450382599e-05, 0.017904985213441662),
        }
        for analysis, (customers, p_value, cramers_v) in expected.items():
            row = tests.loc[analysis]
            self.assertEqual(int(row["customers"]), customers)
            self.assertTrue(math.isclose(float(row["p_value"]), p_value))
            self.assertTrue(math.isclose(float(row["cramers_v"]), cramers_v))

    def test_commercial_revenue_is_conserved_for_delivered_orders(self) -> None:
        delivered_total = float(
            self.order_model.loc[self.order_model["is_delivered"], "item_revenue"].sum()
        )
        for frame in (self.category, self.seller, self.state):
            self.assertTrue(
                math.isclose(float(frame["revenue"].sum()), delivered_total, rel_tol=1e-12)
            )

    def test_commercial_dimension_counts_and_sample_thresholds(self) -> None:
        self.assertEqual(len(self.category), 74)
        self.assertEqual(int(self.category["reliable_sample"].sum()), 32)
        self.assertEqual(int(self.category_diagnostics["comparable_sample"].sum()), 28)
        self.assertEqual(int(self.category_diagnostics["growth_quality_risk"].sum()), 24)

        self.assertEqual(len(self.seller), 2_970)
        self.assertEqual(int(self.seller["reliable_sample"].sum()), 627)
        self.assertTrue(self.seller.loc[self.seller["reliable_sample"], "orders"].ge(30).all())
        self.assertTrue(self.seller.loc[~self.seller["reliable_sample"], "orders"].lt(30).all())

        self.assertEqual(len(self.state), 27)
        self.assertEqual(int(self.state["reliable_sample"].sum()), 17)
        self.assertTrue(self.state.loc[self.state["reliable_sample"], "orders"].ge(500).all())
        self.assertTrue(self.state.loc[~self.state["reliable_sample"], "orders"].lt(500).all())

    def test_commercial_low_review_denominators_exclude_missing_scores(self) -> None:
        for frame in (self.category, self.seller, self.state):
            reviewed = frame["reviewed_orders"]
            low = frame["low_review_orders"]
            self.assertTrue(reviewed.le(frame["orders"]).all())
            self.assertTrue(low.le(reviewed).all())
            expected_rate = low / reviewed.where(reviewed.ne(0))
            pd.testing.assert_series_equal(
                frame["low_review_rate"].reset_index(drop=True),
                expected_rate.astype(float).reset_index(drop=True),
                check_names=False,
            )

        delivered_reviewed = self.order_model[
            self.order_model["is_delivered"] & self.order_model["review_score"].notna()
        ]
        self.assertEqual(int(self.state["reviewed_orders"].sum()), 95_832)
        self.assertEqual(int(self.state["low_review_orders"].sum()), 12_237)
        self.assertEqual(len(delivered_reviewed), 95_832)
        self.assertEqual(int(delivered_reviewed["review_score"].le(2).sum()), 12_237)

    def test_verified_seller_state_and_category_watchlists(self) -> None:
        seller_watchlist = self.seller[self.seller["reliable_sample"]].sort_values(
            ["low_review_rate", "late_delivery_rate", "orders"],
            ascending=[False, False, False],
        ).head(5)
        self.assertEqual(
            seller_watchlist["seller_id"].tolist(),
            [
                "1ca7077d890b907f89be8c954a02686a",
                "2eb70248d66e0e3ef83659f71b244378",
                "972d0f9cf61b499a4812cf0bfa3ad3c4",
                "a49928bcdf77c55c6d6e05e09a9b4ca5",
                "54965bbe3e4f07ae045b90b0b8541f52",
            ],
        )
        self.assertEqual(seller_watchlist["reviewed_orders"].tolist(), [107, 184, 79, 96, 69])
        expected_seller_rates = [64 / 107, 87 / 184, 33 / 79, 39 / 96, 28 / 69]
        for actual, expected in zip(seller_watchlist["low_review_rate"], expected_seller_rates):
            self.assertTrue(math.isclose(float(actual), expected))

        state_watchlist = self.state[self.state["reliable_sample"]].sort_values(
            "late_delivery_rate", ascending=False
        ).head(5)
        self.assertEqual(state_watchlist["customer_state"].tolist(), ["MA", "CE", "BA", "RJ", "PA"])

        risk_categories = self.category_diagnostics[
            self.category_diagnostics["growth_quality_risk"]
        ].head(5)
        self.assertEqual(
            risk_categories["category"].tolist(),
            ["baby", "stationery", "electronics", "watches_gifts", "health_beauty"],
        )

    def test_repurchase_and_commercial_rates_are_valid(self) -> None:
        for summary in self.repurchase_summaries.values():
            self.assertTrue(summary["repeat_90d_rate"].between(0, 1).all())
        for frame, columns in (
            (self.category, ["late_delivery_rate", "freight_to_revenue_rate"]),
            (self.seller, ["low_review_rate", "late_delivery_rate", "freight_to_revenue_rate"]),
            (self.state, ["low_review_rate", "late_delivery_rate", "freight_to_revenue_rate"]),
        ):
            for column in columns:
                self.assertTrue(frame[column].dropna().ge(0).all())
                if column != "freight_to_revenue_rate":
                    self.assertTrue(frame[column].dropna().le(1).all())


if __name__ == "__main__":
    unittest.main()
