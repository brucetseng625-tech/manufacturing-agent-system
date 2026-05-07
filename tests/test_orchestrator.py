
import os
import unittest
from orchestrator import route_query, validate_data_dir, extract_order_ids

class OrchestratorTest(unittest.TestCase):
    def test_route_query_delivery_intent(self):
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = route_query("ORD-1001 能不能準時出？", mock_data_dir)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skill"], "delivery-risk-analysis")
        self.assertEqual(result["data"]["order_id"], "ORD-1001")

    def test_route_query_conflict_intent(self):
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = route_query("檢查 ORD-1001 和 ORD-1002 有沒有排程衝突", mock_data_dir)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skill"], "schedule-conflict-check")

    def test_route_query_validation_failure(self):
        # Create a temp dir with bad data
        import tempfile
        with tempfile.TemporaryDirectory() as bad_dir:
            # orders.csv missing required fields
            with open(os.path.join(bad_dir, "orders.csv"), "w") as f:
                f.write("order_id\nORD-BAD\n")
            
            result = route_query("ORD-BAD 出貨", bad_dir)
            
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["type"], "validation_failed")
            self.assertIn("Missing required field", " ".join(result["details"]))

    def test_extract_order_ids_csv_style(self):
        self.assertEqual(extract_order_ids("ORD-CSV-001 出貨"), ["ORD-CSV-001"])
