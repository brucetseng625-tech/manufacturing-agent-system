
import os
import tempfile
import unittest
from orchestrator import route_query, validate_data_dir, extract_order_ids

class OrchestratorTest(unittest.TestCase):
    def test_route_query_delivery_intent(self):
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = route_query("ORD-1001 能不能準時出？", mock_data_dir)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["intent"], "delivery_risk_analysis")
        self.assertEqual(result["skill"], "delivery-risk-analysis")
        self.assertEqual(result["order_ids"], ["ORD-1001"])
        self.assertEqual(result["data"]["order_id"], "ORD-1001")
        # Check standardized fields
        self.assertIn("decision", result["data"])
        self.assertIn("confidence", result["data"])
        self.assertIn("blockers", result["data"])
        self.assertIn("owner", result["data"])
        self.assertIn("eta", result["data"])

    def test_route_query_conflict_intent(self):
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = route_query("檢查 ORD-1001 和 ORD-1002 有沒有排程衝突", mock_data_dir)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["intent"], "schedule_conflict_check")
        self.assertEqual(result["skill"], "schedule-conflict-check")
        self.assertEqual(result["order_ids"], ["ORD-1001", "ORD-1002"])

    def test_route_query_validation_failure(self):
        # Create a temp dir with bad data
        with tempfile.TemporaryDirectory() as bad_dir:
            # orders.csv missing required fields
            with open(os.path.join(bad_dir, "orders.csv"), "w") as f:
                f.write("order_id\nORD-BAD\n")
            
            result = route_query("ORD-BAD 出貨", bad_dir)
            
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["type"], "validation_failed")
            self.assertEqual(result["order_ids"], ["ORD-BAD"])
            self.assertIn("Missing required field", " ".join(result["details"]))

    def test_extract_order_ids_csv_style(self):
        self.assertEqual(extract_order_ids("ORD-CSV-001 出貨"), ["ORD-CSV-001"])

    def test_route_query_unknown_intent(self):
        """Unknown intent returns unknown_intent error."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = route_query("幫我查天氣", mock_data_dir)
        
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["type"], "unknown_intent")
        self.assertEqual(result["order_ids"], [])

    def test_route_query_missing_order_id(self):
        """Query with delivery keywords but no order ID returns missing_order_id."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = route_query("準時出貨", mock_data_dir)
        
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["type"], "missing_order_id")
        self.assertEqual(result["order_ids"], [])

    def test_route_query_multi_order_triggers_conflict(self):
        """Multiple order IDs auto-route to schedule_conflict_check."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = route_query("ORD-1001 和 ORD-1002", mock_data_dir)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["intent"], "schedule_conflict_check")

    def test_unknown_intent_skips_data_validation(self):
        """Unknown queries should not fail because unrelated datasets are invalid."""
        with tempfile.TemporaryDirectory() as bad_dir:
            with open(os.path.join(bad_dir, "orders.csv"), "w") as f:
                f.write("order_id\nORD-BAD\n")

            result = route_query("幫我查天氣", bad_dir)

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["type"], "unknown_intent")

    def test_validation_is_scoped_to_matched_skill(self):
        """A schedule query should ignore unrelated invalid material data."""
        with tempfile.TemporaryDirectory() as data_dir:
            with open(os.path.join(data_dir, "orders.csv"), "w") as f:
                f.write(
                    "order_id,customer,product,quantity,due_date,priority\n"
                    "ORD-A,Customer A,Part A,1,2026-05-15,High\n"
                    "ORD-B,Customer B,Part B,1,2026-05-16,Low\n"
                )
            with open(os.path.join(data_dir, "schedule.csv"), "w") as f:
                f.write(
                    "order_id,machine_id,start,end\n"
                    "ORD-A,CNC-01,2026-05-14T08:00:00,2026-05-14T10:00:00\n"
                    "ORD-B,CNC-01,2026-05-14T09:00:00,2026-05-14T11:00:00\n"
                )
            with open(os.path.join(data_dir, "materials.csv"), "w") as f:
                f.write("order_id,material\nORD-A,Steel\n")

            result = route_query("檢查 ORD-A 和 ORD-B 有沒有排程衝突", data_dir)

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["intent"], "schedule_conflict_check")
