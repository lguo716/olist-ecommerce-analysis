from __future__ import annotations

import math
import unittest

from src.inspect_powerbi_inputs import INPUT_SPECS, build_preflight_checks, load_inputs


class PowerBIInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frames = load_inputs()
        cls.checks = build_preflight_checks(cls.frames)

    def test_all_eleven_inputs_are_present_and_complete(self) -> None:
        self.assertEqual(len(INPUT_SPECS), 11)
        self.assertEqual(set(self.frames), set(INPUT_SPECS))
        self.assertTrue(self.checks["status"].eq("PASS").all())

    def test_powerbi_fact_and_customer_grains_are_unique(self) -> None:
        orders = self.frames["powerbi_orders"]
        items = self.frames["powerbi_order_items"]
        customers = self.frames["powerbi_customers"]
        self.assertFalse(orders["order_id"].duplicated().any())
        self.assertFalse(items.duplicated(["order_id", "order_item_id"]).any())
        self.assertFalse(customers["customer_unique_id"].duplicated().any())

    def test_dashboard_kpi_baselines(self) -> None:
        orders = self.frames["powerbi_orders"]
        delivered = orders[orders["order_status"].eq("delivered")]
        reviewed = delivered[delivered["review_score"].notna()]
        known_delivery = delivered[delivered["is_late"].notna()]

        self.assertEqual(len(orders), 99_441)
        self.assertEqual(len(delivered), 96_478)
        self.assertTrue(math.isclose(delivered["item_revenue"].sum(), 13_221_498.11, abs_tol=0.01))
        self.assertEqual(delivered["customer_unique_id"].nunique(), 93_358)
        self.assertEqual(delivered.groupby("customer_unique_id")["order_id"].nunique().ge(2).sum(), 2_801)
        self.assertEqual(len(known_delivery), 96_470)
        self.assertEqual(int(known_delivery["is_late"].eq(False).sum()), 88_644)
        self.assertEqual(len(reviewed), 95_832)
        self.assertEqual(int(reviewed["review_score"].le(2).sum()), 12_237)

    def test_diagnostic_tables_keep_review_denominators(self) -> None:
        required = {"reviewed_orders", "low_review_orders", "low_review_rate"}
        for table_name in ("category_performance", "seller_scorecard", "state_performance"):
            self.assertTrue(required.issubset(self.frames[table_name].columns))

    def test_all_cohort_month_zero_cells_are_one(self) -> None:
        cohort = self.frames["cohort_retention_tidy"]
        month_zero = cohort[cohort["cohort_index"].eq(0)]
        self.assertEqual(len(month_zero), 23)
        self.assertTrue(month_zero["retention_rate"].eq(1).all())


if __name__ == "__main__":
    unittest.main()
