"""Tests for incident_report — incident report generation."""

import unittest
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from incident_report import (
    generate_incident_report,
    _filter_alerts_for_report,
    _build_summary,
    _build_provider_info,
    _build_recommendations,
)


class IncidentReportTest(unittest.TestCase):
    """Tests for incident report generation."""

    def test_generate_report_has_required_fields(self):
        """Report should have all required top-level fields."""
        report = generate_incident_report()
        required_fields = [
            "report_id", "generated_at", "window_minutes",
            "system_status", "incident_summary", "related_alerts",
            "related_audit", "audit_summary", "timeline_preview",
            "affected_provider", "resolution_status", "recommendations",
        ]
        for field in required_fields:
            self.assertIn(field, report, f"Missing field: {field}")

    def test_report_id_is_string(self):
        """report_id should be a string."""
        report = generate_incident_report()
        self.assertIsInstance(report["report_id"], str)
        self.assertTrue(report["report_id"].startswith("incident-"))

    def test_generated_at_is_timestamp(self):
        """generated_at should be an ISO timestamp."""
        report = generate_incident_report()
        self.assertIn("T", report["generated_at"])
        self.assertTrue(report["generated_at"].endswith("Z"))

    def test_window_minutes_defaults_to_60(self):
        """window_minutes should default to 60."""
        report = generate_incident_report()
        self.assertEqual(report["window_minutes"], 60)

    def test_window_minutes_custom(self):
        """window_minutes should accept custom values."""
        report = generate_incident_report(window_minutes=30)
        self.assertEqual(report["window_minutes"], 30)

    def test_system_status_has_overall(self):
        """system_status should have overall field."""
        report = generate_incident_report()
        self.assertIn("overall", report["system_status"])
        self.assertIn(report["system_status"]["overall"],
                      ("ok", "degraded", "unhealthy", "unknown"))

    def test_resolution_status_is_valid(self):
        """resolution_status should be one of: resolved, degraded, unresolved."""
        report = generate_incident_report()
        self.assertIn(report["resolution_status"],
                      ("resolved", "degraded", "unresolved"))

    def test_related_alerts_is_list(self):
        """related_alerts should be a list."""
        report = generate_incident_report()
        self.assertIsInstance(report["related_alerts"], list)

    def test_related_audit_is_list(self):
        """related_audit should be a list."""
        report = generate_incident_report()
        self.assertIsInstance(report["related_audit"], list)

    def test_affected_provider_has_name(self):
        """affected_provider should have name field."""
        report = generate_incident_report()
        self.assertIn("name", report["affected_provider"])

    def test_recommendations_is_list(self):
        """recommendations should be a list."""
        report = generate_incident_report()
        self.assertIsInstance(report["recommendations"], list)
        self.assertGreater(len(report["recommendations"]), 0)

    def test_incident_summary_is_string(self):
        """incident_summary should be a non-empty string."""
        report = generate_incident_report()
        self.assertIsInstance(report["incident_summary"], str)
        self.assertGreater(len(report["incident_summary"]), 0)

    def test_audit_summary_has_total(self):
        """audit_summary should have total_entries."""
        report = generate_incident_report()
        self.assertIn("total_entries", report["audit_summary"])

    def test_timeline_preview_is_list(self):
        """timeline_preview should be a list."""
        report = generate_incident_report()
        self.assertIsInstance(report["timeline_preview"], list)


class IncidentReportHelpersTest(unittest.TestCase):
    """Tests for helper functions."""

    def test_filter_alerts_empty(self):
        """Empty alerts should return empty list."""
        result = _filter_alerts_for_report([])
        self.assertEqual(result, [])

    def test_filter_alerts_formats(self):
        """Alerts should be formatted correctly."""
        alerts = [{
            "alert_id": "alert-1",
            "alert_type": "system_unhealthy",
            "status": "firing",
            "fired_at": "2026-05-09T12:00:00Z",
            "acknowledged_at": None,
            "resolved_at": None,
        }]
        result = _filter_alerts_for_report(alerts)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["alert_id"], "alert-1")
        self.assertEqual(result[0]["status"], "firing")

    def test_build_summary_empty(self):
        """Summary with minimal data should still work."""
        summary = _build_summary(
            {"system": "ok", "provider": {"name": "local"}, "degradation": {}},
            [], []
        )
        self.assertIsInstance(summary, str)
        self.assertIn("System status: ok", summary)

    def test_build_summary_with_alerts(self):
        """Summary should mention active alerts."""
        alerts = [{"status": "firing"}, {"status": "firing"}, {"status": "resolved"}]
        summary = _build_summary(
            {"system": "unhealthy", "provider": {"name": "http_readonly"}, "degradation": {}},
            alerts, []
        )
        self.assertIn("2 active alert(s)", summary)

    def test_build_summary_with_denied_ops(self):
        """Summary should mention denied operations."""
        audit_entries = [{"result": "denied"}, {"result": "success"}, {"result": "denied"}]
        summary = _build_summary(
            {"system": "ok", "provider": {"name": "local"}, "degradation": {}},
            [], audit_entries
        )
        self.assertIn("2 guarded operation(s) denied", summary)

    def test_build_provider_info(self):
        """Provider info should extract relevant fields."""
        system_status = {
            "provider": {"name": "auto", "readiness": "ready",
                         "capabilities": ["read"], "default_mode": "auto"},
            "health": {"status": "ok"},
            "degradation": {"active_path": "live", "reason": ""},
        }
        info = _build_provider_info(system_status)
        self.assertEqual(info["name"], "auto")
        self.assertEqual(info["readiness"], "ready")
        self.assertEqual(info["health_status"], "ok")
        self.assertEqual(info["active_path"], "live")
        self.assertEqual(info["default_mode"], "auto")

    def test_build_recommendations_healthy(self):
        """Healthy system should recommend no action."""
        recs = _build_recommendations({}, False, True)
        self.assertIn("System is healthy", " ".join(recs))

    def test_build_recommendations_unresolved(self):
        """Unresolved should recommend reviewing alerts."""
        recs = _build_recommendations({}, False, False)
        self.assertTrue(any("alert" in r.lower() for r in recs))


if __name__ == "__main__":
    unittest.main()
