
import os
import tempfile
import json
import unittest
from orchestrator import route_query
from skills.supplier_followup_draft import (
    handle_supplier_followup_draft,
    _detect_draft_context,
    _generate_emergency_reorder_draft,
    _generate_alternate_supplier_draft,
    _generate_lead_time_confirmation_draft,
    _generate_material_availability_draft,
)
from skills.material_shortage_recovery import handle_material_shortage_recovery


class SupplierFollowupDraftSkillTest(unittest.TestCase):
    """Tests for the supplier-followup-draft skill core logic."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def test_shortage_order_produces_drafts(self):
        """ORD-1001 has shortage — should produce follow-up drafts."""
        result = handle_supplier_followup_draft(["ORD-1001"], self.mock_data_dir)
        self.assertNotIn("error", result)
        drafts = result.get("details", {}).get("drafts", [])
        self.assertGreater(len(drafts), 0)

    def test_drafts_have_required_fields(self):
        """Each draft must contain all required fields."""
        result = handle_supplier_followup_draft(["ORD-1001"], self.mock_data_dir)
        drafts = result.get("details", {}).get("drafts", [])
        required = [
            "draft_type", "label", "target_supplier", "subject",
            "key_asks", "urgency_level", "urgency_reason", "recommended",
        ]
        for draft in drafts:
            for field in required:
                self.assertIn(field, draft, f"Missing field: {field} in {draft['draft_type']}")

    def test_draft_summary_structure(self):
        """Draft summary should contain counts and top recommendation."""
        result = handle_supplier_followup_draft(["ORD-1001"], self.mock_data_dir)
        summary = result.get("details", {}).get("draft_summary", {})
        self.assertIn("total_drafts", summary)
        self.assertIn("recommended_count", summary)
        self.assertIn("top_recommendation", summary)
        self.assertIn("top_urgency", summary)
        self.assertIn("target_suppliers", summary)

    def test_reply_draft_included(self):
        """Top draft's reply_draft should be accessible at top level."""
        result = handle_supplier_followup_draft(["ORD-1001"], self.mock_data_dir)
        reply = result.get("reply_draft")
        self.assertIsNotNone(reply)
        self.assertIsInstance(reply, str)
        self.assertGreater(len(reply), 0)

    def test_no_shortage_order_safe_fallback(self):
        """Order without shortage should return no_followup_needed."""
        result = handle_supplier_followup_draft(["ORD-1002"], self.mock_data_dir)
        self.assertNotIn("error", result)
        self.assertEqual(result["decision"], "no_followup_needed")
        drafts = result.get("details", {}).get("drafts", [])
        self.assertEqual(len(drafts), 0)

    def test_no_order_id_returns_error(self):
        result = handle_supplier_followup_draft([], self.mock_data_dir)
        self.assertIn("error", result)

    def test_nonexistent_order_returns_error(self):
        result = handle_supplier_followup_draft(["ORD-9999"], self.mock_data_dir)
        self.assertIn("error", result)

    def test_urgency_ranking(self):
        """Drafts should be sorted by urgency level."""
        result = handle_supplier_followup_draft(["ORD-1001"], self.mock_data_dir)
        drafts = result.get("details", {}).get("drafts", [])
        urgency_priority = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        for i in range(len(drafts) - 1):
            u1 = urgency_priority.get(drafts[i]["urgency_level"], 0)
            u2 = urgency_priority.get(drafts[i + 1]["urgency_level"], 0)
            self.assertGreaterEqual(u1, u2)

    def test_emergency_reorder_has_critical_urgency(self):
        """Emergency reorder draft should have critical urgency."""
        result = handle_supplier_followup_draft(["ORD-1001"], self.mock_data_dir)
        drafts = result.get("details", {}).get("drafts", [])
        emergency = next((d for d in drafts if d["draft_type"] == "emergency_reorder"), None)
        self.assertIsNotNone(emergency)
        self.assertEqual(emergency["urgency_level"], "critical")

    def test_reuses_shortage_context(self):
        """Follow-up draft should inherit context from shortage analysis."""
        result = handle_supplier_followup_draft(["ORD-1001"], self.mock_data_dir)
        shortage_result = handle_material_shortage_recovery(["ORD-1001"], self.mock_data_dir)
        # Both should reference the same shortage material
        shortage_materials = shortage_result.get("details", {}).get("shortages", [])
        if shortage_materials:
            mat_name = shortage_materials[0].get("material")
            drafts = result.get("details", {}).get("drafts", [])
            # At least one draft should mention this material
            found = any(
                mat_name in d.get("subject", "") or mat_name in d.get("context", {}).get("material", "")
                for d in drafts
            )
            self.assertTrue(found)

    def test_blockers_show_correct_shortage_quantity(self):
        result = handle_supplier_followup_draft(["ORD-1001"], self.mock_data_dir)
        blockers = result.get("blockers", [])
        self.assertTrue(any("shortage: 30 units" in blocker for blocker in blockers))


class SupplierFollowupRoutingTest(unittest.TestCase):
    """Tests for skill routing in the orchestrator."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def test_exact_keyword_routes_to_followup(self):
        result = route_query("ORD-1001 供應商跟進", self.mock_data_dir)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skill"], "supplier-followup-draft")

    def test_english_exact_keyword(self):
        result = route_query("ORD-1001 supplier followup", self.mock_data_dir)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skill"], "supplier-followup-draft")

    def test_followup_draft_keyword(self):
        result = route_query("ORD-1001 follow-up draft", self.mock_data_dir)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skill"], "supplier-followup-draft")

    def test_no_collision_with_sales_response(self):
        """Follow-up keywords should not route to sales-response-draft."""
        result = route_query("ORD-1001 供應商跟進", self.mock_data_dir)
        self.assertNotEqual(result["skill"], "sales-response-draft")

    def test_no_collision_with_quote_comparison(self):
        """Follow-up keywords should not route to quote-comparison-summary."""
        result = route_query("ORD-1001 供應商跟進", self.mock_data_dir)
        self.assertNotEqual(result["skill"], "quote-comparison-summary")

    def test_no_collision_with_shortage_recovery(self):
        result = route_query("ORD-1001 供應商跟進", self.mock_data_dir)
        self.assertNotEqual(result["skill"], "material-shortage-recovery")

    def test_requires_order_id(self):
        result = route_query("供應商跟進", self.mock_data_dir)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["type"], "missing_order_id")


class SupplierFollowupSchemaTest(unittest.TestCase):
    """Tests for unified schema compliance."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def test_has_standardized_fields(self):
        result = handle_supplier_followup_draft(["ORD-1001"], self.mock_data_dir)
        for field in ["skill", "order_id", "decision", "confidence", "blockers",
                      "owner", "eta", "next_action", "trace", "details"]:
            self.assertIn(field, result, f"Missing field: {field}")

    def test_skill_identifier(self):
        result = handle_supplier_followup_draft(["ORD-1001"], self.mock_data_dir)
        self.assertEqual(result["skill"], "supplier-followup-draft")

    def test_details_contain_draft_data(self):
        result = handle_supplier_followup_draft(["ORD-1001"], self.mock_data_dir)
        details = result.get("details", {})
        self.assertIn("drafts", details)
        self.assertIn("draft_summary", details)

    def test_trace_not_empty(self):
        result = handle_supplier_followup_draft(["ORD-1001"], self.mock_data_dir)
        self.assertGreater(len(result.get("trace", [])), 0)


class SupplierFollowupCLITest(unittest.TestCase):
    """Tests for CLI integration."""
    import subprocess

    def test_cli_supplier_followup(self):
        result = self.subprocess.run(
            ["python3", "run_agent.py", "ORD-1001", "供應商跟進"],
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), "..")
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("SUPPLIER FOLLOW-UP DRAFT", result.stdout)

    def test_cli_shows_drafts(self):
        result = self.subprocess.run(
            ["python3", "run_agent.py", "ORD-1001", "supplier", "followup"],
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), "..")
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Drafts generated:", result.stdout)


class SupplierFollowupHelperTest(unittest.TestCase):
    """Tests for helper functions."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def test_detect_draft_context_with_shortage(self):
        from data_source import load_data
        orders = load_data(self.mock_data_dir, "orders.json")
        materials = load_data(self.mock_data_dir, "materials.json")
        order = orders[0]
        context = _detect_draft_context(order["order_id"], order, materials, None)
        self.assertTrue(context["has_shortage"])
        self.assertGreater(len(context["shortage_materials"]), 0)

    def test_detect_draft_context_no_shortage(self):
        from data_source import load_data
        orders = load_data(self.mock_data_dir, "orders.json")
        materials = load_data(self.mock_data_dir, "materials.json")
        # ORD-1002 has no materials in mock_data
        order = orders[1] if len(orders) > 1 else orders[0]
        context = _detect_draft_context("ORD-1002", order, materials, None)
        self.assertFalse(context["has_shortage"])

    def test_generate_emergency_reorder_draft(self):
        order = {"order_id": "ORD-1001", "due_date": "2026-05-15", "customer": "Test"}
        shortage = {
            "material": "Steel", "shortage_qty": 50, "required_qty": 100,
            "lead_time_days": 14, "supplier_reliability": 0.7, "unit_cost": 45.0,
        }
        draft = _generate_emergency_reorder_draft(order, shortage, "ORD-1001", 6)
        self.assertEqual(draft["draft_type"], "emergency_reorder")
        self.assertEqual(draft["urgency_level"], "critical")
        self.assertIn("Steel", draft["subject"])
        self.assertIn("Dear", draft["reply_draft"])

    def test_generate_lead_time_confirmation(self):
        order = {"order_id": "ORD-1001", "due_date": "2026-05-15", "customer": "Test"}
        shortage = {
            "material": "Steel", "shortage_qty": 50, "required_qty": 100,
            "lead_time_days": 14, "supplier_reliability": 0.7, "unit_cost": 45.0,
        }
        draft = _generate_lead_time_confirmation_draft(order, shortage, "ORD-1001", 6)
        self.assertEqual(draft["draft_type"], "lead_time_confirmation")
        self.assertIn("confirm", draft["reply_draft"].lower())

    def test_generate_material_availability(self):
        order = {"order_id": "ORD-1001", "due_date": "2026-05-15", "customer": "Test"}
        shortage = {
            "material": "Steel", "shortage_qty": 50, "required_qty": 100,
            "lead_time_days": 14, "supplier_reliability": 0.7, "unit_cost": 45.0,
            "available_qty": 50, "safety_stock": 30, "below_safety_stock": False,
        }
        draft = _generate_material_availability_draft(order, shortage, "ORD-1001", 6)
        self.assertEqual(draft["draft_type"], "material_availability")
        self.assertIn("Required: 100 units", draft["reply_draft"])
        self.assertIn("Available: 50 units", draft["reply_draft"])


class SupplierFollowupServerTest(unittest.TestCase):
    """Tests for server /run endpoint with supplier-followup-draft."""

    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from http.server import HTTPServer
        import threading
        import time
        from server import AgentHandler
        cls.server = HTTPServer(("127.0.0.1", 0), AgentHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=1)

    def _post(self, payload):
        import json
        import urllib.request
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/run",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())

    def test_run_supplier_followup(self):
        result = self._post({
            "query": "ORD-1001 供應商跟進",
        })
        self.assertEqual(result["status"], "success")
        self.assertIn("supplier_followup_draft", result.get("intent", ""))
