
import os
import tempfile
import json
import unittest
import socket
import threading
import time
from datetime import datetime, timedelta, timezone

from metrics import compute_metrics, _load_runs


class MetricsComputationTest(unittest.TestCase):
    """Tests for metrics computation from audit log data."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _write_runs(self, records):
        """Helper to write fake run records to the temp log dir."""
        log_path = os.path.join(self.tmpdir, "runs.jsonl")
        with open(log_path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def test_empty_log_returns_zeros(self):
        """When no log file exists, all counts should be zero."""
        result = compute_metrics(log_dir=self.tmpdir)
        self.assertEqual(result["total_runs"], 0)
        self.assertEqual(result["success_count"], 0)
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(result["success_rate"], 0.0)
        self.assertEqual(result["error_rate"], 0.0)
        self.assertEqual(result["recent_runs"], 0)
        self.assertEqual(result["skill_distribution"], {})
        self.assertEqual(result["channel_distribution"], {})

    def test_basic_counts(self):
        """Basic success/error counting should be correct."""
        self._write_runs([
            {"status": "success", "skill": "delivery-risk-analysis", "channel": "cli",
             "timestamp": "2026-05-08T10:00:00+00:00"},
            {"status": "success", "skill": "quote-comparison-summary", "channel": "http",
             "timestamp": "2026-05-08T10:01:00+00:00"},
            {"status": "error", "skill": None, "channel": "cli",
             "timestamp": "2026-05-08T10:02:00+00:00"},
        ])
        result = compute_metrics(log_dir=self.tmpdir)
        self.assertEqual(result["total_runs"], 3)
        self.assertEqual(result["success_count"], 2)
        self.assertEqual(result["error_count"], 1)
        self.assertAlmostEqual(result["success_rate"], 66.7, places=1)
        self.assertAlmostEqual(result["error_rate"], 33.3, places=1)

    def test_skill_distribution(self):
        """Skill distribution should count correctly and limit to top 10."""
        records = []
        for i in range(15):
            skill = f"skill-{i % 5}"
            records.append({
                "status": "success", "skill": skill, "channel": "cli",
                "timestamp": "2026-05-08T10:00:00+00:00",
            })
        self._write_runs(records)
        result = compute_metrics(log_dir=self.tmpdir)
        dist = result["skill_distribution"]
        self.assertEqual(len(dist), 5)  # only 5 unique skills
        self.assertEqual(dist["skill-0"], 3)  # each appears 3 times

    def test_channel_distribution(self):
        """Channel distribution should count correctly."""
        self._write_runs([
            {"status": "success", "channel": "cli", "timestamp": "2026-05-08T10:00:00+00:00"},
            {"status": "success", "channel": "http", "timestamp": "2026-05-08T10:01:00+00:00"},
            {"status": "success", "channel": "http", "timestamp": "2026-05-08T10:02:00+00:00"},
        ])
        result = compute_metrics(log_dir=self.tmpdir)
        self.assertEqual(result["channel_distribution"]["cli"], 1)
        self.assertEqual(result["channel_distribution"]["http"], 2)

    def test_recent_window_filtering(self):
        """Recent metrics should only include records within window."""
        now = datetime.now(timezone.utc)
        old_ts = (now - timedelta(hours=48)).isoformat()
        new_ts = now.isoformat()

        self._write_runs([
            {"status": "success", "channel": "cli", "timestamp": old_ts},
            {"status": "success", "channel": "cli", "timestamp": new_ts},
            {"status": "error", "channel": "http", "timestamp": new_ts},
        ])
        result = compute_metrics(log_dir=self.tmpdir, window_hours=24)
        self.assertEqual(result["total_runs"], 3)  # total includes everything
        self.assertEqual(result["recent_runs"], 2)  # only 2 within 24h
        self.assertAlmostEqual(result["recent_success_rate"], 50.0, places=1)

    def test_last_run_timestamp(self):
        """Last run timestamp should be the most recent."""
        self._write_runs([
            {"status": "success", "timestamp": "2026-05-08T10:00:00+00:00"},
            {"status": "success", "timestamp": "2026-05-08T12:00:00+00:00"},
            {"status": "success", "timestamp": "2026-05-08T11:00:00+00:00"},
        ])
        result = compute_metrics(log_dir=self.tmpdir)
        self.assertEqual(result["last_run_timestamp"], "2026-05-08T12:00:00+00:00")

    def test_malformed_lines_skipped(self):
        """Malformed JSONL lines should be silently skipped."""
        log_path = os.path.join(self.tmpdir, "runs.jsonl")
        with open(log_path, "w") as f:
            f.write('{"status": "success", "timestamp": "2026-05-08T10:00:00+00:00"}\n')
            f.write('not json at all\n')
            f.write('{"status": "error", "timestamp": "2026-05-08T10:01:00+00:00"}\n')
        result = compute_metrics(log_dir=self.tmpdir)
        self.assertEqual(result["total_runs"], 2)

    def test_fallback_to_intent_when_skill_missing(self):
        """When skill is None/missing, should use intent for distribution."""
        self._write_runs([
            {"status": "success", "intent": "delivery_risk_analysis", "timestamp": "2026-05-08T10:00:00+00:00"},
        ])
        result = compute_metrics(log_dir=self.tmpdir)
        self.assertIn("delivery_risk_analysis", result["skill_distribution"])


class LoadRunsTest(unittest.TestCase):
    """Tests for _load_runs helper."""

    def test_nonexistent_log_returns_empty(self):
        """If log file doesn't exist, should return empty list."""
        result = _load_runs(log_dir="/nonexistent/path")
        self.assertEqual(result, [])

    def test_loads_all_records(self):
        """Should load all valid records."""
        tmpdir = tempfile.mkdtemp()
        log_path = os.path.join(tmpdir, "runs.jsonl")
        with open(log_path, "w") as f:
            f.write('{"a": 1}\n{"b": 2}\n')
        result = _load_runs(log_dir=tmpdir)
        self.assertEqual(len(result), 2)


class MetricsEndpointTest(unittest.TestCase):
    """Tests for the GET /metrics HTTP endpoint."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Write a run record so we have data
        log_path = os.path.join(self.tmpdir, "runs.jsonl")
        with open(log_path, "w") as f:
            now = datetime.now(timezone.utc).isoformat()
            f.write(json.dumps({"status": "success", "skill": "test", "channel": "cli",
                                "timestamp": now}) + "\n")

    def _find_free_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def test_metrics_endpoint_returns_200(self):
        """GET /metrics should return 200 with stats."""
        from server import run_server
        import urllib.request
        import json as _json

        port = self._find_free_port()

        def run_in_thread():
            os.environ["AGENT_LOG_DIR"] = self.tmpdir
            run_server(port=port)

        server_thread = threading.Thread(target=run_in_thread, daemon=True)
        server_thread.start()
        time.sleep(0.3)

        try:
            url = f"http://localhost:{port}/metrics"
            with urllib.request.urlopen(url, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                data = _json.loads(resp.read().decode("utf-8"))
                self.assertIn("total_runs", data)
                self.assertEqual(data["total_runs"], 1)
                self.assertIn("success_rate", data)
        finally:
            pass  # daemon thread will exit

    def test_metrics_endpoint_empty_log(self):
        """GET /metrics with no log should return zero stats."""
        from server import run_server
        import urllib.request
        import json as _json

        port = self._find_free_port()
        empty_dir = tempfile.mkdtemp()

        def run_in_thread():
            os.environ["AGENT_LOG_DIR"] = empty_dir
            run_server(port=port)

        server_thread = threading.Thread(target=run_in_thread, daemon=True)
        server_thread.start()
        time.sleep(0.3)

        try:
            url = f"http://localhost:{port}/metrics"
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
                self.assertEqual(data["total_runs"], 0)
        finally:
            pass
