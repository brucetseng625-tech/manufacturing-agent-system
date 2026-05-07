import json
import os
import unittest
import tempfile
import datetime
from unittest.mock import patch

from audit_logger import log_run, resolve_log_dir

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
