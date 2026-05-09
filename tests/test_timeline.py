"""Tests for P9-3 Incident timeline view."""

import json
import os
import threading
import time
import unittest
from http.server import HTTPServer
import urllib.request

from alert import get_alert_manager
from timeline import build_timeline, timeline_summary


class TimelineBuildTest(unittest.TestCase):
    """Tests for timeline aggregation logic."""

    def test_returns_list(self):
        """build_timeline must return a list."""
        result = build_timeline()
        self.assertIsInstance(result, list)

    def test_events_have_required_fields(self):
        """Each event must have timestamp, event_type, summary."""
        result = build_timeline()
        for e in result:
            self.assertIn("timestamp", e)
            self.assertIn("event_type", e)
            self.assertIn("summary", e)
            self.assertIn("detail", e)

    def test_event_types_are_valid(self):
        """Event types must be one of run, alert, access."""
        result = build_timeline()
        valid_types = {"run", "alert", "access"}
        for e in result:
            self.assertIn(e["event_type"], valid_types)

    def test_filter_by_event_type(self):
        """Filtering by event_type must only return matching events."""
        for et in ("run", "alert", "access"):
            result = build_timeline(event_type=et)
            for e in result:
                self.assertEqual(e["event_type"], et)

    def test_respects_last_n_limit(self):
        """Must return at most last_n events."""
        result = build_timeline(last_n=5)
        self.assertLessEqual(len(result), 5)

    def test_newest_first_order(self):
        """Events must be sorted newest-first by timestamp."""
        result = build_timeline(last_n=20)
        timestamps = [e["timestamp"] for e in result if e["timestamp"]]
        # Check it's descending
        for i in range(len(timestamps) - 1):
            self.assertGreaterEqual(timestamps[i], timestamps[i + 1])

    def test_timeline_summary_with_events(self):
        """summary must show count and breakdown."""
        events = build_timeline(last_n=10)
        s = timeline_summary(events)
        self.assertIn("events", s)
        self.assertIn("Runs:", s)
        self.assertIn("Alerts:", s)
        self.assertIn("Access:", s)

    def test_timeline_summary_empty(self):
        """summary for empty list must say no events."""
        s = timeline_summary([])
        self.assertIn("No timeline events found", s)


class TimelineWithAlertsTest(unittest.TestCase):
    """Tests that timeline includes alert events."""

    def setUp(self):
        self.mgr = get_alert_manager()
        self.mgr.reset()
        self.mgr._send_webhook = lambda url, payload: True
        # Manually add an alert to the log
        from unittest.mock import patch
        with patch("alert.get_config_value") as mock_cfg:
            mock_cfg.side_effect = lambda key, default: {
                "alerts.enabled": True,
                "alerts.webhook_url": "http://example.com/webhook",
                "alerts.cooldown_seconds": 0,
                "alerts.auto_resolve_seconds": 0,
            }.get(key, default)
            self.mgr.check_and_notify(
                "unhealthy", {"is_degraded": True},
                {"status": "unreachable"}, {"readiness": "disabled"}
            )

    def test_timeline_contains_alert_event(self):
        """Timeline must include alert events."""
        events = build_timeline(event_type="alert")
        self.assertGreater(len(events), 0)
        for e in events:
            self.assertEqual(e["event_type"], "alert")
            self.assertIn("alert_id", e)
            self.assertIsNotNone(e["alert_id"])

    def test_alert_event_has_alert_id(self):
        """Alert events must have alert_id field."""
        events = build_timeline(event_type="alert")
        for e in events:
            if e.get("alert_id"):
                self.assertTrue(e["alert_id"].startswith("alert-"))


class ServerTimelineEndpointTest(unittest.TestCase):
    """Integration tests for GET /timeline endpoint."""

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

    def _get(self, path):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}")
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())

    def test_timeline_endpoint_responds(self):
        """GET /timeline must return 200."""
        status, body = self._get("/timeline")
        self.assertEqual(status, 200)

    def test_timeline_has_total_field(self):
        """Response must include total count."""
        status, body = self._get("/timeline")
        self.assertIn("total", body)
        self.assertIsInstance(body["total"], int)

    def test_timeline_has_events_list(self):
        """Response must include events list."""
        status, body = self._get("/timeline")
        self.assertIn("events", body)
        self.assertIsInstance(body["events"], list)

    def test_timeline_has_summary(self):
        """Response must include summary text."""
        status, body = self._get("/timeline")
        self.assertIn("summary", body)
        self.assertIsInstance(body["summary"], str)

    def test_timeline_filter_by_type(self):
        """GET /timeline?type=alert must filter."""
        status, body = self._get("/timeline?type=alert")
        self.assertEqual(status, 200)
        for e in body["events"]:
            self.assertEqual(e["event_type"], "alert")

    def test_timeline_filter_by_run_type(self):
        """GET /timeline?type=run must filter."""
        status, body = self._get("/timeline?type=run")
        self.assertEqual(status, 200)
        for e in body["events"]:
            self.assertEqual(e["event_type"], "run")

    def test_timeline_last_param(self):
        """GET /timeline?last=5 must limit results."""
        status, body = self._get("/timeline?last=5")
        self.assertEqual(status, 200)
        self.assertLessEqual(body["total"], 5)
        self.assertLessEqual(len(body["events"]), 5)


if __name__ == "__main__":
    unittest.main()
