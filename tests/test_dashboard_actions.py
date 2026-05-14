"""Tests for P9-2 Dashboard operator action panel."""

import json
import os
import threading
import time
import unittest
from http.server import HTTPServer
import urllib.request

from alert import get_alert_manager


class DashboardOperatorActionsHTMLTest(unittest.TestCase):
    """Tests that dashboard HTML contains operator action elements."""

    def setUp(self):
        dashboard_path = os.path.join(
            os.path.dirname(__file__), "..", "static", "dashboard.html"
        )
        with open(dashboard_path, "r", encoding="utf-8") as f:
            self.html = f.read()

    def test_contains_operator_actions_card(self):
        """Dashboard must contain 快速操作 card title."""
        self.assertIn("快速操作", self.html)

    def test_contains_reset_alerts_button(self):
        """Dashboard must contain reset_alerts action button."""
        self.assertIn("doAction('reset_alerts')", self.html)
        self.assertIn("重設警報", self.html)

    def test_contains_reload_config_button(self):
        """Dashboard must contain reload_config action button."""
        self.assertIn("doAction('reload_config')", self.html)
        self.assertIn("重載設定", self.html)

    def test_contains_reload_policy_button(self):
        """Dashboard must contain reload_policy action button."""
        self.assertIn("doAction('reload_policy')", self.html)
        self.assertIn("重載政策", self.html)

    def test_contains_health_check_button(self):
        """Dashboard must contain health_check action button."""
        self.assertIn("doAction('health_check')", self.html)
        self.assertIn("健康檢查", self.html)

    def test_contains_action_result_element(self):
        """Dashboard must have action-result div for feedback."""
        self.assertIn('id="action-result"', self.html)
        self.assertIn("action-result", self.html)

    def test_contains_doaction_function(self):
        """Dashboard must have doAction JavaScript function."""
        self.assertIn("async function doAction(action)", self.html)

    def test_contains_showactionresult_function(self):
        """Dashboard must have showActionResult JavaScript function."""
        self.assertIn("function showActionResult(type, message)", self.html)

    def test_contains_approval_request_preview_markup(self):
        """Approval queue should render replay request preview details."""
        self.assertIn("request_preview", self.html)
        self.assertIn("風險", self.html)

    def test_action_endpoints_mapping(self):
        """doAction must map actions to correct endpoints."""
        self.assertIn("'/alerts/reset'", self.html)
        self.assertIn("'/config/reload'", self.html)
        self.assertIn("'/policy/reload'", self.html)
        self.assertIn("'/provider/health'", self.html)

    def test_action_button_disable_on_click(self):
        """doAction must disable buttons during execution."""
        self.assertIn("b.disabled = true", self.html)
        self.assertIn("b.disabled = false", self.html)


class OperatorActionEndpointTest(unittest.TestCase):
    """Integration tests that dashboard action endpoints respond correctly."""

    @classmethod
    def setUpClass(cls):
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

    def _get(self, path):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}")
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())

    def _post(self, path, body=None):
        data = json.dumps(body).encode() if body else b""
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            method="POST",
        )
        if body:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())

    def test_reset_alerts_endpoint(self):
        """POST /alerts/reset must return success."""
        status, body = self._post("/alerts/reset")
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])

    def test_health_check_endpoint(self):
        """GET /provider/health must return health status."""
        status, body = self._get("/provider/health")
        self.assertEqual(status, 200)
        self.assertIn("status", body)

    def test_reload_config_endpoint(self):
        """POST /config/reload must return reload result."""
        status, body = self._post("/config/reload", {})
        self.assertEqual(status, 200)
        self.assertIn("success", body)
        self.assertIn("source", body)

    def test_reload_policy_endpoint(self):
        """POST /policy/reload must return reload result."""
        status, body = self._post("/policy/reload")
        self.assertEqual(status, 200)
        self.assertIn("success", body)


if __name__ == "__main__":
    unittest.main()
