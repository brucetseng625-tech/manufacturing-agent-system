"""Tests for pilot_checklist module."""

import unittest
from unittest.mock import patch, MagicMock
import pilot_checklist


class TestGetChecklist(unittest.TestCase):

    @patch("pilot_checklist._safety_checks")
    @patch("pilot_checklist._observability_checks")
    @patch("pilot_checklist._workflow_checks")
    def test_checklist_has_three_categories(self, mock_wf, mock_ob, mock_sf):
        mock_sf.return_value = [{"id": "SC-01", "category": pilot_checklist.SAFETY,
                                  "description": "test", "status": "ready", "detail": {}}]
        mock_ob.return_value = [{"id": "OB-01", "category": pilot_checklist.OBSERVABILITY,
                                  "description": "test", "status": "ready", "detail": {}}]
        mock_wf.return_value = [{"id": "WF-01", "category": pilot_checklist.WORKFLOW,
                                  "description": "test", "status": "ready", "detail": {}}]
        checklist = pilot_checklist.get_checklist()
        self.assertEqual(len(checklist), 3)
        categories = {item["category"] for item in checklist}
        self.assertEqual(categories, {pilot_checklist.SAFETY,
                                       pilot_checklist.OBSERVABILITY,
                                       pilot_checklist.WORKFLOW})


class TestSafetyChecks(unittest.TestCase):

    @patch("data_source.get_system_status")
    def test_sc01_circuit_breaker_closed(self, mock_status):
        mock_status.return_value = {"provider": {"circuit_breaker": "closed"}}
        items = pilot_checklist._safety_checks()
        sc01 = [i for i in items if i["id"] == "SC-01"][0]
        self.assertEqual(sc01["status"], "ready")
        self.assertEqual(sc01["detail"]["circuit_breaker_state"], "closed")

    @patch("data_source.get_system_status")
    def test_sc01_circuit_breaker_open(self, mock_status):
        mock_status.return_value = {"provider": {"circuit_breaker": "open"}}
        items = pilot_checklist._safety_checks()
        sc01 = [i for i in items if i["id"] == "SC-01"][0]
        self.assertEqual(sc01["status"], "blocked")

    @patch("automation_policy.get_automation_policy_status")
    def test_sc02_policy_configured(self, mock_policy):
        mock_policy.return_value = {"enabled": True}
        items = pilot_checklist._safety_checks()
        sc02 = [i for i in items if i["id"] == "SC-02"][0]
        self.assertEqual(sc02["status"], "ready")

    @patch("guardrails.get_guardrails_status")
    def test_sc03_guardrails_defined(self, mock_guards):
        mock_guards.return_value = {"rules": ["config:reload", "policy:reload"]}
        items = pilot_checklist._safety_checks()
        sc03 = [i for i in items if i["id"] == "SC-03"][0]
        self.assertEqual(sc03["status"], "ready")


class TestObservabilityChecks(unittest.TestCase):

    @patch("alert.get_alert_manager")
    def test_ob01_no_firing_alerts(self, mock_mgr):
        mock_alert_mgr = MagicMock()
        mock_alert_mgr.list_alerts.return_value = []
        mock_mgr.return_value = mock_alert_mgr
        items = pilot_checklist._observability_checks()
        ob01 = [i for i in items if i["id"] == "OB-01"][0]
        self.assertEqual(ob01["status"], "ready")
        self.assertEqual(ob01["detail"]["firing_count"], 0)

    @patch("alert.get_alert_manager")
    def test_ob01_firing_alerts(self, mock_mgr):
        mock_alert_mgr = MagicMock()
        mock_alert_mgr.list_alerts.return_value = [{"status": "firing"}]
        mock_mgr.return_value = mock_alert_mgr
        items = pilot_checklist._observability_checks()
        ob01 = [i for i in items if i["id"] == "OB-01"][0]
        self.assertEqual(ob01["status"], "pending")

    def test_ob02_audit_chain_writable(self):
        items = pilot_checklist._observability_checks()
        ob02 = [i for i in items if i["id"] == "OB-02"][0]
        self.assertEqual(ob02["status"], "ready")

    def test_ob03_receipts_available(self):
        items = pilot_checklist._observability_checks()
        ob03 = [i for i in items if i["id"] == "OB-03"][0]
        self.assertEqual(ob03["status"], "ready")

    def test_ob04_incident_closure_available(self):
        items = pilot_checklist._observability_checks()
        ob04 = [i for i in items if i["id"] == "OB-04"][0]
        self.assertEqual(ob04["status"], "ready")


class TestWorkflowChecks(unittest.TestCase):

    def test_wf01_approval_queue_available(self):
        items = pilot_checklist._workflow_checks()
        wf01 = [i for i in items if i["id"] == "WF-01"][0]
        self.assertEqual(wf01["status"], "ready")

    def test_wf02_provider_ready(self):
        with patch("data_source.get_provider_status") as mock_prov:
            mock_prov.return_value = {"readiness": "ready", "name": "local"}
            items = pilot_checklist._workflow_checks()
        wf02 = [i for i in items if i["id"] == "WF-02"][0]
        self.assertEqual(wf02["status"], "ready")

    def test_wf03_system_health(self):
        with patch("data_source.get_system_status") as mock_status:
            mock_status.return_value = {"overall_status": "ok"}
            items = pilot_checklist._workflow_checks()
        wf03 = [i for i in items if i["id"] == "WF-03"][0]
        self.assertEqual(wf03["status"], "ready")

    def test_wf04_rollback_available(self):
        items = pilot_checklist._workflow_checks()
        wf04 = [i for i in items if i["id"] == "WF-04"][0]
        self.assertEqual(wf04["status"], "ready")


class TestGetChecklistSummary(unittest.TestCase):

    def test_summary_all_ready(self):
        checklist = [
            {"id": "SC-01", "category": "safety", "status": "ready"},
            {"id": "OB-01", "category": "observability", "status": "ready"},
            {"id": "WF-01", "category": "workflow", "status": "ready"},
        ]
        summary = pilot_checklist.get_checklist_summary(checklist)
        self.assertEqual(summary["total"], 3)
        self.assertTrue(summary["all_ready"])
        self.assertEqual(summary["by_status"]["ready"], 3)

    def test_summary_not_all_ready(self):
        checklist = [
            {"id": "SC-01", "category": "safety", "status": "ready"},
            {"id": "OB-01", "category": "observability", "status": "pending"},
            {"id": "WF-01", "category": "workflow", "status": "blocked"},
        ]
        summary = pilot_checklist.get_checklist_summary(checklist)
        self.assertFalse(summary["all_ready"])
        self.assertEqual(summary["by_status"]["pending"], 1)
        self.assertEqual(summary["by_status"]["blocked"], 1)

    def test_summary_by_category(self):
        checklist = [
            {"id": "SC-01", "category": "safety", "status": "ready"},
            {"id": "SC-02", "category": "safety", "status": "ready"},
            {"id": "OB-01", "category": "observability", "status": "ready"},
        ]
        summary = pilot_checklist.get_checklist_summary(checklist)
        self.assertEqual(summary["by_category"]["safety"], 2)
        self.assertEqual(summary["by_category"]["observability"], 1)

    def test_summary_includes_timestamp(self):
        checklist = []
        summary = pilot_checklist.get_checklist_summary(checklist)
        self.assertIn("checked_at", summary)


if __name__ == "__main__":
    unittest.main()
