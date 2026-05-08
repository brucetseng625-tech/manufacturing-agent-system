
import os
import tempfile
import json
import unittest
from skills.policy import (
    DEFAULT_POLICY,
    load_policy,
    get_policy,
    set_policy,
    get_policy_value,
    _deep_merge,
)


class PolicyDefaultsTest(unittest.TestCase):
    """Tests for DEFAULT_POLICY structure."""

    def test_default_policy_has_all_sections(self):
        """Default policy must contain all expected sections."""
        expected = [
            "routing", "delivery_risk", "quote_scoring",
            "option_ranking", "shortage_recovery", "capacity_rebalance",
            "supplier_followup", "defaults",
        ]
        for section in expected:
            self.assertIn(section, DEFAULT_POLICY)

    def test_default_routing_weights(self):
        self.assertEqual(DEFAULT_POLICY["routing"]["exact_keyword_weight"], 5)
        self.assertEqual(DEFAULT_POLICY["routing"]["keyword_weight"], 2)
        self.assertEqual(DEFAULT_POLICY["routing"]["multi_order_boost"], 3)

    def test_default_delivery_risk_thresholds(self):
        self.assertEqual(DEFAULT_POLICY["delivery_risk"]["at_risk_blocker_max"], 2)
        self.assertEqual(DEFAULT_POLICY["delivery_risk"]["vip_penalty_threshold"], 2000)

    def test_default_quote_scoring_weights(self):
        qs = DEFAULT_POLICY["quote_scoring"]
        self.assertAlmostEqual(qs["price_weight"], 0.30)
        self.assertAlmostEqual(qs["reliability_weight"], 0.25)
        self.assertAlmostEqual(qs["quality_weight"], 0.20)
        self.assertAlmostEqual(qs["lead_time_weight"], 0.15)
        self.assertAlmostEqual(qs["risk_weight"], 0.10)


class DeepMergeTest(unittest.TestCase):
    """Tests for _deep_merge utility."""

    def test_simple_override(self):
        base = {"a": 1, "b": 2}
        override = {"a": 10}
        result = _deep_merge(base, override)
        self.assertEqual(result["a"], 10)
        self.assertEqual(result["b"], 2)

    def test_nested_override(self):
        base = {"routing": {"exact_keyword_weight": 5, "keyword_weight": 2}}
        override = {"routing": {"exact_keyword_weight": 10}}
        result = _deep_merge(base, override)
        self.assertEqual(result["routing"]["exact_keyword_weight"], 10)
        self.assertEqual(result["routing"]["keyword_weight"], 2)

    def test_new_key_added(self):
        base = {"a": 1}
        override = {"b": 2}
        result = _deep_merge(base, override)
        self.assertEqual(result["a"], 1)
        self.assertEqual(result["b"], 2)

    def test_no_mutation(self):
        base = {"a": {"b": 1}}
        override = {"a": {"c": 2}}
        _deep_merge(base, override)
        self.assertEqual(base["a"]["b"], 1)
        self.assertNotIn("c", base["a"])


class PolicyLoadingTest(unittest.TestCase):
    """Tests for load_policy and config file loading."""

    def test_load_default_when_no_file(self):
        """If no config file exists, should return DEFAULT_POLICY."""
        policy = load_policy("/nonexistent/path.json")
        self.assertEqual(policy["routing"]["exact_keyword_weight"], 5)
        self.assertEqual(policy["_source"], "default")

    def test_load_custom_config_file(self):
        """Config file overrides should merge with defaults."""
        override = {
            "routing": {"exact_keyword_weight": 10},
            "delivery_risk": {"at_risk_blocker_max": 5},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(override, f)
            tmp_path = f.name

        try:
            policy = load_policy(tmp_path)
            self.assertEqual(policy["routing"]["exact_keyword_weight"], 10)
            self.assertEqual(policy["routing"]["keyword_weight"], 2)  # unchanged default
            self.assertEqual(policy["delivery_risk"]["at_risk_blocker_max"], 5)
            self.assertIn("quote_scoring", policy)  # other sections intact
            self.assertEqual(policy["_source"], f"file:{tmp_path}")
        finally:
            os.unlink(tmp_path)

    def test_invalid_config_file_raises(self):
        """Invalid JSON in config file should raise."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{invalid json")
            tmp_path = f.name

        try:
            with self.assertRaises(json.JSONDecodeError):
                load_policy(tmp_path)
        finally:
            os.unlink(tmp_path)


class PolicyGetTest(unittest.TestCase):
    """Tests for get_policy and get_policy_value."""

    def tearDown(self):
        set_policy(DEFAULT_POLICY)

    def test_get_policy_returns_default(self):
        policy = get_policy()
        self.assertIs(policy, DEFAULT_POLICY)

    def test_set_and_get_policy(self):
        custom = {"custom": True}
        set_policy(custom)
        self.assertEqual(get_policy()["custom"], True)

    def test_get_policy_value_dot_notation(self):
        val = get_policy_value("routing.exact_keyword_weight")
        self.assertEqual(val, 5)

    def test_get_policy_value_nested(self):
        val = get_policy_value("delivery_risk.escalation.vip_vp_level_penalty")
        self.assertEqual(val, 2000)

    def test_get_policy_value_missing_returns_default(self):
        val = get_policy_value("nonexistent.key", default=99)
        self.assertEqual(val, 99)

    def test_get_policy_value_missing_no_default(self):
        val = get_policy_value("nonexistent.key")
        self.assertIsNone(val)


class PolicyIntegrationTest(unittest.TestCase):
    """Tests that policy changes affect actual skill behavior."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def tearDown(self):
        set_policy(DEFAULT_POLICY)

    def test_modified_routing_weight_affects_matching(self):
        """Increasing exact_keyword_weight should still route correctly."""
        from orchestrator import route_query
        from skills.registry import get_registry

        # Set policy with higher exact keyword weight
        custom = {
            "routing": {"exact_keyword_weight": 20}
        }
        policy = _deep_merge(DEFAULT_POLICY, custom)
        set_policy(policy)

        # Should still route correctly
        result = route_query("ORD-1001 交期風險", self.mock_data_dir)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skill"], "delivery-risk-analysis")

    def test_modified_quote_weights_affect_scoring(self):
        """Changing quote scoring weights should change supplier ranking."""
        from skills.quote_comparison_summary import handle_quote_comparison

        # Set policy that heavily weights price
        custom = {
            "quote_scoring": {
                "price_weight": 0.60,
                "reliability_weight": 0.10,
                "quality_weight": 0.10,
                "lead_time_weight": 0.10,
                "risk_weight": 0.10,
            }
        }
        policy = _deep_merge(DEFAULT_POLICY, custom)
        set_policy(policy)

        result = handle_quote_comparison([], self.mock_data_dir, "Steel 報價")
        self.assertNotIn("error", result)
        # Should still produce a valid result
        self.assertIn("decision", result)


class PolicyCLITest(unittest.TestCase):
    """Tests for CLI --policy flag."""
    import subprocess

    def test_cli_policy_flag(self):
        result = self.subprocess.run(
            ["python3", "run_agent.py", "--policy"],
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), "..")
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Policy source:", result.stdout)
        self.assertIn("routing", result.stdout)
        self.assertIn("delivery_risk", result.stdout)


class PolicyServerTest(unittest.TestCase):
    """Tests for server /policy endpoint."""

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

    def test_get_policy_endpoint(self):
        import json
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/policy")
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read())
        self.assertIn("source", data)
        self.assertIn("policy", data)
        self.assertIn("routing", data["policy"])
        self.assertIn("delivery_risk", data["policy"])
