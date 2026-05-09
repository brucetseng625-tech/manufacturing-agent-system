
import os
import json
import threading
import time
import unittest
from unittest.mock import patch
import urllib.request
from http.server import HTTPServer

from data_source import (
    DataProvider,
    LocalFileProvider,
    LiveDataProvider,
    AutoFailoverProvider,
    CircuitBreaker,
    get_data_source,
    set_data_source,
    get_degradation_status,
)


class LocalFileProviderDegradationTest(unittest.TestCase):
    """Tests for LocalFileProvider degradation_status."""

    def setUp(self):
        self.provider = LocalFileProvider()
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def test_degradation_not_degraded(self):
        """Local-only mode is never degraded."""
        result = self.provider.degradation_status(self.mock_data_dir)
        self.assertFalse(result["is_degraded"])
        self.assertEqual(result["mode"], "local")
        self.assertEqual(result["active_path"], "local")
        self.assertEqual(result["reason"], "")
        self.assertIsNone(result["live_readiness"])
        self.assertIsNone(result["fallback_readiness"])
        self.assertEqual(result["recommendations"], [])


class LiveDataProviderDegradationTest(unittest.TestCase):
    """Tests for LiveDataProvider degradation_status."""

    def setUp(self):
        self.provider = LiveDataProvider()

    def test_degraded_when_not_configured(self):
        """Skeleton live provider reports degradation."""
        result = self.provider.degradation_status()
        self.assertTrue(result["is_degraded"])
        self.assertEqual(result["mode"], "live")
        self.assertEqual(result["active_path"], "none")
        self.assertIn("not configured", result["reason"])
        self.assertEqual(result["live_readiness"], "not_configured")

    @patch("data_source.get_config_value", return_value=False)
    def test_degraded_when_rollout_disabled(self, mock_cfg):
        """Live provider disabled by rollout should report degradation."""
        result = self.provider.degradation_status()
        self.assertTrue(result["is_degraded"])
        self.assertEqual(result["live_readiness"], "disabled")
        self.assertIn("rollout", result["reason"])


class CustomLiveForDegradation(LiveDataProvider):
    """Custom live provider for degradation testing."""

    def __init__(self, available=True):
        self._available = available

    def is_available(self, data_dir):
        return self._available

    def load(self, data_dir, filename):
        return [{"order_id": "LIVE-001"}]


class AutoFailoverProviderDegradationTest(unittest.TestCase):
    """Tests for AutoFailoverProvider degradation_status."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )
        self.local = LocalFileProvider()

    def test_degraded_when_live_not_configured(self):
        """Auto mode with skeleton live provider reports degradation."""
        live = LiveDataProvider()
        provider = AutoFailoverProvider(live, self.local)
        result = provider.degradation_status(self.mock_data_dir)
        self.assertTrue(result["is_degraded"])
        self.assertEqual(result["mode"], "auto")
        self.assertEqual(result["active_path"], "fallback")
        self.assertIn("not configured", result["reason"])
        self.assertEqual(result["live_readiness"], "not_configured")
        self.assertEqual(result["fallback_readiness"], "ready")

    def test_not_degraded_when_live_available(self):
        """Auto mode with available live provider is not degraded."""
        live = CustomLiveForDegradation(available=True)
        provider = AutoFailoverProvider(live, self.local)
        result = provider.degradation_status(self.mock_data_dir)
        self.assertFalse(result["is_degraded"])
        self.assertEqual(result["active_path"], "live")
        self.assertEqual(result["reason"], "")

    def test_degraded_when_circuit_open(self):
        """Open circuit breaker should report degraded with fallback active."""
        live = CustomLiveForDegradation(available=True)
        provider = AutoFailoverProvider(
            live, self.local, failure_threshold=1, recovery_seconds=300
        )
        provider._circuit.record_failure()
        result = provider.degradation_status(self.mock_data_dir)
        self.assertTrue(result["is_degraded"])
        self.assertEqual(result["active_path"], "fallback")
        self.assertIn("Circuit breaker is OPEN", result["reason"])
        self.assertEqual(result["circuit_breaker"]["state"], "open")

    def test_degraded_when_circuit_half_open(self):
        """Half-open circuit should report degraded with probing note."""
        live = CustomLiveForDegradation(available=False)
        provider = AutoFailoverProvider(
            live, self.local, failure_threshold=1, recovery_seconds=0
        )
        provider._circuit.record_failure()
        # recovery_seconds=0 means it should transition to half_open
        result = provider.degradation_status(self.mock_data_dir)
        cb_state = result["circuit_breaker"]["state"]
        self.assertIn(cb_state, ["half_open", "open"])
        if cb_state == "half_open":
            recs = result["recommendations"]
            self.assertTrue(any("probing" in r.lower() for r in recs))

    @patch("data_source.get_config_value")
    def test_degraded_when_rollout_auto_disabled(self, mock_cfg):
        """Auto provider disabled by rollout."""
        mock_cfg.side_effect = lambda key, default: (
            False if key == "rollout.auto.enabled" else True
        )
        live = CustomLiveForDegradation(available=True)
        provider = AutoFailoverProvider(live, self.local, failure_threshold=0)
        result = provider.degradation_status(self.mock_data_dir)
        self.assertTrue(result["is_degraded"])
        self.assertEqual(result["active_path"], "none")
        self.assertIn("rollout", result["reason"])

    @patch("data_source.get_config_value")
    def test_degraded_when_rollout_live_disabled(self, mock_cfg):
        """Auto mode with live disabled by rollout — uses fallback."""
        mock_cfg.side_effect = lambda key, default: (
            False if key == "rollout.live.enabled" else True
        )
        # Use skeleton live provider (always unavailable) + rollout disabled
        live = LiveDataProvider()
        provider = AutoFailoverProvider(live, self.local, failure_threshold=0)
        result = provider.degradation_status(self.mock_data_dir)
        # Live is disabled by rollout → fallback active → degraded
        self.assertTrue(result["is_degraded"])
        self.assertEqual(result["active_path"], "fallback")
        self.assertIn("disabled by rollout", result["reason"])
        self.assertEqual(result["live_readiness"], "disabled")

    def test_recommendations_when_live_not_configured(self):
        """Should recommend configuring live provider."""
        live = LiveDataProvider()
        provider = AutoFailoverProvider(live, self.local)
        result = provider.degradation_status(self.mock_data_dir)
        self.assertTrue(
            any("Configure live provider" in r for r in result["recommendations"])
        )

    def test_circuit_breaker_included_in_status(self):
        """Circuit breaker info should be included in degradation status."""
        live = CustomLiveForDegradation(available=True)
        provider = AutoFailoverProvider(
            live, self.local, failure_threshold=3, recovery_seconds=60
        )
        result = provider.degradation_status(self.mock_data_dir)
        self.assertIsNotNone(result["circuit_breaker"])
        self.assertIn("state", result["circuit_breaker"])
        self.assertIn("failure_threshold", result["circuit_breaker"])

    def test_no_circuit_breaker_when_disabled(self):
        """No circuit breaker config → None in degradation status."""
        live = CustomLiveForDegradation(available=True)
        provider = AutoFailoverProvider(live, self.local, failure_threshold=0)
        result = provider.degradation_status(self.mock_data_dir)
        self.assertIsNone(result["circuit_breaker"])


class GetDegradationStatusTest(unittest.TestCase):
    """Tests for get_degradation_status() module-level function."""

    def tearDown(self):
        set_data_source(LocalFileProvider())

    def test_returns_local_status(self):
        """Local provider should not be degraded."""
        set_data_source(LocalFileProvider())
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        status = get_degradation_status(mock_data_dir)
        self.assertFalse(status["is_degraded"])
        self.assertEqual(status["mode"], "local")

    def test_returns_live_status(self):
        """Live provider should report degradation (not configured)."""
        set_data_source(LiveDataProvider())
        status = get_degradation_status()
        self.assertTrue(status["is_degraded"])
        self.assertEqual(status["mode"], "live")

    def test_returns_auto_status(self):
        """Auto provider should report degradation (live not configured)."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        local = LocalFileProvider()
        live = LiveDataProvider()
        auto = AutoFailoverProvider(live, local)
        set_data_source(auto)
        status = get_degradation_status(mock_data_dir)
        self.assertTrue(status["is_degraded"])
        self.assertEqual(status["mode"], "auto")
        self.assertEqual(status["active_path"], "fallback")


class ServerDegradationStatusTest(unittest.TestCase):
    """Tests for GET /system/degradation-status endpoint."""

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

    def test_degradation_status_endpoint(self):
        """Endpoint should return degradation status with required keys."""
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/system/degradation-status"
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.read())
            self.assertIn("is_degraded", body)
            self.assertIn("mode", body)
            self.assertIn("active_path", body)
            self.assertIn("reason", body)
            self.assertIn("live_readiness", body)
            self.assertIn("fallback_readiness", body)
            self.assertIn("recommendations", body)

    def test_degradation_status_with_data_dir(self):
        """Endpoint should accept data_dir query parameter."""
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/system/degradation-status?data_dir=/tmp"
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.read())
            self.assertIn("is_degraded", body)


if __name__ == "__main__":
    unittest.main()
