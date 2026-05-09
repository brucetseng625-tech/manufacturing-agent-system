
import os
import tempfile
import unittest
import json
import threading
import time
from http.server import HTTPServer

from data_source import (
    DataProvider,
    LocalFileProvider,
    LiveDataProvider,
    AutoFailoverProvider,
    get_data_source,
    set_data_source,
    create_provider,
    get_provider_health,
)


class LocalFileProviderHealthTest(unittest.TestCase):
    """Tests for LocalFileProvider health check."""

    def setUp(self):
        self.provider = LocalFileProvider()
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def test_health_check_supported(self):
        result = self.provider.health_check(self.mock_data_dir)
        self.assertTrue(result["supported"])

    def test_health_check_ok_for_valid_dir(self):
        result = self.provider.health_check(self.mock_data_dir)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["details"]["exists"])
        self.assertTrue(result["details"]["readable"])

    def test_health_check_unreachable_for_missing_dir(self):
        result = self.provider.health_check("/nonexistent/path")
        self.assertEqual(result["status"], "unreachable")
        self.assertFalse(result["details"]["exists"])
        self.assertIn("error", result["details"])

    def test_health_check_no_data_dir(self):
        result = self.provider.health_check()
        self.assertEqual(result["status"], "ok")
        self.assertIn("No data_dir specified", result["details"]["message"])


class LiveDataProviderHealthTest(unittest.TestCase):
    """Tests for LiveDataProvider health check."""

    def setUp(self):
        self.provider = LiveDataProvider()

    def test_health_check_supported(self):
        result = self.provider.health_check()
        self.assertTrue(result["supported"])

    def test_health_check_not_configured(self):
        result = self.provider.health_check()
        self.assertEqual(result["status"], "not_configured")
        self.assertFalse(result["details"]["configured"])

    def test_health_check_with_data_dir(self):
        result = self.provider.health_check("/tmp")
        self.assertEqual(result["status"], "not_configured")


class CustomLiveForHealth(LiveDataProvider):
    """Custom live provider that simulates a configured, reachable source."""

    def __init__(self, available=True):
        self._available = available

    def is_available(self, data_dir):
        return self._available

    def load(self, data_dir, filename):
        return [{"order_id": "LIVE-001"}]

    def health_check(self, data_dir=None):
        if self._available:
            return {
                "supported": True,
                "status": "ok",
                "details": {"configured": True, "reachable": True},
            }
        return {
            "supported": True,
            "status": "unreachable",
            "details": {"configured": True, "reachable": False, "error": "Connection refused"},
        }


class AutoFailoverProviderHealthTest(unittest.TestCase):
    """Tests for AutoFailoverProvider health check."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )
        self.local = LocalFileProvider()

    def test_health_supported(self):
        live = CustomLiveForHealth(available=True)
        provider = AutoFailoverProvider(live, self.local)
        result = provider.health_check(self.mock_data_dir)
        self.assertTrue(result["supported"])

    def test_health_ok_when_live_available(self):
        live = CustomLiveForHealth(available=True)
        provider = AutoFailoverProvider(live, self.local)
        result = provider.health_check(self.mock_data_dir)
        self.assertEqual(result["status"], "ok")

    def test_health_degraded_when_live_unavailable(self):
        live = CustomLiveForHealth(available=False)
        provider = AutoFailoverProvider(live, self.local)
        result = provider.health_check(self.mock_data_dir)
        self.assertEqual(result["status"], "degraded")

    def test_health_details_include_sub_providers(self):
        live = CustomLiveForHealth(available=True)
        provider = AutoFailoverProvider(live, self.local)
        result = provider.health_check(self.mock_data_dir)
        self.assertIn("live", result["details"])
        self.assertIn("fallback", result["details"])
        self.assertIn("circuit_breaker", result["details"])

    def test_health_circuit_open(self):
        """When circuit breaker is OPEN, health status should be circuit_open."""
        live = CustomLiveForHealth(available=False)
        provider = AutoFailoverProvider(
            live, self.local, failure_threshold=1, recovery_seconds=300
        )
        provider._circuit.record_failure()
        result = provider.health_check(self.mock_data_dir)
        self.assertEqual(result["status"], "circuit_open")


class GetProviderHealthTest(unittest.TestCase):
    """Tests for get_provider_health() function."""

    def tearDown(self):
        set_data_source(LocalFileProvider())

    def test_returns_local_health(self):
        set_data_source(LocalFileProvider())
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        health = get_provider_health(mock_data_dir)
        self.assertTrue(health["supported"])
        self.assertEqual(health["status"], "ok")

    def test_returns_live_health(self):
        set_data_source(LiveDataProvider())
        health = get_provider_health()
        self.assertTrue(health["supported"])
        self.assertEqual(health["status"], "not_configured")


class ServerProviderHealthTest(unittest.TestCase):
    """Tests for GET /provider/health endpoint."""

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
        cls.server.server_close()
        cls.thread.join(timeout=1)

    def test_provider_health_endpoint(self):
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/provider/health")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.read())
            self.assertIn("supported", body)
            self.assertIn("status", body)
            self.assertIn("details", body)


if __name__ == "__main__":
    unittest.main()
