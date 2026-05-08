import os
import unittest

from orchestrator import route_query
from skills.registry import get_registry
from skills.sales_response_draft import handle_sales_response_draft


class SalesResponseDraftTest(unittest.TestCase):
    def test_registry_routing_keywords(self):
        registry = get_registry()

        skill = registry.match_skill("請幫我寫 ORD-1001 的客戶回覆草稿", ["ORD-1001"])
        self.assertIsNotNone(skill)
        self.assertEqual(skill["name"], "sales-response-draft")

    def test_skill_requires_order_id(self):
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")

        result = route_query("請幫我寫客戶回覆草稿", mock_data_dir)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["type"], "missing_order_id")

    def test_skill_generates_draft_for_risky_order(self):
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")

        result = route_query("請幫我寫 ORD-1001 的客戶回覆草稿", mock_data_dir)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["intent"], "sales_response_draft")
        self.assertEqual(result["skill"], "sales-response-draft")
        self.assertEqual(result["data"]["details"]["shipment_status"], "recovery_in_progress")
        self.assertIn("may be impacted", result["data"]["reply_draft"])
        self.assertIn("generated sales response draft", result["data"]["trace"])

    def test_skill_generates_draft_for_on_track_order(self):
        csv_data_dir = os.path.join(os.path.dirname(__file__), "..", "data")

        result = handle_sales_response_draft(["ORD-CSV-001"], csv_data_dir)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["details"]["shipment_status"], "on_track")
        self.assertIn("remain on schedule", result["reply_draft"])
        self.assertEqual(result["blockers"], [])


if __name__ == "__main__":
    unittest.main()
