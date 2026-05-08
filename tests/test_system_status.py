
import os
import json
import threading
import time
import unittest
import urllib.request
from http.server import HTTPServer

from data_source import (
    LocalFileProvider,
    LiveDataProvider,
    AutoFailoverProvider,
    get_data_source,
    set_data_source,
    get_system_status,
)


class GetSystemStatusTest(unittest.TestCase):
    """Tests for get_system_status() module-level function."""

    def tearDown(self):
        set_data_source(LocalFileProvider())
        # Clean up any leftover uptime from other tests
        if hasattr(get_system_status, "_uptime_start"):
            delattr(get_system_status, "_uptime_start")

    def test_returns_system_field(self):
        """System status must include 'system' key."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        status = get_system_status(mock_data_dir)
        self.assertIn("system", status)
        self.assertIn(status["system"], ("ok", "degraded", "unhealthy"))

    def test_returns_provider_status(self):
        """Must include provider status dict."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        status = get_system_status(mock_data_dir)
        self.assertIn("provider", status)
        self.assertIn("name", status["provider"])
        self.assertIn("readiness", status["provider"])

    def test_returns_health(self):
        """Must include health check result."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        status = get_system_status(mock_data_dir)
        self.assertIn("health", status)
        self.assertIn("supported", status["health"])
        self.assertIn("status", status["health"])

    def test_returns_degradation(self):
        """Must include degradation visibility."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        status = get_system_status(mock_data_dir)
        self.assertIn("degradation", status)
        self.assertIn("is_degraded", status["degradation"])
        self.assertIn("active_path", status["degradation"])

    def test_returns_config(self):
        """Must include config metadata."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        status = get_system_status(mock_data_dir)
        self.assertIn("config", status)
        self.assertIn("source", status["config"])
        self.assertIn("reload_count", status["config"])

    def test_returns_data_dir(self):
        """Must include data directory metadata."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        status = get_system_status(mock_data_dir)
        self.assertIn("data_dir", status)
        self.assertIn("data_dir", status["data_dir"])

    def test_returns_timestamp(self):
        """Must include ISO 8601 timestamp."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        status = get_system_status(mock_data_dir)
        self.assertIn("timestamp", status)
        self.assertIn("T", status["timestamp"])
        self.assertTrue(status["timestamp"].endswith("Z"))

    def test_returns_uptime_none_without_server(self):
        """Uptime should be None when server not running."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        status = get_system_status(mock_data_dir)
        self.assertIsNone(status["uptime_seconds"])

    def test_system_ok_for_local_provider(self):
        """Local provider with valid data_dir should report 'ok'."""
        set_data_source(LocalFileProvider())
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        status = get_system_status(mock_data_dir)
        self.assertEqual(status["system"], "ok")

    def test_system_degraded_for_auto_provider(self):
        """Auto provider with skeleton live should report 'degraded'."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        local = LocalFileProvider()
        live = LiveDataProvider()
        auto = AutoFailoverProvider(live, local)
        set_data_source(auto)
        status = get_system_status(mock_data_dir)
        self.assertEqual(status["system"], "degraded")

    def test_uptime_when_server_sets_start(self):
        """Uptime should be a positive number when server start time is set."""
        get_system_status._uptime_start = time.monotonic() - 5.0
        try:
            mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
            status = get_system_status(mock_data_dir)
            self.assertIsNotNone(status["uptime_seconds"])
            self.assertGreaterEqual(status["uptime_seconds"], 4.0)
            self.assertLessEqual(status["uptime_seconds"], 10.0)
        finally:
            if hasattr(get_system_status, "_uptime_start"):
                delattr(get_system_status, "_uptime_start")


class ServerSystemStatusTest(unittest.TestCase):
    """Tests for GET /system/status endpoint."""

    @classmethod
    def setUpClass(cls):
        from server import AgentHandler
        cls.server = HTTPServer(("127.0.0.1", 0), AgentHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_system_status_endpoint(self):
        """Endpoint should return aggregated status with required keys."""
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/system/status"
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.read())
            self.assertIn("system", body)
            self.assertIn("provider", body)
            self.assertIn("health", body)
            self.assertIn("degradation", body)
            self.assertIn("config", body)
            self.assertIn("data_dir", body)
            self.assertIn("timestamp", body)

    def test_system_status_with_data_dir(self):
        """Endpoint should accept data_dir query parameter."""
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/system/status?data_dir=/tmp"
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.read())
            self.assertIn("system", body)
            # /tmp exists, so data_dir should be scanned
            self.assertIn("data_dir", body["data_dir"])


if __name__ == "__main__":
    unittest.main()
