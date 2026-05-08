
import os
import tempfile
import json
import unittest
from orchestrator import route_query
from skills.capacity_rebalance import (
    handle_capacity_rebalance,
    _analyze_machine_loads,
    _identify_pressure_points,
    _evaluate_reassign_machine,
    _evaluate_resequence_wos,
    _evaluate_split_load,
    _evaluate_defer_order,
    _compute_ranked_recommendation,
)
from skills.delivery_risk import analyze_delivery_risk
from skills.schedule_conflict_check import check_schedule_conflict


class CapacityRebalanceSkillTest(unittest.TestCase):
    """Tests for the capacity-rebalance skill core logic."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def test_single_order_produces_rebalance_plan(self):
        """ORD-1001 has machine and schedule pressure — should produce rebalance options."""
        result = handle_capacity_rebalance(["ORD-1001"], self.mock_data_dir)
        self.assertNotIn("error", result)
        # Should have pressures or conflicts
        pressures = result.get("details", {}).get("pressures", [])
        conflicts = result.get("details", {}).get("conflicts", [])
        total = len(pressures) + len(conflicts)
        self.assertGreater(total, 0)

    def test_options_have_required_fields(self):
        """Each rebalance option must contain all required fields."""
        result = handle_capacity_rebalance(["ORD-1001"], self.mock_data_dir)
        options = result.get("details", {}).get("options", [])
        required = [
            "name", "label", "feasibility", "feasibility_reason",
            "expected_impact", "capacity_effect", "timing_implication",
            "cost_implication", "cost_estimate", "assumptions", "blockers", "recommended",
        ]
        for opt in options:
            for field in required:
                self.assertIn(field, opt, f"Missing field: {field} in {opt['name']}")

    def test_rebalance_summary_structure(self):
        """Rebalance summary should contain counts and top recommendation."""
        result = handle_capacity_rebalance(["ORD-1001"], self.mock_data_dir)
        summary = result.get("details", {}).get("rebalance_summary", {})
        self.assertIn("total_pressures", summary)
        self.assertIn("total_conflicts", summary)
        self.assertIn("total_evaluated", summary)
        self.assertIn("recommended_count", summary)
        self.assertIn("top_recommendation", summary)
        self.assertEqual(summary["total_evaluated"], 4)

    def test_machine_utilization_reported(self):
        """Machine utilization should be reported for all machines."""
        result = handle_capacity_rebalance(["ORD-1001"], self.mock_data_dir)
        util = result.get("details", {}).get("machine_utilization", {})
        self.assertGreater(len(util), 0)
        for mid, u in util.items():
            self.assertIn("load_percent", u)
            self.assertIn("max_capacity_percent", u)
            self.assertIn("available_capacity_percent", u)
            self.assertIn("status", u)

    def test_no_order_id_returns_error(self):
        result = handle_capacity_rebalance([], self.mock_data_dir)
        self.assertIn("error", result)

    def test_nonexistent_order_returns_error(self):
        result = handle_capacity_rebalance(["ORD-9999"], self.mock_data_dir)
        self.assertIn("error", result)

    def test_options_count(self):
        """Should always evaluate 4 options."""
        result = handle_capacity_rebalance(["ORD-1001"], self.mock_data_dir)
        options = result.get("details", {}).get("options", [])
        self.assertEqual(len(options), 4)

    def test_reuses_delivery_risk_context(self):
        """Rebalance should inherit confidence from delivery risk."""
        result = handle_capacity_rebalance(["ORD-1001"], self.mock_data_dir)
        delivery = analyze_delivery_risk("ORD-1001", self.mock_data_dir)
        if "error" not in delivery:
            self.assertEqual(result["confidence"], delivery.get("confidence"))


class CapacityRebalanceRoutingTest(unittest.TestCase):
    """Tests for skill routing in the orchestrator."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def test_exact_keyword_routes_to_rebalance(self):
        result = route_query("ORD-1001 產能重分配", self.mock_data_dir)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skill"], "capacity-rebalance")

    def test_english_exact_keyword(self):
        result = route_query("ORD-1001 capacity rebalance", self.mock_data_dir)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skill"], "capacity-rebalance")

    def test_load_balancing_keyword(self):
        result = route_query("ORD-1001 機台負載平衡", self.mock_data_dir)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skill"], "capacity-rebalance")

    def test_no_collision_with_schedule_conflict(self):
        """Capacity keywords should not route to schedule-conflict-check."""
        result = route_query("ORD-1001 產能重分配", self.mock_data_dir)
        self.assertNotEqual(result["skill"], "schedule-conflict-check")

    def test_no_collision_with_expedite(self):
        result = route_query("ORD-1001 產能重分配", self.mock_data_dir)
        self.assertNotEqual(result["skill"], "expedite-options")

    def test_no_collision_with_shortage(self):
        result = route_query("ORD-1001 產能重分配", self.mock_data_dir)
        self.assertNotEqual(result["skill"], "material-shortage-recovery")

    def test_requires_order_id(self):
        result = route_query("產能重分配", self.mock_data_dir)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["type"], "missing_order_id")


class CapacityRebalanceSchemaTest(unittest.TestCase):
    """Tests for unified schema compliance."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def test_has_standardized_fields(self):
        result = handle_capacity_rebalance(["ORD-1001"], self.mock_data_dir)
        for field in ["skill", "order_id", "decision", "confidence", "blockers",
                      "owner", "eta", "next_action", "trace", "details"]:
            self.assertIn(field, result, f"Missing field: {field}")

    def test_skill_identifier(self):
        result = handle_capacity_rebalance(["ORD-1001"], self.mock_data_dir)
        self.assertEqual(result["skill"], "capacity-rebalance")

    def test_details_contain_rebalance_data(self):
        result = handle_capacity_rebalance(["ORD-1001"], self.mock_data_dir)
        details = result.get("details", {})
        self.assertIn("pressures", details)
        self.assertIn("options", details)
        self.assertIn("rebalance_summary", details)
        self.assertIn("machine_utilization", details)

    def test_trace_not_empty(self):
        result = handle_capacity_rebalance(["ORD-1001"], self.mock_data_dir)
        self.assertGreater(len(result.get("trace", [])), 0)


class CapacityRebalanceCLITest(unittest.TestCase):
    """Tests for CLI integration."""
    import subprocess

    def test_cli_capacity_rebalance(self):
        result = self.subprocess.run(
            ["python3", "run_agent.py", "ORD-1001", "產能重分配"],
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), "..")
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("CAPACITY REBALANCE", result.stdout)

    def test_cli_shows_machine_utilization(self):
        result = self.subprocess.run(
            ["python3", "run_agent.py", "ORD-1001", "capacity", "rebalance"],
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), "..")
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Machine Utilization", result.stdout)


class CapacityRebalanceHelperTest(unittest.TestCase):
    """Tests for helper functions."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def test_analyze_machine_loads(self):
        from data_source import load_data
        machines = load_data(self.mock_data_dir, "machines.json")
        work_orders = load_data(self.mock_data_dir, "work_orders.json")
        result = _analyze_machine_loads(machines, work_orders)
        self.assertIn("CNC-01", result)
        self.assertIn("CNC-02", result)
        self.assertIn("load_percent", result["CNC-01"])
        self.assertIn("available_capacity_percent", result["CNC-01"])

    def test_ranked_recommendation_sorting(self):
        options = [
            {"feasibility": "low", "recommended": False, "cost_estimate": None},
            {"feasibility": "high", "recommended": True, "cost_estimate": 5000},
            {"feasibility": "medium", "recommended": True, "cost_estimate": 3000},
        ]
        ranked = _compute_ranked_recommendation(options)
        self.assertEqual(ranked[0]["feasibility"], "high")
        self.assertTrue(ranked[0]["recommended"])


class CapacityRebalanceServerTest(unittest.TestCase):
    """Tests for server /run endpoint with capacity-rebalance."""

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
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/run",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())

    def test_run_capacity_rebalance(self):
        result = self._post({
            "query": "ORD-1001 產能重分配",
        })
        self.assertEqual(result["status"], "success")
        self.assertIn("capacity_rebalance", result.get("intent", ""))
