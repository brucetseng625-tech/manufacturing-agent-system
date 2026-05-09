"""Tests for P10-1 HttpReadonlyProvider."""

import json
import os
import threading
import time
import unittest
from http.server import HTTPServer, BaseHTTPRequestHandler
from unittest.mock import patch

from data_source import HttpReadonlyProvider, LocalFileProvider


class _MockJSONHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler that serves mock JSON data."""

    def do_GET(self):
        if self.path == "/orders":
            data = [{"order_id": "ORD-1", "status": "pending"}, {"order_id": "ORD-2", "status": "shipped"}]
        elif self.path == "/single":
            data = {"order_id": "ORD-3", "status": "complete"}
        elif self.path == "/empty":
            data = []
        elif self.path == "/health" or self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
            return
        elif self.path == "/404":
            self.send_response(404)
            self.end_headers()
            return
        else:
            self.send_response(500)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        pass  # Silence logs


class HttpReadonlyProviderConfigTest(unittest.TestCase):
    """Tests for provider configuration."""

    def test_from_config_returns_none_without_url(self):
        """Without base_url config, _from_config returns None."""
        with patch("data_source.get_config_value") as mock_cfg:
            mock_cfg.side_effect = lambda key, default: {
                "live_provider.http.base_url": "",
            }.get(key, default)
            result = HttpReadonlyProvider._from_config()
            self.assertIsNone(result)

    def test_from_config_returns_provider_with_url(self):
        """With base_url config, _from_config returns HttpReadonlyProvider."""
        with patch("data_source.get_config_value") as mock_cfg:
            mock_cfg.side_effect = lambda key, default: {
                "live_provider.http.base_url": "https://api.example.com/data",
                "live_provider.http.timeout_seconds": 15,
                "live_provider.http.health_path": "/health",
            }.get(key, default)
            result = HttpReadonlyProvider._from_config()
            self.assertIsInstance(result, HttpReadonlyProvider)
            self.assertEqual(result._base_url, "https://api.example.com/data")
            self.assertEqual(result._timeout, 15)
            self.assertEqual(result._health_path, "/health")


class HttpReadonlyProviderLiveTest(unittest.TestCase):
    """Integration tests using a real HTTP server."""

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _MockJSONHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()
        time.sleep(0.1)
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_load_list_data(self):
        """Loading from endpoint returning JSON list should work."""
        provider = HttpReadonlyProvider(self.base_url)
        result = provider.load("", "orders.json")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["order_id"], "ORD-1")

    def test_load_single_object_wrapped(self):
        """Loading from endpoint returning JSON object should wrap in list."""
        provider = HttpReadonlyProvider(self.base_url)
        result = provider.load("", "single.json")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["order_id"], "ORD-3")

    def test_load_empty_list(self):
        """Loading from endpoint returning empty list should work."""
        provider = HttpReadonlyProvider(self.base_url)
        result = provider.load("", "empty.json")
        self.assertEqual(result, [])

    def test_load_raises_on_404(self):
        """Loading from 404 endpoint should raise RuntimeError."""
        provider = HttpReadonlyProvider(self.base_url)
        with self.assertRaises(RuntimeError) as ctx:
            provider.load("", "404.json")
        self.assertIn("HTTP 404", str(ctx.exception))

    def test_health_check_ok(self):
        """Health check to /health should return ok."""
        provider = HttpReadonlyProvider(self.base_url, health_path="/health")
        result = provider.health_check()
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["details"]["configured"])

    def test_health_check_base_url(self):
        """Health check to base URL without health_path should return ok."""
        provider = HttpReadonlyProvider(self.base_url)
        result = provider.health_check()
        self.assertEqual(result["status"], "ok")

    def test_name(self):
        """Provider name should be http_readonly."""
        provider = HttpReadonlyProvider(self.base_url)
        self.assertEqual(provider.name(), "http_readonly")

    def test_capabilities(self):
        """Capabilities should include READ and HEALTH_CHECK."""
        provider = HttpReadonlyProvider(self.base_url)
        caps = provider.capabilities()
        self.assertIn("read", caps)
        self.assertIn("health_check", caps)
        self.assertNotIn("write", caps)

    def test_is_available_when_configured(self):
        """Provider should be available when base_url is set."""
        provider = HttpReadonlyProvider(self.base_url)
        self.assertTrue(provider.is_available(""))

    def test_is_available_when_not_configured(self):
        """Provider should not be available without base_url."""
        provider = HttpReadonlyProvider()
        self.assertFalse(provider.is_available(""))

    def test_readiness_ready(self):
        """Provider should be ready when configured and rollout enabled."""
        with patch("data_source.get_config_value") as mock_cfg:
            mock_cfg.side_effect = lambda key, default: {
                "rollout.live.enabled": True,
            }.get(key, default)
            provider = HttpReadonlyProvider(self.base_url)
            self.assertEqual(provider.readiness(), "ready")

    def test_readiness_not_configured(self):
        """Provider should be not_configured without base_url."""
        with patch("data_source.get_config_value") as mock_cfg:
            mock_cfg.side_effect = lambda key, default: {
                "rollout.live.enabled": True,
            }.get(key, default)
            provider = HttpReadonlyProvider()
            self.assertEqual(provider.readiness(), "not_configured")

    def test_readiness_disabled(self):
        """Provider should be disabled when rollout disabled."""
        with patch("data_source.get_config_value") as mock_cfg:
            mock_cfg.side_effect = lambda key, default: {
                "rollout.live.enabled": False,
            }.get(key, default)
            provider = HttpReadonlyProvider(self.base_url)
            self.assertEqual(provider.readiness(), "disabled")

    def test_degradation_status_configured_and_healthy(self):
        """After healthy check, degradation should show not degraded."""
        provider = HttpReadonlyProvider(self.base_url, health_path="/health")
        provider.health_check()
        status = provider.degradation_status()
        self.assertFalse(status["is_degraded"])
        self.assertEqual(status["active_path"], "http")
        self.assertEqual(status["live_readiness"], "ready")

    def test_degradation_status_not_configured(self):
        """Unconfigured provider should show degraded."""
        provider = HttpReadonlyProvider()
        status = provider.degradation_status()
        self.assertTrue(status["is_degraded"])
        self.assertEqual(status["reason"], "HTTP base_url not configured")

    def test_load_raises_when_not_configured(self):
        """Load without base_url should raise RuntimeError."""
        provider = HttpReadonlyProvider()
        with self.assertRaises(RuntimeError) as ctx:
            provider.load("", "orders.json")
        self.assertIn("not configured", str(ctx.exception))

    def test_load_unreachable_url(self):
        """Load from unreachable URL should raise RuntimeError."""
        provider = HttpReadonlyProvider("http://192.0.2.1:1", timeout=1)
        with self.assertRaises(RuntimeError):
            provider.load("", "orders.json")


if __name__ == "__main__":
    unittest.main()
