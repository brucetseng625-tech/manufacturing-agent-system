"""Tests for audit_chain — operator action audit logging."""

import unittest
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audit_chain import (
    append_audit_entry,
    query_audit_log,
    get_audit_summary,
    _close_audit_log,
    _ensure_audit_log,
    _AUDIT_FILE,
)


class AuditChainTest(unittest.TestCase):
    """Tests for the audit chain module."""

    def setUp(self):
        """Create a temp directory for audit logs."""
        self.tmpdir = tempfile.mkdtemp()
        # Reset global state
        _close_audit_log()

    def tearDown(self):
        """Clean up."""
        _close_audit_log()

    def _log_path(self):
        return os.path.join(self.tmpdir, "audit.jsonl")

    def test_append_creates_file(self):
        """Appending an entry should create the log file."""
        append_audit_entry("test:action", log_dir=self.tmpdir)
        self.assertTrue(os.path.exists(self._log_path()))

    def test_append_writes_valid_json(self):
        """Each entry should be valid JSON."""
        append_audit_entry("test:action", log_dir=self.tmpdir)
        with open(self._log_path(), "r") as f:
            line = f.readline()
        entry = json.loads(line)
        self.assertEqual(entry["action"], "test:action")
        self.assertEqual(entry["operator"], "api")
        self.assertEqual(entry["result"], "success")
        self.assertIn("timestamp", entry)

    def test_append_with_details(self):
        """Details should be stored in the entry."""
        append_audit_entry("config:reload", operator="dashboard",
                           source_ip="10.0.0.1",
                           details={"config_path": "/etc/config.json"},
                           result="success", log_dir=self.tmpdir)
        with open(self._log_path(), "r") as f:
            entry = json.loads(f.readline())
        self.assertEqual(entry["action"], "config:reload")
        self.assertEqual(entry["operator"], "dashboard")
        self.assertEqual(entry["source_ip"], "10.0.0.1")
        self.assertEqual(entry["details"]["config_path"], "/etc/config.json")
        self.assertEqual(entry["result"], "success")

    def test_append_denied_result(self):
        """Denied entries should have result='denied'."""
        append_audit_entry("guardrail:denied", operator="api",
                           details={"guardrail": True},
                           result="denied", log_dir=self.tmpdir)
        with open(self._log_path(), "r") as f:
            entry = json.loads(f.readline())
        self.assertEqual(entry["result"], "denied")

    def test_multiple_entries(self):
        """Multiple entries should be appended sequentially."""
        append_audit_entry("action:1", log_dir=self.tmpdir)
        append_audit_entry("action:2", log_dir=self.tmpdir)
        append_audit_entry("action:3", log_dir=self.tmpdir)

        with open(self._log_path(), "r") as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(json.loads(lines[0])["action"], "action:1")
        self.assertEqual(json.loads(lines[1])["action"], "action:2")
        self.assertEqual(json.loads(lines[2])["action"], "action:3")

    def test_query_returns_entries(self):
        """Query should return entries."""
        append_audit_entry("config:reload", log_dir=self.tmpdir)
        append_audit_entry("alerts:reset", log_dir=self.tmpdir)

        result = query_audit_log(log_dir=self.tmpdir)
        self.assertEqual(result["total"], 2)
        self.assertEqual(len(result["entries"]), 2)

    def test_query_newest_first(self):
        """Entries should be returned newest-first."""
        append_audit_entry("first", log_dir=self.tmpdir)
        append_audit_entry("second", log_dir=self.tmpdir)
        append_audit_entry("third", log_dir=self.tmpdir)

        result = query_audit_log(log_dir=self.tmpdir)
        self.assertEqual(result["entries"][0]["action"], "third")
        self.assertEqual(result["entries"][1]["action"], "second")
        self.assertEqual(result["entries"][2]["action"], "first")

    def test_query_with_action_filter(self):
        """Action filter should work."""
        append_audit_entry("config:reload", log_dir=self.tmpdir)
        append_audit_entry("alerts:reset", log_dir=self.tmpdir)
        append_audit_entry("config:reload", log_dir=self.tmpdir)

        result = query_audit_log(action_filter="config:reload", log_dir=self.tmpdir)
        self.assertEqual(result["total"], 2)
        for entry in result["entries"]:
            self.assertEqual(entry["action"], "config:reload")

    def test_query_with_result_filter(self):
        """Result filter should work."""
        append_audit_entry("test:1", result="success", log_dir=self.tmpdir)
        append_audit_entry("test:2", result="denied", log_dir=self.tmpdir)
        append_audit_entry("test:3", result="success", log_dir=self.tmpdir)

        result = query_audit_log(result_filter="denied", log_dir=self.tmpdir)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["entries"][0]["result"], "denied")

    def test_query_with_limit(self):
        """Limit should work."""
        for i in range(10):
            append_audit_entry(f"action:{i}", log_dir=self.tmpdir)

        result = query_audit_log(limit=3, log_dir=self.tmpdir)
        self.assertEqual(len(result["entries"]), 3)
        self.assertEqual(result["total"], 10)

    def test_query_with_offset(self):
        """Offset should work."""
        for i in range(5):
            append_audit_entry(f"action:{i}", log_dir=self.tmpdir)

        result = query_audit_log(offset=2, log_dir=self.tmpdir)
        self.assertEqual(result["total"], 5)
        self.assertEqual(len(result["entries"]), 3)  # 5 - 2 = 3

    def test_query_empty_log(self):
        """Query on non-existent log should return empty."""
        result = query_audit_log(log_dir=self.tmpdir)
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["entries"], [])

    def test_get_summary(self):
        """Summary should aggregate counts."""
        append_audit_entry("config:reload", result="success", log_dir=self.tmpdir)
        append_audit_entry("config:reload", result="denied", log_dir=self.tmpdir)
        append_audit_entry("alerts:reset", result="success", log_dir=self.tmpdir)

        summary = get_audit_summary(log_dir=self.tmpdir)
        self.assertEqual(summary["total_entries"], 3)
        self.assertEqual(summary["by_action"]["config:reload"], 2)
        self.assertEqual(summary["by_action"]["alerts:reset"], 1)
        self.assertEqual(summary["by_result"]["success"], 2)
        self.assertEqual(summary["by_result"]["denied"], 1)
        self.assertIsNotNone(summary["last_entry"])
        self.assertEqual(summary["last_entry"]["action"], "alerts:reset")

    def test_summary_empty_log(self):
        """Summary on empty log should have zero counts."""
        summary = get_audit_summary(log_dir=self.tmpdir)
        self.assertEqual(summary["total_entries"], 0)
        self.assertEqual(summary["by_action"], {})
        self.assertEqual(summary["by_result"], {})
        self.assertIsNone(summary["last_entry"])

    def test_audit_file_closed(self):
        """Close should close the file handle."""
        append_audit_entry("test", log_dir=self.tmpdir)
        _close_audit_log()
        # Should be able to re-open
        _ensure_audit_log(self.tmpdir)
        append_audit_entry("test2", log_dir=self.tmpdir)
        _close_audit_log()


if __name__ == "__main__":
    unittest.main()
