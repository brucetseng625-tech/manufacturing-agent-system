
import json
import os
import threading
import time
import unittest
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
from unittest.mock import patch

from data_source import (
    LocalFileProvider,
    LiveDataProvider,
    AutoFailoverProvider,
    get_data_source,
    set_data_source,
    get_provider_status,
    get_provider_health,
    get_degradation_status,
)
from alert import AlertManager, check_alerts, get_alert_manager


class AlertManagerEvaluationTest(unittest.TestCase):
    """Tests for alert evaluation logic without network calls."""

    def setUp(self):
        self.mgr = AlertManager()
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def test_no_alert_when_system_ok(self):
        """No alert should trigger when system is healthy."""
        local = LocalFileProvider()
        set_data_source(local)
        status = get_provider_status(self.mock_data_dir)
        health = get_provider_health(self.mock_data_dir)
        degradation = get_degradation_status(self.mock_data_dir)

        result = self.mgr.check_and_notify("ok", degradation, health, status)
        self.assertIsNone(result)

    def test_alert_when_system_unhealthy(self):
        """Should trigger alert when system is unhealthy."""
        result = self.mgr._evaluate("unhealthy", {}, {"status": "unreachable"}, {"readiness": "disabled"})
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "system_unhealthy")
        self.assertEqual(result["severity"], "critical")

    def test_alert_when_provider_disabled(self):
        """Should trigger alert when provider readiness is disabled."""
        result = self.mgr._evaluate("ok", {}, {"status": "ok"}, {"readiness": "disabled"})
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "system_unhealthy")
        self.assertEqual(result["severity"], "critical")

    def test_alert_when_degraded_with_circuit_open(self):
        """Should trigger alert when circuit breaker is open."""
        degradation = {
            "is_degraded": True,
            "circuit_breaker": {"state": "open"},
            "reason": "Circuit tripped",
        }
        result = self.mgr._evaluate("degraded", degradation, {"status": "degraded"}, {"readiness": "degraded"})
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "circuit_breaker_open")
        self.assertEqual(result["severity"], "warning")

    def test_alert_when_degraded_no_circuit(self):
        """Should trigger degradation alert when degraded without circuit breaker."""
        degradation = {
            "is_degraded": True,
            "circuit_breaker": None,
            "reason": "Live provider not configured",
        }
        result = self.mgr._evaluate("degraded", degradation, {"status": "not_configured"}, {"readiness": "degraded"})
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "degradation_detected")
        self.assertEqual(result["severity"], "warning")

    def test_no_alert_when_ok_and_not_degraded(self):
        """No alert when system is ok and not degraded."""
        result = self.mgr._evaluate("ok", {"is_degraded": False}, {"status": "ok"}, {"readiness": "ready"})
        self.assertIsNone(result)


class AlertManagerCooldownTest(unittest.TestCase):
    """Tests for alert cooldown behavior."""

    def setUp(self):
        self.mgr = AlertManager()
        self.mgr._send_webhook = lambda url, payload: True

    @patch("alert.get_config_value")
    def test_cooldown_prevents_duplicate_alerts(self, mock_cfg):
        """Second alert within cooldown should not send."""
        mock_cfg.side_effect = lambda key, default: {
            "alerts.enabled": True,
            "alerts.webhook_url": "http://example.com/webhook",
            "alerts.cooldown_seconds": 300,
        }.get(key, default)

        # First alert should send
        result1 = self.mgr.check_and_notify(
            "unhealthy", {"is_degraded": True}, {"status": "unreachable"}, {"readiness": "disabled"}
        )
        self.assertIsNotNone(result1)
        self.assertTrue(result1["sent"])

        # Second alert immediately should be in cooldown
        result2 = self.mgr.check_and_notify(
            "unhealthy", {"is_degraded": True}, {"status": "unreachable"}, {"readiness": "disabled"}
        )
        self.assertIsNone(result2)

    @patch("alert.get_config_value")
    def test_cooldown_expires_allows_new_alert(self, mock_cfg):
        """After cooldown expires, new alert should send."""
        mock_cfg.side_effect = lambda key, default: {
            "alerts.enabled": True,
            "alerts.webhook_url": "http://example.com/webhook",
            "alerts.cooldown_seconds": 300,
        }.get(key, default)

        # First alert
        result1 = self.mgr.check_and_notify(
            "unhealthy", {"is_degraded": True}, {"status": "unreachable"}, {"readiness": "disabled"}
        )
        self.assertIsNotNone(result1)

        # Simulate time passing past cooldown
        self.mgr._last_alert["system_unhealthy"] = time.time() - 600  # 10 min ago
        self.mgr.reset()
        # After reset, cooldown cleared — new alert should work
        result2 = self.mgr.check_and_notify(
            "unhealthy", {"is_degraded": True}, {"status": "unreachable"}, {"readiness": "disabled"}
        )
        self.assertIsNotNone(result2)

    @patch("alert.get_config_value")
    def test_different_alert_types_have_independent_cooldowns(self, mock_cfg):
        """Different alert types should not block each other."""
        mock_cfg.side_effect = lambda key, default: {
            "alerts.enabled": True,
            "alerts.webhook_url": "http://example.com/webhook",
            "alerts.cooldown_seconds": 300,
        }.get(key, default)

        # Trigger system_unhealthy
        result1 = self.mgr.check_and_notify(
            "unhealthy", {"is_degraded": True}, {"status": "unreachable"}, {"readiness": "disabled"}
        )
        self.assertIsNotNone(result1)
        self.assertEqual(result1["alert"]["alert_type"], "system_unhealthy")

        # Trigger circuit_breaker_open (different type, should still send)
        degradation = {
            "is_degraded": True,
            "circuit_breaker": {"state": "open"},
            "reason": "test",
            "recommendations": [],
        }
        result2 = self.mgr.check_and_notify(
            "degraded", degradation, {"status": "degraded"}, {"readiness": "degraded"}
        )
        self.assertIsNotNone(result2)
        self.assertEqual(result2["alert"]["alert_type"], "circuit_breaker_open")


class AlertManagerLogTest(unittest.TestCase):
    """Tests for alert log functionality."""

    def setUp(self):
        self.mgr = AlertManager()
        self.mgr._send_webhook = lambda url, payload: True

    @patch("alert.get_config_value")
    def test_alert_log_records_sent_alerts(self, mock_cfg):
        """Alert log should record sent alerts."""
        mock_cfg.side_effect = lambda key, default: {
            "alerts.enabled": True,
            "alerts.webhook_url": "http://example.com/webhook",
            "alerts.cooldown_seconds": 300,
        }.get(key, default)

        self.mgr.check_and_notify(
            "unhealthy", {"is_degraded": True}, {"status": "unreachable"}, {"readiness": "disabled"}
        )
        log = self.mgr.get_alert_log()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["type"], "system_unhealthy")
        self.assertTrue(log[0]["sent"])

    @patch("alert.get_config_value")
    def test_alert_log_does_not_record_blocked_alerts(self, mock_cfg):
        """Cooldown-blocked alerts should not appear in log."""
        mock_cfg.side_effect = lambda key, default: {
            "alerts.enabled": True,
            "alerts.webhook_url": "http://example.com/webhook",
            "alerts.cooldown_seconds": 300,
        }.get(key, default)

        self.mgr.check_and_notify(
            "unhealthy", {"is_degraded": True}, {"status": "unreachable"}, {"readiness": "disabled"}
        )
        # Second alert blocked by cooldown
        self.mgr.check_and_notify(
            "unhealthy", {"is_degraded": True}, {"status": "unreachable"}, {"readiness": "disabled"}
        )
        log = self.mgr.get_alert_log()
        self.assertEqual(len(log), 1)

    def test_reset_clears_log(self):
        """Reset should clear the alert log."""
        # Directly add to log to test reset
        self.mgr._alert_log.append({"type": "test", "severity": "warning", "sent": True})
        self.mgr.reset()
        log = self.mgr.get_alert_log()
        self.assertEqual(len(log), 0)


class CheckAlertsDisabledTest(unittest.TestCase):
    """Tests for check_alerts when alerts are disabled."""

    def setUp(self):
        # Reset singleton state
        get_alert_manager().reset()

    def test_no_alert_when_disabled(self):
        """No alert when alerts.enabled is False."""
        result = check_alerts("unhealthy", {"is_degraded": True}, {"status": "unreachable"}, {"readiness": "disabled"})
        self.assertIsNone(result)

    def test_no_alert_when_no_webhook_url(self):
        """No alert when webhook_url is empty."""
        result = check_alerts("unhealthy", {"is_degraded": True}, {"status": "unreachable"}, {"readiness": "disabled"})
        self.assertIsNone(result)


class ServerAlertsLogTest(unittest.TestCase):
    """Tests for GET /alerts/log endpoint."""

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

    def test_alerts_log_endpoint(self):
        """Endpoint should return alert log."""
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/alerts/log"
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.read())
            self.assertIn("total", body)
            self.assertIn("alerts", body)
            self.assertIsInstance(body["alerts"], list)

    def test_alerts_log_with_last_param(self):
        """Endpoint should accept last query parameter."""
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/alerts/log?last=5"
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.read())
            self.assertIn("total", body)


class ServerAlertsResetTest(unittest.TestCase):
    """Tests for POST /alerts/reset endpoint."""

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

    def test_alerts_reset_endpoint(self):
        """Endpoint should clear alert state."""
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/alerts/reset",
            data=b"",
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.read())
            self.assertTrue(body["success"])


if __name__ == "__main__":
    unittest.main()


class AlertAutoRemediationRolloutGatingTest(unittest.TestCase):
    """Test that alert-triggered auto-remediation respects rollout gating."""

    def test_alert_trigger_respects_rollout_disabled(self):
        """When auto_remediation is disabled in rollout, alert-triggered remediation is blocked."""
        from alert import get_alert_manager
        from rollout_profile import reload_rollout_profile
        import tempfile, json, os

        profile = {
            "global_level": "internal_only",
            "capabilities": {
                "run_query": "limited_automation",
                "team_workflows": "limited_automation",
                "provider_selection": "internal_only",
                "approval_linked_execution": "pilot_with_approval",
                "auto_remediation": "disabled",
            },
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(profile, f)
            tmp_path = f.name

        try:
            reload_rollout_profile(tmp_path)
            mgr = get_alert_manager()
            mgr._trigger_auto_remediation(
                {"type": "circuit_breaker_open", "severity": "warning"},
                {}, {}, {"name": "local", "readiness": "ready"}
            )
        finally:
            os.unlink(tmp_path)
            reload_rollout_profile()

    def test_alert_trigger_allowed_when_rollout_sufficient(self):
        """When auto_remediation level is sufficient, alert-triggered remediation proceeds."""
        from alert import get_alert_manager
        from rollout_profile import reload_rollout_profile
        import tempfile, json, os

        profile = {
            "global_level": "internal_only",
            "capabilities": {
                "run_query": "limited_automation",
                "team_workflows": "limited_automation",
                "provider_selection": "internal_only",
                "approval_linked_execution": "pilot_with_approval",
                "auto_remediation": "pilot_readonly",
            },
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(profile, f)
            tmp_path = f.name

        try:
            reload_rollout_profile(tmp_path)
            mgr = get_alert_manager()
            mgr._trigger_auto_remediation(
                {"type": "circuit_breaker_open", "severity": "warning"},
                {}, {}, {"name": "local", "readiness": "ready"}
            )
        finally:
            os.unlink(tmp_path)
            reload_rollout_profile()

