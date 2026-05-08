import json
import os
import unittest
import tempfile
import datetime
from unittest.mock import patch

from audit_logger import log_run, resolve_log_dir, query_runs, format_run_summary

class AuditLoggerTest(unittest.TestCase):
    def test_log_run_success_cli(self):
        """Test successful CLI run logging"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = {
                "status": "success",
                "query": "ORD-1001 出貨",
                "data_dir": "mock_data",
                "order_ids": ["ORD-1001"],
                "intent": "delivery_risk_analysis",
                "skill": "delivery-risk-analysis",
                "data": {
                    "order_id": "ORD-1001",
                    "decision": "can_ship",
                    "trace": ["loaded orders", "checked risk"]
                }
            }
            
            log_run(result, "cli", asana_task="12345", asana_posted=True, log_dir=tmp_dir)
            
            log_path = os.path.join(tmp_dir, "runs.jsonl")
            self.assertTrue(os.path.exists(log_path))
            
            with open(log_path, "r") as f:
                lines = f.readlines()
                self.assertEqual(len(lines), 1)
                record = json.loads(lines[0])
                
                # Verify fields
                self.assertEqual(record["channel"], "cli")
                self.assertEqual(record["query"], "ORD-1001 出貨")
                self.assertEqual(record["status"], "success")
                self.assertEqual(record["intent"], "delivery_risk_analysis")
                self.assertEqual(record["skill"], "delivery-risk-analysis")
                self.assertEqual(record["order_ids"], ["ORD-1001"])
                self.assertEqual(record["asana_task"], "12345")
                self.assertTrue(record["asana_posted"])
                self.assertEqual(record["error_type"], None)
                self.assertEqual(record["trace"], ["loaded orders", "checked risk"])
                self.assertIn("timestamp", record)

    def test_log_run_error_http(self):
        """Test error HTTP run logging"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = {
                "status": "error",
                "query": "BAD QUERY",
                "data_dir": "mock_data",
                "order_ids": [],
                "intent": None,
                "type": "validation_failed",
                "details": ["Missing order ID"]
            }
            
            log_run(result, "http", asana_task=None, asana_posted=None, log_dir=tmp_dir)
            
            log_path = os.path.join(tmp_dir, "runs.jsonl")
            with open(log_path, "r") as f:
                record = json.loads(f.read())
                
                self.assertEqual(record["channel"], "http")
                self.assertEqual(record["status"], "error")
                self.assertEqual(record["error_type"], "validation_failed")
                self.assertEqual(record["asana_task"], None)
                self.assertEqual(record["asana_posted"], None)
                self.assertEqual(record["trace"], [])

    def test_log_run_fail_safe(self):
        """Test that logging failure does not crash the app"""
        # Try to write to a non-existent directory that cannot be created (e.g., read-only root)
        # Or simply mock the open function to raise an error
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_dir = os.path.join(tmp_dir, "readonly")
            os.makedirs(bad_dir)
            # Make it read-only
            os.chmod(bad_dir, 0o555)
            
            result = {"status": "success", "query": "test", "data_dir": ".", "order_ids": []}
            
            # This should not raise an exception
            try:
                log_run(result, "cli", log_dir=bad_dir)
            except Exception as e:
                self.fail(f"log_run should not raise exception on failure: {e}")
            
            # Restore permissions for cleanup
            os.chmod(bad_dir, 0o755)

    def test_resolve_log_dir_uses_env_override(self):
        with patch.dict(os.environ, {"AGENT_LOG_DIR": "/tmp/agent-runs"}):
            self.assertEqual(resolve_log_dir(), "/tmp/agent-runs")

    def _write_test_records(self, log_dir, records):
        """Helper to write test JSONL records."""
        log_path = os.path.join(log_dir, "runs.jsonl")
        with open(log_path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def test_query_runs_returns_all_records_newest_first(self):
        """query_runs returns all records sorted newest first."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            records = [
                {"timestamp": "2026-05-08T01:00:00", "status": "success", "query": "q1", "channel": "cli", "skill": "delivery-risk-analysis", "intent": "delivery_risk_analysis", "order_ids": ["ORD-1"]},
                {"timestamp": "2026-05-08T02:00:00", "status": "error", "query": "q2", "channel": "http", "skill": "quote-comparison-summary", "intent": "quote_comparison_summary", "order_ids": []},
                {"timestamp": "2026-05-08T03:00:00", "status": "success", "query": "q3", "channel": "cli", "skill": "team:comprehensive-analysis", "intent": "comprehensive_analysis", "order_ids": ["ORD-2"]},
            ]
            self._write_test_records(tmp_dir, records)

            runs = query_runs(log_dir=tmp_dir)
            self.assertEqual(len(runs), 3)
            self.assertEqual(runs[0]["query"], "q3")  # newest first
            self.assertEqual(runs[2]["query"], "q1")

    def test_query_runs_filters_by_status(self):
        """Filter by status returns only matching records."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            records = [
                {"timestamp": "2026-05-08T01:00:00", "status": "success", "query": "ok", "channel": "cli", "skill": "delivery-risk-analysis", "intent": "delivery_risk_analysis", "order_ids": []},
                {"timestamp": "2026-05-08T02:00:00", "status": "error", "query": "bad", "channel": "http", "skill": "delivery-risk-analysis", "intent": "delivery_risk_analysis", "order_ids": [], "error_type": "missing_order_id"},
                {"timestamp": "2026-05-08T03:00:00", "status": "success", "query": "ok2", "channel": "cli", "skill": "sales-response-draft", "intent": "sales_response_draft", "order_ids": ["ORD-1"]},
            ]
            self._write_test_records(tmp_dir, records)

            error_runs = query_runs(log_dir=tmp_dir, status="error")
            self.assertEqual(len(error_runs), 1)
            self.assertEqual(error_runs[0]["query"], "bad")

            success_runs = query_runs(log_dir=tmp_dir, status="success")
            self.assertEqual(len(success_runs), 2)

    def test_query_runs_filters_by_skill(self):
        """Filter by skill name supports partial matching."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            records = [
                {"timestamp": "2026-05-08T01:00:00", "status": "success", "query": "q1", "channel": "cli", "skill": "delivery-risk-analysis", "intent": "delivery_risk_analysis", "order_ids": []},
                {"timestamp": "2026-05-08T02:00:00", "status": "success", "query": "q2", "channel": "cli", "skill": "team:comprehensive-analysis", "intent": "comprehensive_analysis", "order_ids": ["ORD-1"]},
                {"timestamp": "2026-05-08T03:00:00", "status": "success", "query": "q3", "channel": "http", "skill": "quote-comparison-summary", "intent": "quote_comparison_summary", "order_ids": []},
            ]
            self._write_test_records(tmp_dir, records)

            # Exact match
            delivery = query_runs(log_dir=tmp_dir, skill="delivery-risk-analysis")
            self.assertEqual(len(delivery), 1)

            # Partial match for team prefix
            team_runs = query_runs(log_dir=tmp_dir, skill="team:")
            self.assertEqual(len(team_runs), 1)
            self.assertEqual(team_runs[0]["skill"], "team:comprehensive-analysis")

    def test_query_runs_filters_by_channel(self):
        """Filter by channel returns only matching records."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            records = [
                {"timestamp": "2026-05-08T01:00:00", "status": "success", "query": "q1", "channel": "cli", "skill": "delivery-risk-analysis", "intent": "delivery_risk_analysis", "order_ids": []},
                {"timestamp": "2026-05-08T02:00:00", "status": "success", "query": "q2", "channel": "http", "skill": "sales-response-draft", "intent": "sales_response_draft", "order_ids": ["ORD-1"]},
            ]
            self._write_test_records(tmp_dir, records)

            cli_runs = query_runs(log_dir=tmp_dir, channel="cli")
            self.assertEqual(len(cli_runs), 1)
            self.assertEqual(cli_runs[0]["channel"], "cli")

    def test_query_runs_returns_empty_for_missing_file(self):
        """query_runs returns empty list when log file does not exist."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            runs = query_runs(log_dir=tmp_dir)
            self.assertEqual(runs, [])

    def test_query_runs_skips_malformed_lines(self):
        """query_runs skips lines that are not valid JSON."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "runs.jsonl")
            with open(log_path, "w") as f:
                f.write('{"timestamp": "2026-05-08T01:00:00", "status": "success", "query": "good", "channel": "cli", "skill": "delivery-risk-analysis", "intent": "delivery_risk_analysis", "order_ids": []}\n')
                f.write("NOT VALID JSON\n")
                f.write("\n")
                f.write('{"timestamp": "2026-05-08T02:00:00", "status": "error", "query": "good2", "channel": "http", "skill": "quote-comparison-summary", "intent": "quote_comparison_summary", "order_ids": []}\n')

            runs = query_runs(log_dir=tmp_dir)
            self.assertEqual(len(runs), 2)
            self.assertEqual(runs[0]["query"], "good2")  # newest first

    def test_query_runs_last_n_limit(self):
        """last_n parameter limits the number of returned records."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            records = [
                {"timestamp": f"2026-05-08T{i:02d}:00:00", "status": "success", "query": f"q{i}", "channel": "cli", "skill": "delivery-risk-analysis", "intent": "delivery_risk_analysis", "order_ids": []}
                for i in range(1, 11)
            ]
            self._write_test_records(tmp_dir, records)

            runs = query_runs(log_dir=tmp_dir, last_n=3)
            self.assertEqual(len(runs), 3)
            self.assertEqual(runs[0]["query"], "q10")
            self.assertEqual(runs[2]["query"], "q8")

    def test_format_run_summary_empty(self):
        """format_run_summary returns friendly message for empty results."""
        result = format_run_summary([])
        self.assertIn("No runs found", result)

    def test_format_run_summary_compact_mode(self):
        """format_run_summary compact mode produces one line per run."""
        runs = [
            {"timestamp": "2026-05-08T10:00:00", "status": "success", "query": "test", "channel": "cli", "skill": "delivery-risk-analysis", "order_ids": ["ORD-1"]},
        ]
        result = format_run_summary(runs, compact=True)
        self.assertIn("OK", result)
        self.assertIn("cli", result)
        # Header (2 lines) + 1 record = 3 total
        lines = result.strip().split("\n")
        self.assertEqual(len(lines), 3)  # header + separator + 1 record

    def test_format_run_summary_with_error(self):
        """format_run_summary shows error type for failed runs."""
        runs = [
            {"timestamp": "2026-05-08T10:00:00", "status": "error", "query": "bad query", "channel": "http", "skill": "delivery-risk-analysis", "order_ids": [], "error_type": "missing_order_id"},
        ]
        result = format_run_summary(runs, compact=True)
        self.assertIn("FAIL(missing_order_id)", result)
