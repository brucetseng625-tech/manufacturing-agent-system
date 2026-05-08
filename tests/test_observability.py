
import os
import tempfile
import json
import unittest
from unittest.mock import patch

from skills.observability import (
    generate_run_id,
    get_run_id,
    set_run_id,
    clear_run_id,
    log_event,
    _write_event,
    _resolve_log_dir,
    log_routing,
    log_error,
    log_complete,
    log_asana_post,
)


class RunIdTest(unittest.TestCase):
    """Tests for run ID generation and thread-local context."""

    def test_run_id_format(self):
        """Run ID should match pattern: run-YYYYMMDD-XXXXXX."""
        run_id = generate_run_id()
        self.assertIsInstance(run_id, str)
        self.assertTrue(run_id.startswith("run-"))
        parts = run_id.split("-")
        self.assertEqual(len(parts), 3)  # run, date, hex
        self.assertEqual(parts[0], "run")
        self.assertEqual(len(parts[1]), 8)  # YYYYMMDD
        self.assertEqual(len(parts[2]), 6)  # 6-char hex

    def test_run_id_uniqueness(self):
        """Each generated run ID should be unique."""
        ids = [generate_run_id() for _ in range(100)]
        self.assertEqual(len(set(ids)), 100)

    def test_run_id_thread_local_get_set(self):
        """set_run_id and get_run_id should work with thread-local storage."""
        clear_run_id()
        self.assertIsNone(get_run_id())
        set_run_id("run-test-123")
        self.assertEqual(get_run_id(), "run-test-123")

    def test_run_id_thread_local_clear(self):
        """clear_run_id should reset to None."""
        set_run_id("run-test-456")
        clear_run_id()
        self.assertIsNone(get_run_id())


class StructuredEventLogTest(unittest.TestCase):
    """Tests for structured event logging."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = os.path.join(self.tmpdir, "events.jsonl")

    def test_write_event_creates_file(self):
        """Writing an event should create the JSONL file."""
        with patch("skills.observability._resolve_log_dir", return_value=self.tmpdir):
            _write_event({"event": "test", "timestamp": "2026-05-08T00:00:00+00:00"})
        self.assertTrue(os.path.isfile(self.log_path))

    def test_write_event_appends_jsonl(self):
        """Each event should be appended as a single JSON line."""
        with patch("skills.observability._resolve_log_dir", return_value=self.tmpdir):
            _write_event({"event": "e1", "timestamp": "2026-05-08T00:00:00+00:00"})
            _write_event({"event": "e2", "timestamp": "2026-05-08T00:00:01+00:00"})
        with open(self.log_path, "r") as f:
            lines = [l for l in f.read().strip().split("\n") if l]
        self.assertEqual(len(lines), 2)
        data1 = json.loads(lines[0])
        data2 = json.loads(lines[1])
        self.assertEqual(data1["event"], "e1")
        self.assertEqual(data2["event"], "e2")

    def test_write_event_injects_run_id(self):
        """Event should include current thread's run_id if not already present."""
        set_run_id("run-inject-test")
        try:
            with patch("skills.observability._resolve_log_dir", return_value=self.tmpdir):
                _write_event({"event": "inject_test", "timestamp": "2026-05-08T00:00:00+00:00"})
            with open(self.log_path, "r") as f:
                data = json.loads(f.read().strip())
            self.assertEqual(data["run_id"], "run-inject-test")
        finally:
            clear_run_id()

    def test_write_event_preserves_existing_run_id(self):
        """Event with explicit run_id should not be overwritten."""
        set_run_id("run-thread-local")
        try:
            with patch("skills.observability._resolve_log_dir", return_value=self.tmpdir):
                _write_event({"event": "preserve_test", "run_id": "run-explicit",
                              "timestamp": "2026-05-08T00:00:00+00:00"})
            with open(self.log_path, "r") as f:
                data = json.loads(f.read().strip())
            self.assertEqual(data["run_id"], "run-explicit")
        finally:
            clear_run_id()

    def test_write_event_never_raises(self):
        """Even with invalid paths, _write_event should never crash."""
        with patch("skills.observability._resolve_log_dir",
                   return_value="/nonexistent/path/that/does/not/exist"):
            _write_event({"event": "fail_test", "timestamp": "2026-05-08T00:00:00+00:00"})
        # No exception = pass


class LogEventHelperTest(unittest.TestCase):
    """Tests for log_event convenience functions."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _patch_log_dir(self):
        return patch("skills.observability._resolve_log_dir", return_value=self.tmpdir)

    def test_log_event_writes_to_file(self):
        with self._patch_log_dir():
            log_event("request", query="test query", channel="cli")
        log_path = os.path.join(self.tmpdir, "events.jsonl")
        self.assertTrue(os.path.isfile(log_path))
        with open(log_path, "r") as f:
            data = json.loads(f.read().strip())
        self.assertEqual(data["event"], "request")
        self.assertEqual(data["query"], "test query")
        self.assertEqual(data["channel"], "cli")

    def test_log_routing_includes_intent(self):
        with self._patch_log_dir():
            log_routing("delivery_risk_analysis", skill_name="delivery-risk-analysis",
                        order_ids=["ORD-1001"])
        with open(os.path.join(self.tmpdir, "events.jsonl"), "r") as f:
            data = json.loads(f.read().strip())
        self.assertEqual(data["event"], "routing")
        self.assertEqual(data["intent"], "delivery_risk_analysis")
        self.assertEqual(data["skill"], "delivery-risk-analysis")
        self.assertEqual(data["order_ids"], ["ORD-1001"])

    def test_log_error_includes_type_and_message(self):
        with self._patch_log_dir():
            log_error("validation_failed", "Missing order", run_id="run-err-001")
        with open(os.path.join(self.tmpdir, "events.jsonl"), "r") as f:
            data = json.loads(f.read().strip())
        self.assertEqual(data["event"], "error")
        self.assertEqual(data["error_type"], "validation_failed")
        self.assertEqual(data["message"], "Missing order")
        self.assertEqual(data["run_id"], "run-err-001")

    def test_log_complete_includes_status(self):
        with self._patch_log_dir():
            log_complete("run-complete-1", "success", "http", "delivery_risk_analysis",
                         skill="delivery-risk-analysis", duration_ms=42)
        with open(os.path.join(self.tmpdir, "events.jsonl"), "r") as f:
            data = json.loads(f.read().strip())
        self.assertEqual(data["event"], "complete")
        self.assertEqual(data["run_id"], "run-complete-1")
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["channel"], "http")
        self.assertEqual(data["duration_ms"], 42)

    def test_log_asana_post_records_success(self):
        with self._patch_log_dir():
            log_asana_post("1234567890", True, run_id="run-asana-1")
        with open(os.path.join(self.tmpdir, "events.jsonl"), "r") as f:
            data = json.loads(f.read().strip())
        self.assertEqual(data["event"], "asana_post")
        self.assertEqual(data["task_gid"], "1234567890")
        self.assertTrue(data["success"])
        self.assertEqual(data["run_id"], "run-asana-1")


class ResolveLogDirTest(unittest.TestCase):
    """Tests for log directory resolution."""

    def test_default_log_dir(self):
        """Without env var or arg, should return absolute 'logs' path."""
        result = _resolve_log_dir()
        self.assertTrue(result.endswith("logs"))
        self.assertTrue(os.path.isabs(result))

    def test_env_var_override(self):
        """AGENT_LOG_DIR env var should be used."""
        with patch.dict(os.environ, {"AGENT_LOG_DIR": "/custom/log/path"}):
            result = _resolve_log_dir()
            self.assertEqual(result, "/custom/log/path")

    def test_explicit_arg_override(self):
        """Explicit log_dir arg should override env var."""
        with patch.dict(os.environ, {"AGENT_LOG_DIR": "/env/path"}):
            result = _resolve_log_dir("/explicit/path")
            self.assertEqual(result, "/explicit/path")


class AuditLoggerRunIdIntegrationTest(unittest.TestCase):
    """Integration test: run_id flows from orchestrator to audit log."""

    def test_orchestrator_includes_run_id(self):
        """route_query should return run_id in result."""
        from orchestrator import route_query
        data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = route_query("ORD-1001 出貨風險分析", data_dir)
        self.assertIn("run_id", result)
        self.assertIsNotNone(result["run_id"])
        self.assertTrue(result["run_id"].startswith("run-"))

    def test_orchestrator_error_includes_run_id(self):
        """Even error results should include run_id."""
        from orchestrator import route_query
        data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = route_query("this is a completely unknown intent query", data_dir)
        self.assertIn("run_id", result)
        self.assertEqual(result["status"], "error")

    def test_audit_log_record_has_run_id(self):
        """log_run should include run_id from result dict."""
        from audit_logger import log_run, query_runs
        result = {
            "status": "success",
            "query": "test query",
            "data_dir": "/tmp/test",
            "order_ids": ["ORD-1001"],
            "intent": "delivery_risk_analysis",
            "skill": "delivery-risk-analysis",
            "run_id": "run-audit-test",
            "data": {"trace": []},
        }
        tmpdir = tempfile.mkdtemp()
        log_run(result, "cli", log_dir=tmpdir)

        runs = query_runs(log_dir=tmpdir)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["run_id"], "run-audit-test")

    def test_audit_log_filter_by_run_id(self):
        """query_runs should support filtering by run_id."""
        from audit_logger import log_run, query_runs
        tmpdir = tempfile.mkdtemp()

        log_run({"status": "success", "query": "q1", "data_dir": "",
                 "order_ids": [], "intent": "a", "skill": "a",
                 "run_id": "run-aaa", "data": {"trace": []}}, "cli", log_dir=tmpdir)
        log_run({"status": "success", "query": "q2", "data_dir": "",
                 "order_ids": [], "intent": "b", "skill": "b",
                 "run_id": "run-bbb", "data": {"trace": []}}, "cli", log_dir=tmpdir)
        log_run({"status": "success", "query": "q3", "data_dir": "",
                 "order_ids": [], "intent": "c", "skill": "c",
                 "run_id": "run-aaa", "data": {"trace": []}}, "http", log_dir=tmpdir)

        # Filter by run-aaa should return 2 records
        runs = query_runs(log_dir=tmpdir, run_id="run-aaa")
        self.assertEqual(len(runs), 2)
        for r in runs:
            self.assertEqual(r["run_id"], "run-aaa")

        # Filter by run-bbb should return 1 record
        runs = query_runs(log_dir=tmpdir, run_id="run-bbb")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["run_id"], "run-bbb")

        # Filter by nonexistent run_id should return 0
        runs = query_runs(log_dir=tmpdir, run_id="run-nope")
        self.assertEqual(len(runs), 0)
