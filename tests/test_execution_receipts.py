"""Tests for execution_receipts module."""

import unittest
from unittest.mock import patch, MagicMock
import execution_receipts


class TestRecordReceipt(unittest.TestCase):

    def setUp(self):
        execution_receipts.reset_receipts()

    def test_record_approval_retry_receipt(self):
        r = execution_receipts.record_receipt(
            source="approval-retry",
            operation="policy:reload",
            status="success",
            approval_id="approval-1",
            details={"status_code": 200},
        )
        self.assertTrue(r["receipt_id"].startswith("rcpt-"))
        self.assertEqual(r["source"], "approval-retry")
        self.assertEqual(r["operation"], "policy:reload")
        self.assertEqual(r["status"], "success")
        self.assertEqual(r["approval_id"], "approval-1")
        self.assertIn("recorded_at", r)

    def test_record_auto_remediation_receipt(self):
        r = execution_receipts.record_receipt(
            source="auto-remediation",
            operation="alerts:reset",
            status="executed",
            trigger="circuit_breaker_open",
            hook="reset_on_cb",
            details={"dry_run": False},
        )
        self.assertEqual(r["source"], "auto-remediation")
        self.assertEqual(r["operation"], "alerts:reset")
        self.assertEqual(r["status"], "executed")
        self.assertEqual(r["trigger"], "circuit_breaker_open")
        self.assertEqual(r["hook"], "reset_on_cb")

    def test_record_receipt_with_minimal_fields(self):
        r = execution_receipts.record_receipt(
            source="approval-retry",
            operation="config:reload",
            status="failed",
        )
        self.assertEqual(r["source"], "approval-retry")
        self.assertEqual(r["operation"], "config:reload")
        self.assertEqual(r["status"], "failed")
        self.assertNotIn("approval_id", r)
        self.assertNotIn("trigger", r)
        self.assertNotIn("hook", r)
        self.assertNotIn("duration_ms", r)
        self.assertNotIn("details", r)

    @patch("execution_receipts.append_audit_entry")
    def test_record_receipt_logs_to_audit(self, mock_audit):
        execution_receipts.record_receipt(
            source="auto-remediation",
            operation="alerts:reset",
            status="executed",
        )
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args[1]
        self.assertEqual(call_kwargs["action"], "execution_receipt")
        self.assertEqual(call_kwargs["result"], "executed")

    @patch("execution_receipts.append_audit_entry")
    def test_record_receipt_operator_for_approval_retry(self, mock_audit):
        execution_receipts.record_receipt(
            source="approval-retry",
            operation="policy:reload",
            status="success",
        )
        self.assertEqual(mock_audit.call_args[1]["operator"], "operator")

    @patch("execution_receipts.append_audit_entry")
    def test_record_receipt_system_for_auto_remediation(self, mock_audit):
        execution_receipts.record_receipt(
            source="auto-remediation",
            operation="alerts:reset",
            status="executed",
        )
        self.assertEqual(mock_audit.call_args[1]["operator"], "system")


class TestQueryReceipts(unittest.TestCase):

    def setUp(self):
        execution_receipts.reset_receipts()

    def _add_receipts(self):
        execution_receipts.record_receipt(
            source="approval-retry", operation="policy:reload", status="success",
            approval_id="approval-1")
        execution_receipts.record_receipt(
            source="auto-remediation", operation="alerts:reset", status="executed",
            trigger="circuit_breaker_open", hook="hook1")
        execution_receipts.record_receipt(
            source="auto-remediation", operation="config:reload", status="failed",
            trigger="system_unhealthy", hook="hook2")
        execution_receipts.record_receipt(
            source="approval-retry", operation="alerts:reset", status="policy_denied",
            approval_id="approval-2")

    def test_query_all_receipts(self):
        self._add_receipts()
        result = execution_receipts.query_receipts()
        self.assertEqual(result["total"], 4)
        self.assertEqual(len(result["receipts"]), 4)

    def test_query_by_source(self):
        self._add_receipts()
        result = execution_receipts.query_receipts(source="approval-retry")
        self.assertEqual(result["total"], 2)
        for r in result["receipts"]:
            self.assertEqual(r["source"], "approval-retry")

    def test_query_by_status(self):
        self._add_receipts()
        result = execution_receipts.query_receipts(status="executed")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["receipts"][0]["status"], "executed")

    def test_query_by_operation(self):
        self._add_receipts()
        result = execution_receipts.query_receipts(operation="alerts:reset")
        self.assertEqual(result["total"], 2)

    def test_query_with_limit(self):
        self._add_receipts()
        result = execution_receipts.query_receipts(limit=2)
        self.assertEqual(len(result["receipts"]), 2)

    def test_query_with_offset(self):
        self._add_receipts()
        result = execution_receipts.query_receipts(offset=2)
        self.assertEqual(len(result["receipts"]), 2)
        self.assertEqual(result["total"], 4)

    def test_query_returns_newest_first(self):
        self._add_receipts()
        result = execution_receipts.query_receipts(limit=1)
        self.assertEqual(result["receipts"][0]["operation"], "alerts:reset")

    def test_query_combined_filters(self):
        self._add_receipts()
        result = execution_receipts.query_receipts(
            source="auto-remediation", status="failed")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["receipts"][0]["operation"], "config:reload")


class TestGetReceiptsSummary(unittest.TestCase):

    def setUp(self):
        execution_receipts.reset_receipts()

    def test_empty_summary(self):
        summary = execution_receipts.get_receipts_summary()
        self.assertEqual(summary["total"], 0)
        self.assertEqual(summary["by_source"], {})
        self.assertEqual(summary["by_status"], {})
        self.assertEqual(summary["by_operation"], {})

    def test_summary_counts(self):
        execution_receipts.record_receipt(
            source="approval-retry", operation="policy:reload", status="success")
        execution_receipts.record_receipt(
            source="auto-remediation", operation="alerts:reset", status="executed")
        execution_receipts.record_receipt(
            source="auto-remediation", operation="alerts:reset", status="executed")

        summary = execution_receipts.get_receipts_summary()
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["by_source"]["approval-retry"], 1)
        self.assertEqual(summary["by_source"]["auto-remediation"], 2)
        self.assertEqual(summary["by_status"]["success"], 1)
        self.assertEqual(summary["by_status"]["executed"], 2)
        self.assertEqual(summary["by_operation"]["policy:reload"], 1)
        self.assertEqual(summary["by_operation"]["alerts:reset"], 2)


class TestPruning(unittest.TestCase):

    def setUp(self):
        execution_receipts.reset_receipts()

    def test_pruning_keeps_only_latest(self):
        original_max = execution_receipts.MAX_RECEIPTS
        try:
            execution_receipts.MAX_RECEIPTS = 3
            for i in range(5):
                execution_receipts.record_receipt(
                    source="approval-retry",
                    operation="op-{}".format(i),
                    status="success",
                )
            result = execution_receipts.query_receipts()
            self.assertEqual(result["total"], 3)
            # Should be the last 3 (op-2, op-3, op-4), newest first
            ops = [r["operation"] for r in result["receipts"]]
            self.assertEqual(ops[0], "op-4")
            self.assertEqual(ops[2], "op-2")
        finally:
            execution_receipts.MAX_RECEIPTS = original_max


class TestReset(unittest.TestCase):

    def setUp(self):
        execution_receipts.reset_receipts()

    @patch("execution_receipts.append_audit_entry")
    def test_reset_clears_all(self, _mock_audit):
        execution_receipts.record_receipt(
            source="approval-retry", operation="test", status="success")
        execution_receipts.record_receipt(
            source="auto-remediation", operation="test2", status="executed")
        execution_receipts.reset_receipts()
        summary = execution_receipts.get_receipts_summary()
        self.assertEqual(summary["total"], 0)

    def test_reset_after_pruning(self):
        execution_receipts.record_receipt(
            source="approval-retry", operation="test", status="success")
        execution_receipts.reset_receipts()
        result = execution_receipts.query_receipts()
        self.assertEqual(result["total"], 0)


class TestUniqueIds(unittest.TestCase):

    def setUp(self):
        execution_receipts.reset_receipts()

    def test_each_receipt_has_unique_id(self):
        ids = set()
        for _ in range(10):
            r = execution_receipts.record_receipt(
                source="approval-retry", operation="test", status="success")
            ids.add(r["receipt_id"])
        self.assertEqual(len(ids), 10)


if __name__ == "__main__":
    unittest.main()
