"""Tests for rollback_eligibility — rollback eligibility analysis for audit entries."""

import unittest
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rollback_eligibility import (
    analyze_entry,
    query_rollback_eligibility,
    get_rollback_summary,
    _ROLLBACK_RULES,
    _DEFAULT_RULE,
)


class RollbackEligibilityRulesTest(unittest.TestCase):
    """Test that rollback rules are well-defined for all known action types."""

    def test_all_known_actions_have_rules(self):
        """Every known action type should have a rollback rule."""
        known_actions = {
            "config:reload", "policy:reload", "provider:select",
            "alerts:reset", "approval:created", "approval:approved",
            "approval:rejected", "approval:reset", "auto_remediation",
            "automation:policy_denied",
        }
        for action in known_actions:
            self.assertIn(action, _ROLLBACK_RULES, f"Missing rule for: {action}")

    def test_rules_have_required_fields(self):
        """Each rule must have eligible, reason, category, requires_context, related_action."""
        required_fields = ["eligible", "reason", "category", "requires_context", "related_action"]
        for action, rule in _ROLLBACK_RULES.items():
            for field in required_fields:
                self.assertIn(field, rule, f"Rule for {action} missing field: {field}")

    def test_default_rule_exists(self):
        """Unknown actions should fall back to default rule."""
        self.assertIn("eligible", _DEFAULT_RULE)
        self.assertFalse(_DEFAULT_RULE["eligible"])


class AnalyzeEntryTest(unittest.TestCase):
    """Test analyze_entry for various action types."""

    def test_config_reload_not_eligible(self):
        """config:reload should not be rollbackable."""
        entry = {
            "timestamp": "2026-05-09T12:00:00Z",
            "action": "config:reload",
            "operator": "api",
            "source_ip": "127.0.0.1",
            "details": {"source": "default"},
            "result": "success",
            "run_id": None,
        }
        result = analyze_entry(entry)
        self.assertFalse(result["eligible"])
        self.assertEqual(result["action"], "config:reload")
        self.assertEqual(result["category"], "guarded_operation")

    def test_policy_reload_not_eligible(self):
        """policy:reload should not be rollbackable."""
        entry = {
            "timestamp": "2026-05-09T12:00:00Z",
            "action": "policy:reload",
            "operator": "api",
            "source_ip": "127.0.0.1",
            "details": {"source": "default"},
            "result": "success",
            "run_id": None,
        }
        result = analyze_entry(entry)
        self.assertFalse(result["eligible"])

    def test_alerts_reset_not_eligible(self):
        """alerts:reset should not be rollbackable."""
        entry = {
            "timestamp": "2026-05-09T12:00:00Z",
            "action": "alerts:reset",
            "operator": "api",
            "source_ip": "127.0.0.1",
            "details": {},
            "result": "success",
            "run_id": None,
        }
        result = analyze_entry(entry)
        self.assertFalse(result["eligible"])

    def test_approval_created_not_eligible(self):
        """approval:created is just a queue entry, not executable."""
        entry = {
            "timestamp": "2026-05-09T12:00:00Z",
            "action": "approval:created",
            "operator": "api",
            "source_ip": "127.0.0.1",
            "details": {"operation": "config:reload", "reason": "needs approval"},
            "result": "pending",
            "run_id": None,
        }
        result = analyze_entry(entry)
        self.assertFalse(result["eligible"])

    def test_approval_rejected_not_eligible(self):
        """approval:rejected means operation was never executed."""
        entry = {
            "timestamp": "2026-05-09T12:00:00Z",
            "action": "approval:rejected",
            "operator": "operator",
            "source_ip": "127.0.0.1",
            "details": {"operation": "config:reload", "reason": "not approved"},
            "result": "rejected",
            "run_id": None,
        }
        result = analyze_entry(entry)
        self.assertFalse(result["eligible"])

    def test_approval_reset_not_eligible(self):
        """approval:reset is an administrative action."""
        entry = {
            "timestamp": "2026-05-09T12:00:00Z",
            "action": "approval:reset",
            "operator": "api",
            "source_ip": "127.0.0.1",
            "details": {},
            "result": "success",
            "run_id": None,
        }
        result = analyze_entry(entry)
        self.assertFalse(result["eligible"])

    def test_policy_denied_not_eligible(self):
        """automation:policy_denied means operation was blocked."""
        entry = {
            "timestamp": "2026-05-09T12:00:00Z",
            "action": "automation:policy_denied",
            "operator": "system",
            "source_ip": "127.0.0.1",
            "details": {"action": "auto_remediation.alerts:reset"},
            "result": "denied",
            "run_id": None,
        }
        result = analyze_entry(entry)
        self.assertFalse(result["eligible"])

    def test_approval_approved_provider_select_eligible(self):
        """approval:approved for provider:select should be eligible."""
        entry = {
            "timestamp": "2026-05-09T12:00:00Z",
            "action": "approval:approved",
            "operator": "operator",
            "source_ip": "127.0.0.1",
            "details": {"operation": "provider:select", "approval_id": "approval-1"},
            "result": "success",
            "run_id": None,
        }
        result = analyze_entry(entry)
        self.assertTrue(result["eligible"])
        self.assertEqual(result["rollback_action"], "provider:select")

    def test_approval_approved_unknown_operation(self):
        """approval:approved for unknown operation has generic reason."""
        entry = {
            "timestamp": "2026-05-09T12:00:00Z",
            "action": "approval:approved",
            "operator": "operator",
            "source_ip": "127.0.0.1",
            "details": {"operation": "custom_action", "approval_id": "approval-1"},
            "result": "success",
            "run_id": None,
        }
        result = analyze_entry(entry)
        self.assertTrue(result["eligible"])
        self.assertIsNone(result["rollback_action"])

    def test_auto_remediation_dry_run_not_eligible(self):
        """auto_remediation in dry_run mode has no side effects."""
        entry = {
            "timestamp": "2026-05-09T12:00:00Z",
            "action": "auto_remediation",
            "operator": "system",
            "source_ip": "127.0.0.1",
            "details": {"hook": "test", "trigger": "test", "action": "alerts:reset", "dry_run": True},
            "result": "dry_run",
            "run_id": None,
        }
        result = analyze_entry(entry)
        self.assertFalse(result["eligible"])

    def test_auto_remediation_alerts_reset_not_eligible(self):
        """auto_remediation of alerts:reset is not rollbackable."""
        entry = {
            "timestamp": "2026-05-09T12:00:00Z",
            "action": "auto_remediation",
            "operator": "system",
            "source_ip": "127.0.0.1",
            "details": {"hook": "test", "trigger": "test", "action": "alerts:reset", "dry_run": False},
            "result": "success",
            "run_id": None,
        }
        result = analyze_entry(entry)
        self.assertFalse(result["eligible"])

    def test_failed_result_not_eligible(self):
        """Failed operations should never be eligible."""
        entry = {
            "timestamp": "2026-05-09T12:00:00Z",
            "action": "config:reload",
            "operator": "api",
            "source_ip": "127.0.0.1",
            "details": {},
            "result": "failed",
            "run_id": None,
        }
        result = analyze_entry(entry)
        self.assertFalse(result["eligible"])

    def test_unknown_action_not_eligible(self):
        """Unknown actions should fall back to default rule."""
        entry = {
            "timestamp": "2026-05-09T12:00:00Z",
            "action": "mystery_action",
            "operator": "api",
            "source_ip": "127.0.0.1",
            "details": {},
            "result": "success",
            "run_id": None,
        }
        result = analyze_entry(entry)
        self.assertFalse(result["eligible"])
        self.assertEqual(result["category"], "unknown")

    def test_result_preserved_from_entry(self):
        """Result field should be preserved from the original entry."""
        entry = {
            "timestamp": "2026-05-09T12:00:00Z",
            "action": "config:reload",
            "operator": "api",
            "source_ip": "127.0.0.1",
            "details": {},
            "result": "success",
            "run_id": None,
        }
        result = analyze_entry(entry)
        self.assertEqual(result["result"], "success")
        self.assertEqual(result["operator"], "api")

    def test_details_summary_extracted(self):
        """Details summary should extract relevant fields."""
        entry = {
            "timestamp": "2026-05-09T12:00:00Z",
            "action": "approval:approved",
            "operator": "operator",
            "source_ip": "127.0.0.1",
            "details": {"operation": "provider:select", "approval_id": "a-1", "approved_by": "admin"},
            "result": "success",
            "run_id": None,
        }
        result = analyze_entry(entry)
        self.assertIn("operation", result["details_summary"])
        self.assertIn("approval_id", result["details_summary"])


class QueryRollbackEligibilityTest(unittest.TestCase):
    """Test query_rollback_eligibility with temp audit log."""

    def setUp(self):
        """Create a temp directory with a known audit log."""
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = os.path.join(self.tmpdir, "audit.jsonl")

        entries = [
            {"timestamp": "2026-05-09T12:00:00Z", "action": "config:reload", "operator": "api", "source_ip": "127.0.0.1", "details": {"source": "default"}, "result": "success", "run_id": None},
            {"timestamp": "2026-05-09T12:01:00Z", "action": "approval:created", "operator": "api", "source_ip": "127.0.0.1", "details": {"operation": "config:reload"}, "result": "pending", "run_id": None},
            {"timestamp": "2026-05-09T12:02:00Z", "action": "approval:approved", "operator": "operator", "source_ip": "127.0.0.1", "details": {"operation": "provider:select", "approval_id": "a-1"}, "result": "success", "run_id": None},
            {"timestamp": "2026-05-09T12:03:00Z", "action": "auto_remediation", "operator": "system", "source_ip": "127.0.0.1", "details": {"hook": "h1", "trigger": "test", "action": "alerts:reset", "dry_run": False}, "result": "success", "run_id": None},
            {"timestamp": "2026-05-09T12:04:00Z", "action": "automation:policy_denied", "operator": "system", "source_ip": "127.0.0.1", "details": {"action": "auto_remediation.alerts:reset"}, "result": "denied", "run_id": None},
        ]
        with open(self.log_path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    def test_query_returns_all_entries(self):
        """Should return all entries with analysis."""
        result = query_rollback_eligibility(limit=10, log_dir=self.tmpdir)
        self.assertEqual(result["total"], 5)
        self.assertEqual(len(result["entries"]), 5)

    def test_eligible_filter(self):
        """Should filter to only eligible entries."""
        result = query_rollback_eligibility(limit=10, eligible_filter=True, log_dir=self.tmpdir)
        for entry in result["entries"]:
            self.assertTrue(entry["eligible"])

    def test_ineligible_filter(self):
        """Should filter to only ineligible entries."""
        result = query_rollback_eligibility(limit=10, eligible_filter=False, log_dir=self.tmpdir)
        for entry in result["entries"]:
            self.assertFalse(entry["eligible"])

    def test_category_filter(self):
        """Should filter by category."""
        result = query_rollback_eligibility(limit=10, category_filter="automation", log_dir=self.tmpdir)
        for entry in result["entries"]:
            self.assertEqual(entry["category"], "automation")

    def test_summary_counts(self):
        """Summary should have correct counts."""
        result = query_rollback_eligibility(limit=10, log_dir=self.tmpdir)
        summary = result["summary"]
        self.assertEqual(summary["total_analyzed"], 5)
        self.assertGreater(summary["eligible_count"], 0)
        self.assertGreater(summary["ineligible_count"], 0)

    def test_pagination(self):
        """Should respect limit and offset."""
        result1 = query_rollback_eligibility(limit=2, offset=0, log_dir=self.tmpdir)
        result2 = query_rollback_eligibility(limit=2, offset=2, log_dir=self.tmpdir)
        self.assertEqual(len(result1["entries"]), 2)
        self.assertEqual(len(result2["entries"]), 2)
        # Different entries
        self.assertNotEqual(result1["entries"][0]["timestamp"], result2["entries"][0]["timestamp"])

    def test_empty_log(self):
        """Should handle empty audit log gracefully."""
        empty_dir = tempfile.mkdtemp()
        result = query_rollback_eligibility(limit=10, log_dir=empty_dir)
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["entries"], [])


class GetRollbackSummaryTest(unittest.TestCase):
    """Test get_rollback_summary."""

    def setUp(self):
        """Create a temp directory with audit log."""
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = os.path.join(self.tmpdir, "audit.jsonl")

        entries = [
            {"timestamp": "2026-05-09T12:00:00Z", "action": "config:reload", "operator": "api", "source_ip": "127.0.0.1", "details": {}, "result": "success", "run_id": None},
            {"timestamp": "2026-05-09T12:01:00Z", "action": "config:reload", "operator": "api", "source_ip": "127.0.0.1", "details": {}, "result": "success", "run_id": None},
            {"timestamp": "2026-05-09T12:02:00Z", "action": "approval:approved", "operator": "operator", "source_ip": "127.0.0.1", "details": {"operation": "provider:select"}, "result": "success", "run_id": None},
        ]
        with open(self.log_path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    def test_summary_has_required_fields(self):
        """Summary should have all required top-level fields."""
        summary = get_rollback_summary(log_dir=self.tmpdir)
        required = ["total_entries", "eligible_count", "ineligible_count", "by_category", "top_ineligible_actions"]
        for field in required:
            self.assertIn(field, summary, f"Missing field: {field}")

    def test_summary_counts_match(self):
        """Total should equal eligible + ineligible."""
        summary = get_rollback_summary(log_dir=self.tmpdir)
        self.assertEqual(
            summary["total_entries"],
            summary["eligible_count"] + summary["ineligible_count"]
        )

    def test_top_ineligible_actions(self):
        """Should list most common ineligible actions."""
        summary = get_rollback_summary(log_dir=self.tmpdir)
        self.assertIsInstance(summary["top_ineligible_actions"], list)
        if summary["top_ineligible_actions"]:
            first = summary["top_ineligible_actions"][0]
            self.assertIn("action", first)
            self.assertIn("count", first)


if __name__ == "__main__":
    unittest.main()
