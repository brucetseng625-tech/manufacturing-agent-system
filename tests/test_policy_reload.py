
import os
import tempfile
import json
import unittest
import socket
import threading
import time

from skills.policy import (
    DEFAULT_POLICY,
    reload_policy,
    get_reload_metadata,
    get_policy,
    get_policy_value,
)


class PolicyReloadTest(unittest.TestCase):
    """Tests for policy hot-reload functionality."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.tmpdir, "active.json")

    def _write_config(self, data):
        with open(self.config_path, "w") as f:
            json.dump(data, f)

    def test_reload_with_valid_config(self):
        """Reloading with a valid config file should succeed."""
        self._write_config({"delivery_risk": {"at_risk_blocker_max": 5}})
        result = reload_policy(self.config_path)
        self.assertTrue(result["success"])
        self.assertIn("active.json", result["source"])
        self.assertIsNone(result["error"])

        # Verify the new value is active
        val = get_policy_value("delivery_risk.at_risk_blocker_max")
        self.assertEqual(val, 5)

    def test_reload_with_missing_file_uses_defaults(self):
        """Reloading when config file doesn't exist should fall back to defaults."""
        result = reload_policy("/nonexistent/policy.json")
        self.assertTrue(result["success"])
        self.assertEqual(result["source"], "default")

        # Verify defaults are restored
        val = get_policy_value("routing.exact_keyword_weight")
        self.assertEqual(val, 5)

    def test_reload_with_invalid_json_fails_gracefully(self):
        """Reloading with invalid JSON should fail gracefully, not crash."""
        with open(self.config_path, "w") as f:
            f.write("{invalid json}")
        result = reload_policy(self.config_path)
        self.assertFalse(result["success"])
        self.assertIsNotNone(result["error"])

    def test_reload_metadata_tracks_count(self):
        """Reload count should increment with each reload."""
        meta_before = get_reload_metadata()
        count_before = meta_before["reload_count"]

        self._write_config({"routing": {"exact_keyword_weight": 10}})
        reload_policy(self.config_path)
        reload_policy(self.config_path)

        meta_after = get_reload_metadata()
        self.assertEqual(meta_after["reload_count"], count_before + 2)
        self.assertTrue(meta_after["last_reload_success"])

    def test_reload_updates_policy_immediately(self):
        """After reload, get_policy should return the new values."""
        self._write_config({"routing": {"exact_keyword_weight": 99}})
        reload_policy(self.config_path)
        policy = get_policy()
        self.assertEqual(policy["routing"]["exact_keyword_weight"], 99)

    def test_reload_preserves_unmodified_defaults(self):
        """Reloading with a partial config should preserve unmodified defaults."""
        self._write_config({"routing": {"keyword_weight": 9}})
        reload_policy(self.config_path)

        # Modified value
        self.assertEqual(get_policy_value("routing.keyword_weight"), 9)
        # Unmodified default
        self.assertEqual(get_policy_value("routing.exact_keyword_weight"), 5)
        self.assertEqual(get_policy_value("quote_scoring.price_weight"), 0.30)


class PolicyReloadEndpointTest(unittest.TestCase):
    """Tests for the POST /policy/reload HTTP endpoint."""

    def _find_free_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def test_reload_endpoint_without_body(self):
        """POST /policy/reload with no body should reload default path."""
        from server import run_server
        import urllib.request

        port = self._find_free_port()

        def run_in_thread():
            os.environ["AGENT_LOG_DIR"] = tempfile.mkdtemp()
            run_server(port=port)

        server_thread = threading.Thread(target=run_in_thread, daemon=True)
        server_thread.start()
        time.sleep(0.3)

        try:
            url = f"http://localhost:{port}/policy/reload"
            req = urllib.request.Request(url, data=b"", method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(data["success"])
                self.assertIn("source", data)
                self.assertIn("reload_count", data)
        finally:
            pass

    def test_reload_endpoint_with_custom_path(self):
        """POST /policy/reload with config_path in body."""
        from server import run_server
        import urllib.request

        port = self._find_free_port()
        tmpdir = tempfile.mkdtemp()
        config_path = os.path.join(tmpdir, "custom.json")
        with open(config_path, "w") as f:
            json.dump({"routing": {"exact_keyword_weight": 77}}, f)

        def run_in_thread():
            os.environ["AGENT_LOG_DIR"] = tempfile.mkdtemp()
            run_server(port=port)

        server_thread = threading.Thread(target=run_in_thread, daemon=True)
        server_thread.start()
        time.sleep(0.3)

        try:
            url = f"http://localhost:{port}/policy/reload"
            payload = json.dumps({"config_path": config_path}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(data["success"])
                self.assertIn("custom.json", data["source"])
        finally:
            pass
