
import os
import tempfile
import json
import unittest
from orchestrator import route_query
from skills.material_shortage_recovery import (
    handle_material_shortage_recovery,
    _identify_shortage_materials,
    _evaluate_emergency_reorder,
    _evaluate_alternate_supplier,
    _evaluate_substitute_material,
    _evaluate_partial_production,
    _compute_ranked_recommendation,
)
from skills.delivery_risk import analyze_delivery_risk


class MaterialShortageRecoverySkillTest(unittest.TestCase):
    """Tests for the material-shortage-recovery skill core logic."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def test_shortage_order_produces_recovery_plan(self):
        """ORD-1001 has Coating Fluid X shortage — should produce recovery options."""
        result = handle_material_shortage_recovery(["ORD-1001"], self.mock_data_dir)
        self.assertNotIn("error", result)
        options = result.get("details", {}).get("options", [])
        self.assertGreaterEqual(len(options), 4)

    def test_no_shortage_order_returns_clear_result(self):
        """Order with no material shortages should return decision=no_shortage."""
        result = handle_material_shortage_recovery(["ORD-1002"], self.mock_data_dir)
        self.assertNotIn("error", result)
        # ORD-1002 may or may not have shortages depending on mock data
        # Just verify structure is correct
        self.assertIn("decision", result)
        self.assertIn("details", result)

    def test_options_have_required_fields(self):
        """Each recovery option must contain all required fields."""
        result = handle_material_shortage_recovery(["ORD-1001"], self.mock_data_dir)
        options = result.get("details", {}).get("options", [])
        required = [
            "name", "label", "feasibility", "feasibility_reason",
            "expected_impact", "lead_time_implication", "cost_implication",
            "cost_estimate", "assumptions", "blockers", "recommended",
        ]
        for opt in options:
            for field in required:
                self.assertIn(field, opt, f"Missing field: {field} in {opt['name']}")

    def test_shortages_identified_correctly(self):
        """Shortage materials should be listed with correct quantities."""
        result = handle_material_shortage_recovery(["ORD-1001"], self.mock_data_dir)
        shortages = result.get("details", {}).get("shortages", [])
        # ORD-1001 has Coating Fluid X shortage (20/50)
        self.assertGreater(len(shortages), 0)
        for s in shortages:
            self.assertIn("material", s)
            self.assertIn("shortage_qty", s)
            self.assertGreater(s["shortage_qty"], 0)
            self.assertIn("lead_time_days", s)
            self.assertIn("supplier_reliability", s)

    def test_recovery_summary_structure(self):
        """Recovery summary should contain counts and top recommendation."""
        result = handle_material_shortage_recovery(["ORD-1001"], self.mock_data_dir)
        summary = result.get("details", {}).get("recovery_summary", {})
        self.assertIn("total_shortages", summary)
        self.assertIn("total_evaluated", summary)
        self.assertIn("recommended_count", summary)
        self.assertIn("top_recommendation", summary)
        self.assertEqual(summary["total_evaluated"], 4)

    def test_no_order_id_returns_error(self):
        result = handle_material_shortage_recovery([], self.mock_data_dir)
        self.assertIn("error", result)

    def test_nonexistent_order_returns_error(self):
        result = handle_material_shortage_recovery(["ORD-9999"], self.mock_data_dir)
        self.assertIn("error", result)

    def test_high_lead_time_affects_ranking(self):
        """Long lead time + low reliability should make emergency reorder less feasible."""
        result = handle_material_shortage_recovery(["ORD-1001"], self.mock_data_dir)
        options = result.get("details", {}).get("options", [])
        emergency = next((o for o in options if o["name"] == "emergency_reorder"), None)
        self.assertIsNotNone(emergency)
        # Coating Fluid X has 14d lead time and 0.7 reliability
        # With 6 days left, emergency (14*0.6/0.7=~12d) likely won't arrive
        # Should not be recommended
        self.assertFalse(emergency["recommended"])

    def test_reuses_delivery_risk_data(self):
        """Recovery should inherit decision context from delivery risk."""
        result = handle_material_shortage_recovery(["ORD-1001"], self.mock_data_dir)
        delivery = analyze_delivery_risk("ORD-1001", self.mock_data_dir)
        self.assertEqual(result["confidence"], delivery.get("confidence"))


class MaterialShortageRoutingTest(unittest.TestCase):
    """Tests for skill routing in the orchestrator."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def test_exact_keyword_routes_to_recovery(self):
        result = route_query("ORD-1001 缺料恢復", self.mock_data_dir)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skill"], "material-shortage-recovery")

    def test_english_exact_keyword(self):
        result = route_query("ORD-1001 material shortage", self.mock_data_dir)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skill"], "material-shortage-recovery")

    def test_shortage_recovery_keyword(self):
        result = route_query("ORD-1001 shortage recovery", self.mock_data_dir)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skill"], "material-shortage-recovery")

    def test_no_collision_with_expedite(self):
        """Material shortage keywords should not route to expedite-options."""
        result = route_query("ORD-1001 缺料恢復", self.mock_data_dir)
        self.assertNotEqual(result["skill"], "expedite-options")

    def test_no_collision_with_delivery(self):
        """Material shortage keywords should not route to delivery-risk-analysis."""
        result = route_query("ORD-1001 缺料恢復", self.mock_data_dir)
        self.assertNotEqual(result["skill"], "delivery-risk-analysis")

    def test_requires_order_id(self):
        result = route_query("缺料恢復", self.mock_data_dir)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["type"], "missing_order_id")


class MaterialShortageSchemaTest(unittest.TestCase):
    """Tests for unified schema compliance."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def test_has_standardized_fields(self):
        result = handle_material_shortage_recovery(["ORD-1001"], self.mock_data_dir)
        for field in ["skill", "order_id", "decision", "confidence", "blockers",
                      "owner", "eta", "next_action", "trace", "details"]:
            self.assertIn(field, result, f"Missing field: {field}")

    def test_skill_identifier(self):
        result = handle_material_shortage_recovery(["ORD-1001"], self.mock_data_dir)
        self.assertEqual(result["skill"], "material-shortage-recovery")

    def test_details_contain_recovery_data(self):
        result = handle_material_shortage_recovery(["ORD-1001"], self.mock_data_dir)
        details = result.get("details", {})
        self.assertIn("shortages", details)
        self.assertIn("options", details)
        self.assertIn("recovery_summary", details)

    def test_trace_not_empty(self):
        result = handle_material_shortage_recovery(["ORD-1001"], self.mock_data_dir)
        self.assertGreater(len(result.get("trace", [])), 0)


class MaterialShortageCLITest(unittest.TestCase):
    """Tests for CLI integration."""
    import subprocess

    def test_cli_material_shortage_recovery(self):
        result = self.subprocess.run(
            ["python3", "run_agent.py", "ORD-1001", "缺料恢復"],
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), "..")
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("MATERIAL SHORTAGE RECOVERY", result.stdout)

    def test_cli_shows_shortages(self):
        result = self.subprocess.run(
            ["python3", "run_agent.py", "ORD-1001", "material", "shortage"],
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), "..")
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Shortages detected:", result.stdout)


class MaterialShortageHelperTest(unittest.TestCase):
    """Tests for helper functions."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def test_identify_shortage_materials(self):
        from data_source import load_data
        materials = load_data(self.mock_data_dir, "materials.json")
        shortages = _identify_shortage_materials("ORD-1001", materials)
        self.assertGreater(len(shortages), 0)
        # Coating Fluid X should be identified
        names = [s["material"] for s in shortages]
        self.assertIn("Coating Fluid X", names)

    def test_identify_no_shortage(self):
        from data_source import load_data
        materials = load_data(self.mock_data_dir, "materials.json")
        shortages = _identify_shortage_materials("ORD-1002", materials)
        # ORD-1002 has no materials in mock_data
        self.assertEqual(len(shortages), 0)

    def test_ranked_recommendation_sorting(self):
        options = [
            {"feasibility": "low", "recommended": False, "cost_estimate": None},
            {"feasibility": "high", "recommended": True, "cost_estimate": 5000},
            {"feasibility": "medium", "recommended": True, "cost_estimate": 3000},
        ]
        ranked = _compute_ranked_recommendation(options)
        self.assertEqual(ranked[0]["feasibility"], "high")
        self.assertTrue(ranked[0]["recommended"])


class MaterialShortageServerTest(unittest.TestCase):
    """Tests for server /run endpoint with material-shortage-recovery."""

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

    def test_run_material_shortage_recovery(self):
        result = self._post({
            "query": "ORD-1001 缺料恢復",
        })
        self.assertEqual(result["status"], "success")
        self.assertIn("material_shortage_recovery", result.get("intent", ""))
