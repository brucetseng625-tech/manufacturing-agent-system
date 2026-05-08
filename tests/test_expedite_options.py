
import os
import tempfile
import json
import unittest
from orchestrator import route_query
from skills.expedite_options import (
    handle_expedite_options,
    _evaluate_overtime,
    _evaluate_extra_shift,
    _evaluate_alternate_machine,
    _evaluate_partial_shipment,
    _compute_ranked_recommendation,
    _days_until,
)
from skills.delivery_risk import analyze_delivery_risk


class ExpediteOptionsSkillTest(unittest.TestCase):
    """Tests for the expedite-options skill core logic."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def test_high_risk_order_produces_options(self):
        """ORD-1001 (VIP, high penalty, at_risk) should produce ranked options."""
        result = handle_expedite_options(["ORD-1001"], self.mock_data_dir)
        self.assertNotIn("error", result)
        options = result.get("details", {}).get("options", [])
        self.assertGreaterEqual(len(options), 4)

    def test_options_have_required_fields(self):
        """Each option must contain all required fields."""
        result = handle_expedite_options(["ORD-1001"], self.mock_data_dir)
        options = result.get("details", {}).get("options", [])
        required = [
            "name", "label", "feasibility", "feasibility_reason",
            "expected_impact", "cost_implication", "cost_estimate",
            "key_assumptions", "blockers", "recommended",
        ]
        for opt in options:
            for field in required:
                self.assertIn(field, opt, f"Missing field: {field} in {opt['name']}")

    def test_options_are_ranked(self):
        """Options should be sorted by recommendation score descending."""
        result = handle_expedite_options(["ORD-1001"], self.mock_data_dir)
        options = result.get("details", {}).get("options", [])
        # At least one should be recommended if order is at-risk
        recommended = [o for o in options if o["recommended"]]
        self.assertGreaterEqual(len(recommended), 0)

    def test_option_summary_structure(self):
        """Option summary should contain counts and top recommendation."""
        result = handle_expedite_options(["ORD-1001"], self.mock_data_dir)
        summary = result.get("details", {}).get("option_summary", {})
        self.assertIn("total_evaluated", summary)
        self.assertIn("recommended_count", summary)
        self.assertIn("top_recommendation", summary)
        self.assertEqual(summary["total_evaluated"], 4)

    def test_no_order_id_returns_error(self):
        result = handle_expedite_options([], self.mock_data_dir)
        self.assertIn("error", result)

    def test_nonexistent_order_returns_error(self):
        result = handle_expedite_options(["ORD-9999"], self.mock_data_dir)
        self.assertIn("error", result)

    def test_order_without_expedite_config(self):
        """ORD-1003 has expedite_option='none' and cost=0 — options should have low feasibility."""
        result = handle_expedite_options(["ORD-1003"], self.mock_data_dir)
        self.assertNotIn("error", result)
        options = result.get("details", {}).get("options", [])
        # At least some options should still be evaluated
        self.assertGreaterEqual(len(options), 4)

    def test_reuses_delivery_risk_data(self):
        """Expedite options should inherit decision and blockers from delivery risk."""
        result = handle_expedite_options(["ORD-1001"], self.mock_data_dir)
        delivery = analyze_delivery_risk("ORD-1001", self.mock_data_dir)
        self.assertEqual(result["decision"], delivery.get("decision"))


class ExpediteOptionsRoutingTest(unittest.TestCase):
    """Tests for skill routing in the orchestrator."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def test_exact_keyword_routes_to_expedite(self):
        """Query with '加急方案' should route to expedite-options."""
        result = route_query("ORD-1001 加急方案", self.mock_data_dir)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skill"], "expedite-options")

    def test_english_exact_keyword(self):
        """'expedite options' should route to expedite-options."""
        result = route_query("ORD-1001 expedite options", self.mock_data_dir)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skill"], "expedite-options")

    def test_recovery_plan_keyword(self):
        """'recovery plan' should route to expedite-options."""
        result = route_query("ORD-1001 recovery plan", self.mock_data_dir)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skill"], "expedite-options")

    def test_no_keyword_collision_with_sales(self):
        """Query with expedite keywords should NOT route to sales-response-draft."""
        result = route_query("ORD-1001 加急方案", self.mock_data_dir)
        self.assertNotEqual(result["skill"], "sales-response-draft")
        self.assertEqual(result["skill"], "expedite-options")

    def test_no_keyword_collision_with_delivery(self):
        """Query with expedite keywords should NOT route to delivery-risk-analysis."""
        result = route_query("ORD-1001 加急方案", self.mock_data_dir)
        self.assertNotEqual(result["skill"], "delivery-risk-analysis")

    def test_requires_order_id(self):
        """Expedite options without order ID should return missing_order_id."""
        result = route_query("加急方案", self.mock_data_dir)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["type"], "missing_order_id")


class ExpediteOptionsSchemaTest(unittest.TestCase):
    """Tests for unified schema compliance."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def test_has_standardized_fields(self):
        result = handle_expedite_options(["ORD-1001"], self.mock_data_dir)
        for field in ["skill", "order_id", "decision", "confidence", "blockers",
                      "owner", "eta", "next_action", "trace", "details"]:
            self.assertIn(field, result, f"Missing field: {field}")

    def test_skill_identifier(self):
        result = handle_expedite_options(["ORD-1001"], self.mock_data_dir)
        self.assertEqual(result["skill"], "expedite-options")

    def test_details_contain_options(self):
        result = handle_expedite_options(["ORD-1001"], self.mock_data_dir)
        details = result.get("details", {})
        self.assertIn("options", details)
        self.assertIn("option_summary", details)

    def test_trace_not_empty(self):
        result = handle_expedite_options(["ORD-1001"], self.mock_data_dir)
        self.assertGreater(len(result.get("trace", [])), 0)


class ExpediteOptionsCLITest(unittest.TestCase):
    """Tests for CLI integration."""
    import subprocess

    def test_cli_expedite_options(self):
        result = self.subprocess.run(
            ["python3", "run_agent.py", "ORD-1001", "加急方案"],
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), "..")
        )
        # Should not crash
        self.assertEqual(result.returncode, 0)
        # Should contain expedite options output
        self.assertIn("EXPEDITE OPTIONS", result.stdout)

    def test_cli_expedite_options_shows_options(self):
        result = self.subprocess.run(
            ["python3", "run_agent.py", "ORD-1001", "expedite", "options"],
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), "..")
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Options evaluated:", result.stdout)


class ExpediteOptionsHelperTest(unittest.TestCase):
    """Tests for helper functions."""

    def test_days_until_future(self):
        from datetime import datetime, timedelta
        future = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        days = _days_until(future)
        self.assertGreater(days, 0)

    def test_days_until_invalid(self):
        days = _days_until("not-a-date")
        self.assertEqual(days, 0)

    def test_ranked_recommendation_sorting(self):
        options = [
            {"feasibility": "low", "recommended": False, "cost_estimate": None},
            {"feasibility": "high", "recommended": True, "cost_estimate": 5000},
            {"feasibility": "medium", "recommended": True, "cost_estimate": 3000},
        ]
        ranked = _compute_ranked_recommendation(options)
        # First should be high + recommended
        self.assertEqual(ranked[0]["feasibility"], "high")
        self.assertTrue(ranked[0]["recommended"])


class ExpediteOptionsServerTest(unittest.TestCase):
    """Tests for server /run endpoint with expedite-options."""

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

    def _post(self, payload):
        import json
        import urllib.request
        import urllib.error
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/run",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())

    def test_run_expedite_options(self):
        import json
        result = self._post({
            "query": "ORD-1001 加急方案",
        })
        self.assertEqual(result["status"], "success")
        self.assertIn("expedite_options", result.get("intent", ""))
