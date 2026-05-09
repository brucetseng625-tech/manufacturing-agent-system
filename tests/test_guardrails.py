"""Tests for P9-4 Execution guardrails."""

import json
import threading
import time
import unittest
from http.server import HTTPServer
import urllib.request
from unittest.mock import patch

from guardrails import check_guardrail, get_guardrail, get_guardrails_status


class GuardrailsDisabledTest(unittest.TestCase):
    """When guardrails are disabled, all operations should be allowed."""

    def test_no_guard_when_disabled(self):
        """With guardrails disabled, check_guardrail returns None."""
        with patch("guardrails.get_config_value") as mock_cfg:
            mock_cfg.side_effect = lambda key, default: {
                "guardrails.enabled": False,
            }.get(key, default)
            result = check_guardrail("alerts:reset")
            self.assertIsNone(result)

    def test_no_guard_when_no_config_for_operation(self):
        """With guardrails enabled but no config for operation, allowed."""
        with patch("guardrails.get_config_value") as mock_cfg:
            mock_cfg.side_effect = lambda key, default: {
                "guardrails.enabled": True,
                "guardrails.operations": {},
            }.get(key, default)
            result = check_guardrail("alerts:reset")
            self.assertIsNone(result)


class GuardrailsDenyTest(unittest.TestCase):
    """Test operation denial via guardrails."""

    def test_denied_operation_returns_error(self):
        """Denied operation should return guardrail_denied error."""
        with patch("guardrails.get_config_value") as mock_cfg:
            mock_cfg.side_effect = lambda key, default: {
                "guardrails.enabled": True,
                "guardrails.operations": {
                    "alerts:reset": {"denied": True},
                },
            }.get(key, default)
            result = check_guardrail("alerts:reset")
            self.assertIsNotNone(result)
            self.assertEqual(result["error_type"], "guardrail_denied")
            self.assertEqual(result["operation"], "alerts:reset")

    def test_non_denied_operation_allowed(self):
        """Non-denied operation should be allowed."""
        with patch("guardrails.get_config_value") as mock_cfg:
            mock_cfg.side_effect = lambda key, default: {
                "guardrails.enabled": True,
                "guardrails.operations": {
                    "alerts:reset": {"denied": True},
                },
            }.get(key, default)
            result = check_guardrail("config:reload")
            self.assertIsNone(result)


class GuardrailsApprovalTest(unittest.TestCase):
    """Test approval-required guardrails."""

    def test_approval_required_without_token_denied(self):
        """Operation requiring approval without token should be denied."""
        with patch("guardrails.get_config_value") as mock_cfg:
            mock_cfg.side_effect = lambda key, default: {
                "guardrails.enabled": True,
                "guardrails.operations": {
                    "policy:reload": {"require_approval": True},
                },
                "guardrails.approval_token": "secret-123",
            }.get(key, default)
            result = check_guardrail("policy:reload", {})
            self.assertIsNotNone(result)
            self.assertEqual(result["error_type"], "guardrail_approval_required")

    def test_approval_required_with_correct_token_allowed(self):
        """Operation requiring approval with correct token should be allowed."""
        with patch("guardrails.get_config_value") as mock_cfg:
            mock_cfg.side_effect = lambda key, default: {
                "guardrails.enabled": True,
                "guardrails.operations": {
                    "policy:reload": {"require_approval": True},
                },
                "guardrails.approval_token": "secret-123",
            }.get(key, default)
            headers = {"X-Approval-Token": "secret-123"}
            result = check_guardrail("policy:reload", headers)
            self.assertIsNone(result)

    def test_approval_required_with_wrong_token_denied(self):
        """Operation with wrong approval token should be denied."""
        with patch("guardrails.get_config_value") as mock_cfg:
            mock_cfg.side_effect = lambda key, default: {
                "guardrails.enabled": True,
                "guardrails.operations": {
                    "policy:reload": {"require_approval": True},
                },
                "guardrails.approval_token": "secret-123",
            }.get(key, default)
            headers = {"X-Approval-Token": "wrong-token"}
            result = check_guardrail("policy:reload", headers)
            self.assertIsNotNone(result)
            self.assertEqual(result["error_type"], "guardrail_approval_required")

    def test_approval_header_lowercase(self):
        """Approval token should work with lowercase header name."""
        with patch("guardrails.get_config_value") as mock_cfg:
            mock_cfg.side_effect = lambda key, default: {
                "guardrails.enabled": True,
                "guardrails.operations": {
                    "policy:reload": {"require_approval": True},
                },
                "guardrails.approval_token": "secret-123",
            }.get(key, default)
            headers = {"x-approval-token": "secret-123"}
            result = check_guardrail("policy:reload", headers)
            self.assertIsNone(result)

    def test_approval_not_required_no_token_allowed(self):
        """Operation not requiring approval should work without token."""
        with patch("guardrails.get_config_value") as mock_cfg:
            mock_cfg.side_effect = lambda key, default: {
                "guardrails.enabled": True,
                "guardrails.operations": {
                    "config:reload": {"require_approval": False},
                },
            }.get(key, default)
            result = check_guardrail("config:reload", {})
            self.assertIsNone(result)


class GuardrailsStatusTest(unittest.TestCase):
    """Tests for guardrails status endpoint."""

    def test_status_disabled(self):
        """Status should show enabled=false when guardrails disabled."""
        with patch("guardrails.get_config_value") as mock_cfg:
            mock_cfg.side_effect = lambda key, default: {
                "guardrails.enabled": False,
                "guardrails.operations": {},
            }.get(key, default)
            status = get_guardrails_status()
            self.assertFalse(status["enabled"])
            self.assertEqual(status["operations"], {})

    def test_status_enabled_with_operations(self):
        """Status should show per-operation guard settings."""
        with patch("guardrails.get_config_value") as mock_cfg:
            mock_cfg.side_effect = lambda key, default: {
                "guardrails.enabled": True,
                "guardrails.operations": {
                    "alerts:reset": {"denied": False, "require_approval": False},
                    "policy:reload": {"denied": False, "require_approval": True},
                },
            }.get(key, default)
            status = get_guardrails_status()
            self.assertTrue(status["enabled"])
            self.assertIn("alerts:reset", status["operations"])
            self.assertIn("policy:reload", status["operations"])
            self.assertFalse(status["operations"]["alerts:reset"]["require_approval"])
            self.assertTrue(status["operations"]["policy:reload"]["require_approval"])


class ServerGuardrailsEndpointTest(unittest.TestCase):
    """Integration tests for GET /guardrails endpoint."""

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

    def test_guardrails_endpoint_responds(self):
        """GET /guardrails must return 200."""
        status, body = self._get("/guardrails")
        self.assertEqual(status, 200)

    def test_guardrails_has_enabled_field(self):
        """Response must include enabled boolean."""
        status, body = self._get("/guardrails")
        self.assertIn("enabled", body)
        self.assertIsInstance(body["enabled"], bool)

    def test_guardrails_has_operations_field(self):
        """Response must include operations dict."""
        status, body = self._get("/guardrails")
        self.assertIn("operations", body)
        self.assertIsInstance(body["operations"], dict)


if __name__ == "__main__":
    unittest.main()
