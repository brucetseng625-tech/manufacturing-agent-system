"""Tests for alert lifecycle: acknowledgement, resolution, and auto-resolve."""

import json
import threading
import time
import unittest
from http.server import HTTPServer
import urllib.request
from unittest.mock import patch

from alert import AlertManager, get_alert_manager


class AlertLifecycleTest(unittest.TestCase):
    """Tests for alert ID generation and lifecycle state transitions."""

    def setUp(self):
        self.mgr = AlertManager()
        self.mgr._send_webhook = lambda url, payload: True

    def _trigger_alert(self):
        """Helper: trigger an alert with mock config."""
        with patch("alert.get_config_value") as mock_cfg:
            mock_cfg.side_effect = lambda key, default: {
                "alerts.enabled": True,
                "alerts.webhook_url": "http://example.com/webhook",
                "alerts.cooldown_seconds": 0,
                "alerts.auto_resolve_seconds": 0,
            }.get(key, default)
            return self.mgr.check_and_notify(
                "unhealthy", {"is_degraded": True},
                {"status": "unreachable"}, {"readiness": "disabled"}
            )

    def test_alert_has_unique_id(self):
        """Each alert should get a unique ID."""
        result = self._trigger_alert()
        self.assertIsNotNone(result)
        self.assertIn("alert_id", result)
        self.assertTrue(result["alert_id"].startswith("alert-"))

    def test_alert_ids_are_sequential(self):
        """Alert IDs should increment monotonically."""
        r1 = self._trigger_alert()
        r2 = self._trigger_alert()
        r3 = self._trigger_alert()
        self.assertEqual(r1["alert_id"], "alert-1")
        self.assertEqual(r2["alert_id"], "alert-2")
        self.assertEqual(r3["alert_id"], "alert-3")

    def test_alert_log_entry_has_status(self):
        """Alert log entries should include status field."""
        self._trigger_alert()
        log = self.mgr.get_alert_log()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["status"], "firing")
        self.assertIn("id", log[0])
        self.assertIn("acknowledged_at", log[0])
        self.assertIn("resolved_at", log[0])

    def test_acknowledge_alert(self):
        """Acknowledging an alert should update its status."""
        self._trigger_alert()
        result = self.mgr.acknowledge("alert-1")
        self.assertEqual(result["status"], "acknowledged")
        self.assertEqual(result["id"], "alert-1")
        self.assertIsNotNone(result["acknowledged_at"])

        # Verify log entry updated
        log = self.mgr.get_alert_log()
        self.assertEqual(log[0]["status"], "acknowledged")

    def test_resolve_alert(self):
        """Resolving an alert should update its status."""
        self._trigger_alert()
        self.mgr.acknowledge("alert-1")
        result = self.mgr.resolve("alert-1")
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["id"], "alert-1")
        self.assertIsNotNone(result["resolved_at"])

        log = self.mgr.get_alert_log()
        self.assertEqual(log[0]["status"], "resolved")

    def test_resolve_directly_from_firing(self):
        """Should be able to resolve directly from firing state."""
        self._trigger_alert()
        result = self.mgr.resolve("alert-1")
        self.assertEqual(result["status"], "resolved")

    def test_double_acknowledge_returns_error(self):
        """Acknowledging an already-acknowledged alert should return error."""
        self._trigger_alert()
        self.mgr.acknowledge("alert-1")
        result = self.mgr.acknowledge("alert-1")
        self.assertEqual(result["error"], "alert_already_acknowledged")

    def test_double_resolve_returns_error(self):
        """Resolving an already-resolved alert should return error."""
        self._trigger_alert()
        self.mgr.resolve("alert-1")
        result = self.mgr.resolve("alert-1")
        self.assertEqual(result["error"], "alert_already_resolved")

    def test_acknowledge_resolved_returns_error(self):
        """Acknowledging a resolved alert should return error."""
        self._trigger_alert()
        self.mgr.resolve("alert-1")
        result = self.mgr.acknowledge("alert-1")
        self.assertEqual(result["error"], "alert_already_resolved")

    def test_acknowledge_not_found(self):
        """Acknowledging a non-existent alert should return error."""
        result = self.mgr.acknowledge("alert-999")
        self.assertEqual(result["error"], "alert_not_found")

    def test_resolve_not_found(self):
        """Resolving a non-existent alert should return error."""
        result = self.mgr.resolve("alert-999")
        self.assertEqual(result["error"], "alert_not_found")

    def test_find_alert_returns_entry(self):
        """find_alert should return the alert entry."""
        self._trigger_alert()
        alert = self.mgr.find_alert("alert-1")
        self.assertIsNotNone(alert)
        self.assertEqual(alert["id"], "alert-1")
        self.assertEqual(alert["type"], "system_unhealthy")

    def test_find_alert_not_found(self):
        """find_alert should return None for missing alerts."""
        result = self.mgr.find_alert("alert-999")
        self.assertIsNone(result)

    def test_get_all_alerts(self):
        """get_all_alerts should return all entries."""
        self._trigger_alert()
        self._trigger_alert()
        all_alerts = self.mgr.get_all_alerts()
        self.assertEqual(len(all_alerts), 2)

    def test_reset_clears_counter(self):
        """Reset should clear the alert counter."""
        self._trigger_alert()
        self._trigger_alert()
        self.mgr.reset()
        # After reset, new alert should start from alert-1
        result = self._trigger_alert()
        self.assertEqual(result["alert_id"], "alert-1")


class AutoResolveTest(unittest.TestCase):
    """Tests for auto-resolve functionality."""

    def setUp(self):
        self.mgr = AlertManager()
        self.mgr._send_webhook = lambda url, payload: True

    def _trigger_alert_with_auto_resolve(self, seconds=1):
        with patch("alert.get_config_value") as mock_cfg:
            mock_cfg.side_effect = lambda key, default: {
                "alerts.enabled": True,
                "alerts.webhook_url": "http://example.com/webhook",
                "alerts.cooldown_seconds": 0,
                "alerts.auto_resolve_seconds": seconds,
            }.get(key, default)
            return self.mgr.check_and_notify(
                "unhealthy", {"is_degraded": True},
                {"status": "unreachable"}, {"readiness": "disabled"}
            )

    def test_auto_resolve_transitions_to_resolved(self):
        """Alert should auto-resolve after configured seconds."""
        self._trigger_alert_with_auto_resolve(seconds=1)
        # Initially firing
        alert = self.mgr.find_alert("alert-1")
        self.assertEqual(alert["status"], "firing")

        # Wait for auto-resolve
        time.sleep(1.5)
        alert = self.mgr.find_alert("alert-1")
        self.assertEqual(alert["status"], "resolved")
        self.assertTrue(alert.get("auto_resolved"))

    def test_auto_resolve_does_not_override_manual(self):
        """If alert already acknowledged, auto-resolve should not fire."""
        self._trigger_alert_with_auto_resolve(seconds=1)
        self.mgr.acknowledge("alert-1")

        # Wait past auto-resolve time
        time.sleep(1.5)
        alert = self.mgr.find_alert("alert-1")
        # Should remain acknowledged (not overwritten by auto-resolve)
        self.assertEqual(alert["status"], "acknowledged")


class ServerAlertsEndpointsTest(unittest.TestCase):
    """Integration tests for new alert lifecycle endpoints."""

    @classmethod
    def setUpClass(cls):
        from server import AgentHandler
        cls.server = HTTPServer(("127.0.0.1", 0), AgentHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()
        time.sleep(0.1)

        # Trigger a test alert
        mgr = get_alert_manager()
        mgr.reset()
        mgr._send_webhook = lambda url, payload: True
        mgr._alert_counter = 0
        mgr._alert_log.append({
            "id": "alert-1",
            "type": "system_unhealthy",
            "severity": "critical",
            "status": "firing",
            "sent": True,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "acknowledged_at": None,
            "resolved_at": None,
        })

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=1)

    def _get(self, path):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}")
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())

    def _post(self, path):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=b"",
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())

    def test_get_alerts_list(self):
        """GET /alerts should list all alerts with summary."""
        status, body = self._get("/alerts")
        self.assertEqual(status, 200)
        self.assertIn("total", body)
        self.assertIn("by_status", body)
        self.assertIn("alerts", body)
        self.assertGreaterEqual(body["total"], 1)

    def test_get_alerts_list_with_status_filter(self):
        """GET /alerts?status=firing should filter by status."""
        status, body = self._get("/alerts?status=firing")
        self.assertEqual(status, 200)
        for a in body["alerts"]:
            self.assertEqual(a["status"], "firing")

    def test_get_alert_detail(self):
        """GET /alerts/alert-1 should return specific alert."""
        status, body = self._get("/alerts/alert-1")
        self.assertEqual(status, 200)
        self.assertEqual(body["id"], "alert-1")
        self.assertEqual(body["type"], "system_unhealthy")

    def test_get_alert_detail_not_found(self):
        """GET /alerts/alert-999 should return 404."""
        try:
            self._get("/alerts/alert-999")
            self.fail("Expected 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)

    def test_acknowledge_alert(self):
        """POST /alerts/alert-1/acknowledge should acknowledge."""
        status, body = self._post("/alerts/alert-1/acknowledge")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "acknowledged")
        self.assertIn("acknowledged_at", body)

    def test_resolve_alert(self):
        """POST /alerts/alert-1/resolve should resolve."""
        # Reset alert-1 to firing for this test
        from alert import get_alert_manager
        mgr = get_alert_manager()
        with mgr._lock:
            for entry in mgr._alert_log:
                if entry["id"] == "alert-1":
                    entry["status"] = "firing"
                    entry["acknowledged_at"] = None
                    entry["resolved_at"] = None
                    break
        status, body = self._post("/alerts/alert-1/resolve")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "resolved")
        self.assertIn("resolved_at", body)

    def test_acknowledge_already_resolved(self):
        """POST /alerts/alert-1/acknowledge on resolved should return 409."""
        # Ensure resolved first
        try:
            self._post("/alerts/alert-1/resolve")
        except Exception:
            pass
        try:
            self._post("/alerts/alert-1/acknowledge")
            self.fail("Expected 409")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 409)

    def test_resolve_not_found(self):
        """POST /alerts/alert-999/resolve should return 404."""
        try:
            self._post("/alerts/alert-999/resolve")
            self.fail("Expected 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)


if __name__ == "__main__":
    unittest.main()
