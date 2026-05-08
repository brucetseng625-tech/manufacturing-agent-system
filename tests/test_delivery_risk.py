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
        self.assertIn("evaluated delivery risk with inventory/supplier/capacity data", result["trace"])

    def test_schedule_conflict_is_included_as_delivery_blocker(self):
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")

        result = analyze_delivery_risk("ORD-1002", mock_data_dir)

        self.assertIn("Schedule conflict", " ".join(result["blockers"]))
        self.assertIn("ORD-1001, ORD-1002", " ".join(result["blockers"]))
        self.assertIn("Schedule conflict status: conflict_detected.", " ".join(result.get("details", {}).get("evidence", [])))
        self.assertEqual(result["decision"], "at_risk")
        self.assertEqual(result["confidence"], "Medium")

    def test_unknown_order_returns_error(self):
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")

        result = analyze_delivery_risk("ORD-9999", mock_data_dir)

        self.assertEqual(result, {"error": "Order ORD-9999 not found"})

    def test_delivery_risk_supports_csv_data_dir(self):
        csv_data_dir = os.path.join(os.path.dirname(__file__), "..", "data")

        result = analyze_delivery_risk("ORD-CSV-001", csv_data_dir)

        self.assertEqual(result["decision"], "can_ship_on_time")
        self.assertEqual(result["confidence"], "High")
        self.assertEqual(result["blockers"], ["No critical blockers found in current mock data."])
        self.assertIn("Schedule conflict status: no_conflict.", " ".join(result.get("details", {}).get("evidence", [])))

    def test_delivery_risk_uses_customer_tier_and_penalty(self):
        """VIP customer with high penalty triggers specific escalation."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")

        result = analyze_delivery_risk("ORD-1001", mock_data_dir)

        details = result.get("details", {})
        self.assertEqual(details.get("customer_tier"), "VIP")
        self.assertEqual(details.get("penalty_per_day"), 5000.0)
        self.assertIn("VIP", result["escalation"])

    def test_delivery_risk_uses_expedite_option(self):
        """Expedite option and cost appear in details and next_action."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")

        result = analyze_delivery_risk("ORD-1001", mock_data_dir)

        details = result.get("details", {})
        self.assertEqual(details.get("expedite_option"), "overtime")
        self.assertEqual(details.get("expedite_cost"), 15000.0)
        cost_notes = details.get("cost_notes", [])
        next_action = result.get("next_action", "")
        self.assertTrue(
            any("overtime" in str(cn) or "Expedite" in str(cn) for cn in cost_notes) or "overtime" in next_action,
            f"Expected expedite mention in cost_notes or next_action. cost_notes={cost_notes}, next_action={next_action}"
        )

    def test_delivery_risk_uses_safety_stock_and_supplier_data(self):
        """Material safety stock and supplier lead time affect blocker analysis."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")

        result = analyze_delivery_risk("ORD-1001", mock_data_dir)

        evidence_str = " ".join(result.get("details", {}).get("evidence", []))
        # Should mention supplier lead time and reliability for the shortage material
        self.assertTrue(
            "lead time" in evidence_str.lower() or "reliability" in evidence_str.lower() or "safety stock" in evidence_str.lower(),
            f"Expected supplier/inventory data in evidence, got: {evidence_str}"
        )


if __name__ == "__main__":
    unittest.main()
