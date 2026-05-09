
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
    CircuitBreaker,
    ProviderCapability,
    ProviderReadiness,
    get_data_source,
    set_data_source,
    create_provider,
    get_provider_status,
)


class ProviderCapabilityTest(unittest.TestCase):
    """Tests for ProviderCapability enum."""

    def test_read_capability_exists(self):
        self.assertEqual(ProviderCapability.READ.value, "read")

    def test_write_capability_exists(self):
        self.assertEqual(ProviderCapability.WRITE.value, "write")

    def test_health_check_capability_exists(self):
        self.assertEqual(ProviderCapability.HEALTH_CHECK.value, "health_check")


class ProviderReadinessTest(unittest.TestCase):
    """Tests for ProviderReadiness enum."""

    def test_ready_state(self):
        self.assertEqual(ProviderReadiness.READY.value, "ready")

    def test_not_configured_state(self):
        self.assertEqual(ProviderReadiness.NOT_CONFIGURED.value, "not_configured")

    def test_degraded_state(self):
        self.assertEqual(ProviderReadiness.DEGRADED.value, "degraded")

    def test_disabled_state(self):
        self.assertEqual(ProviderReadiness.DISABLED.value, "disabled")

    def test_circuit_open_state(self):
        self.assertEqual(ProviderReadiness.CIRCUIT_OPEN.value, "circuit_open")


class LocalFileProviderCapabilityTest(unittest.TestCase):
    """Tests for LocalFileProvider capabilities and readiness."""

    def setUp(self):
        self.provider = LocalFileProvider()
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def test_capabilities(self):
        caps = self.provider.capabilities()
        self.assertIn("read", caps)
        self.assertEqual(len(caps), 1)

    def test_readiness_with_valid_dir(self):
        self.assertEqual(self.provider.readiness(self.mock_data_dir), "ready")

    def test_readiness_with_invalid_dir(self):
        self.assertEqual(self.provider.readiness("/nonexistent/path"), "disabled")

    def test_readiness_without_data_dir(self):
        self.assertEqual(self.provider.readiness(), "ready")

    def test_status(self):
        status = self.provider.status(self.mock_data_dir)
        self.assertEqual(status["name"], "local")
        self.assertIn("read", status["capabilities"])
        self.assertEqual(status["readiness"], "ready")
        self.assertTrue(status["available"])


class LiveDataProviderCapabilityTest(unittest.TestCase):
    """Tests for LiveDataProvider capabilities and readiness."""

    def setUp(self):
        self.provider = LiveDataProvider()

    def test_capabilities(self):
        caps = self.provider.capabilities()
        self.assertIn("read", caps)
        self.assertIn("write", caps)
        self.assertIn("health_check", caps)
        self.assertEqual(len(caps), 3)

    def test_readiness_not_configured(self):
        self.assertEqual(self.provider.readiness(), "not_configured")
        self.assertEqual(self.provider.readiness("/tmp"), "not_configured")

    def test_status(self):
        status = self.provider.status()
        self.assertEqual(status["name"], "live")
        self.assertEqual(status["readiness"], "not_configured")
        self.assertIn("health_check", status["capabilities"])


class CustomLiveForStatus(LiveDataProvider):
    """Custom live provider for testing readiness states."""

    def __init__(self, available=True):
        self._available = available

    def is_available(self, data_dir):
        return self._available

    def load(self, data_dir, filename):
        return [{"order_id": "LIVE-001"}]


class AutoFailoverProviderStatusTest(unittest.TestCase):
    """Tests for AutoFailoverProvider capabilities, readiness, and extended status."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )
        self.local = LocalFileProvider()

    def test_capabilities_union(self):
        live = CustomLiveForStatus()
        provider = AutoFailoverProvider(live, self.local)
        caps = provider.capabilities()
        # Union of live (read, write, health_check) + local (read)
        self.assertIn("read", caps)
        self.assertIn("write", caps)
        self.assertIn("health_check", caps)

    def test_readiness_ready_when_live_available(self):
        live = CustomLiveForStatus(available=True)
        provider = AutoFailoverProvider(live, self.local)
        self.assertEqual(provider.readiness(self.mock_data_dir), "ready")

    def test_readiness_degraded_when_live_unavailable(self):
        live = CustomLiveForStatus(available=False)
        provider = AutoFailoverProvider(live, self.local)
        self.assertEqual(provider.readiness(self.mock_data_dir), "degraded")

    def test_readiness_disabled_when_both_unavailable(self):
        live = CustomLiveForStatus(available=False)
        provider = AutoFailoverProvider(live, self.local)
        self.assertEqual(provider.readiness("/nonexistent"), "disabled")

    def test_readiness_circuit_open(self):
        """When circuit breaker is OPEN, readiness should be circuit_open."""
        live = CustomLiveForStatus(available=True)
        # Circuit with threshold=1 so it trips on first failure
        provider = AutoFailoverProvider(
            live, self.local, failure_threshold=1, recovery_seconds=300
        )
        # Simulate a failure to open the circuit
        provider._circuit.record_failure()
        self.assertEqual(provider.readiness(self.mock_data_dir), "circuit_open")

    def test_extended_status(self):
        live = CustomLiveForStatus(available=True)
        provider = AutoFailoverProvider(live, self.local)
        status = provider.status(self.mock_data_dir)

        self.assertEqual(status["name"], "auto")
        self.assertIn("read", status["capabilities"])
        self.assertEqual(status["readiness"], "ready")

        # Should include sub-provider details
        self.assertIn("live_provider", status)
        self.assertEqual(status["live_provider"]["name"], "live")
        self.assertIn("fallback_provider", status)
        self.assertEqual(status["fallback_provider"]["name"], "local")

        # Circuit breaker should be None when threshold=0
        self.assertIsNone(status.get("circuit_breaker"))

    def test_extended_status_with_circuit(self):
        live = CustomLiveForStatus(available=True)
        provider = AutoFailoverProvider(
            live, self.local, failure_threshold=3, recovery_seconds=60
        )
        status = provider.status(self.mock_data_dir)
        self.assertIn("circuit_breaker", status)
        self.assertIn("state", status["circuit_breaker"])


class GetProviderStatusTest(unittest.TestCase):
    """Tests for get_provider_status() function."""

    def tearDown(self):
        set_data_source(LocalFileProvider())

    def test_returns_local_status(self):
        set_data_source(LocalFileProvider())
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        status = get_provider_status(mock_data_dir)
        self.assertEqual(status["name"], "local")
        self.assertEqual(status["readiness"], "ready")

    def test_returns_live_status(self):
        set_data_source(LiveDataProvider())
        status = get_provider_status()
        self.assertEqual(status["name"], "live")
        self.assertEqual(status["readiness"], "not_configured")


class ServerProviderStatusTest(unittest.TestCase):
    """Tests for GET /provider/status endpoint."""

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

    def test_provider_status_endpoint(self):
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/provider/status")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.read())
            self.assertIn("name", body)
            self.assertIn("capabilities", body)
            self.assertIn("readiness", body)


if __name__ == "__main__":
    unittest.main()
