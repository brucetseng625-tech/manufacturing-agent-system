import json
import os
import tempfile
import unittest
import threading
import time
import urllib.request
from http.server import HTTPServer

from server import (
    AgentHandler,
    _access_log_enabled,
    _access_log_file,
    _ensure_access_log,
    _write_access_log,
    run_server,
)


class AccessLogWriterTest(unittest.TestCase):
    """Unit tests for access log writing."""

    def test_write_disabled_does_nothing(self):
        """When disabled, _write_access_log should not fail."""
        import server
        original = server._access_log_enabled
        server._access_log_enabled = False
        try:
            _write_access_log({"test": True})
            # Should not raise
        finally:
            server._access_log_enabled = original

    def test_write_enabled_creates_file(self):
        """When enabled, _write_access_log should write JSON lines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import server
            server._access_log_enabled = True
            server._access_log_file = open(os.path.join(tmpdir, "access.log"), "a", encoding="utf-8")
            try:
                entry = {"timestamp": "2026-01-01T00:00:00Z", "method": "GET", "path": "/health", "status_code": 200, "duration_ms": 1.5, "client": "127.0.0.1"}
                _write_access_log(entry)
                server._access_log_file.close()
                with open(os.path.join(tmpdir, "access.log"), "r") as f:
                    line = f.read().strip()
                data = json.loads(line)
                self.assertEqual(data["method"], "GET")
                self.assertEqual(data["path"], "/health")
                self.assertEqual(data["status_code"], 200)
            finally:
                server._access_log_file = None
                server._access_log_enabled = False


class AccessLogIntegrationTest(unittest.TestCase):
    """Integration test: server with access logging enabled."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.log_path = os.path.join(cls.tmpdir, "access.log")
        cls.server = HTTPServer(("localhost", 0), AgentHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()
        time.sleep(0.5)
        # Enable access logging
        import server
        server._access_log_enabled = True
        server._access_log_file = open(cls.log_path, "a", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        import server
        if server._access_log_file:
            server._access_log_file.close()
        server._access_log_file = None
        server._access_log_enabled = False
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=1)

    def test_health_request_logged(self):
        """GET /health should produce an access log entry."""
        url = f"http://localhost:{self.port}/health"
        with urllib.request.urlopen(url):
            pass
        time.sleep(0.1)  # Allow async write to flush
        # Flush file manually for test
        import server
        if server._access_log_file:
            server._access_log_file.flush()
        with open(self.log_path, "r") as f:
            lines = [l for l in f.read().strip().split("\n") if l]
        self.assertGreater(len(lines), 0)
        entry = json.loads(lines[-1])
        self.assertEqual(entry["method"], "GET")
        self.assertEqual(entry["path"], "/health")
        self.assertEqual(entry["status_code"], 200)
        self.assertIn("duration_ms", entry)
        self.assertIn("timestamp", entry)
        self.assertIn("client", entry)

    def test_404_request_logged(self):
        """GET /nonexistent should produce a 404 access log entry."""
        url = f"http://localhost:{self.port}/nonexistent"
        try:
            urllib.request.urlopen(url)
        except Exception:
            pass
        time.sleep(0.1)
        import server
        if server._access_log_file:
            server._access_log_file.flush()
        with open(self.log_path, "r") as f:
            lines = [l for l in f.read().strip().split("\n") if l]
        entry = json.loads(lines[-1])
        self.assertEqual(entry["path"], "/nonexistent")
        self.assertEqual(entry["status_code"], 404)


if __name__ == "__main__":
    unittest.main()
