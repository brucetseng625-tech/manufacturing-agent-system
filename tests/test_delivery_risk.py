import os
import unittest

from skills.delivery_risk import analyze_delivery_risk


class DeliveryRiskTest(unittest.TestCase):
    def test_urgent_order_cannot_ship_on_time(self):
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")

        result = analyze_delivery_risk("ORD-1001", mock_data_dir)

        self.assertEqual(result["decision"], "cannot_ship_on_time")
        self.assertEqual(result["confidence"], "High")
        self.assertIn("Coating Fluid X", " ".join(result["blockers"]))
        self.assertIn("CNC-02", " ".join(result["blockers"]))
        self.assertIn("Quality Check", " ".join(result["blockers"]))
        self.assertIn("checked schedule conflicts", result["trace"])

    def test_schedule_conflict_is_included_as_delivery_blocker(self):
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")

        result = analyze_delivery_risk("ORD-1002", mock_data_dir)

        self.assertIn("Schedule conflict", " ".join(result["blockers"]))
        self.assertIn("ORD-1001, ORD-1002", " ".join(result["blockers"]))
        self.assertIn("Schedule conflict status: conflict_detected.", result["evidence"])
        self.assertEqual(result["decision"], "at_risk")
        self.assertEqual(result["confidence"], "Medium")

    def test_unknown_order_returns_error(self):
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")

        result = analyze_delivery_risk("ORD-9999", mock_data_dir)

        self.assertEqual(result, {"error": "Order ORD-9999 not found"})


if __name__ == "__main__":
    unittest.main()
