import json
import os
import unittest
import threading
import time
import urllib.request
import urllib.error
from http.server import HTTPServer

from server import AgentHandler, _check_auth, _PROTECTED_PATHS
from config import get_config_value, reload_config, set_config, DEFAULT_CONFIG


PORT = 0


class AuthProtectedEndpointsTest(unittest.TestCase):
    """Verify all mutation endpoints are in the protected set."""

    def test_run_is_protected(self):
        self.assertIn("/run", _PROTECTED_PATHS)

    def test_batch_is_protected(self):
        self.assertIn("/batch", _PROTECTED_PATHS)

    def test_config_reload_is_protected(self):
        self.assertIn("/config/reload", _PROTECTED_PATHS)

    def test_policy_reload_is_protected(self):
        self.assertIn("/policy/reload", _PROTECTED_PATHS)

    def test_health_is_not_protected(self):
        self.assertNotIn("/health", _PROTECTED_PATHS)

    def test_metrics_is_not_protected(self):
        self.assertNotIn("/metrics", _PROTECTED_PATHS)

    def test_history_is_not_protected(self):
        self.assertNotIn("/history", _PROTECTED_PATHS)

    def test_skills_is_not_protected(self):
        self.assertNotIn("/skills", _PROTECTED_PATHS)

    def test_config_read_is_not_protected(self):
        self.assertNotIn("/config", _PROTECTED_PATHS)

    def test_data_status_is_not_protected(self):
        self.assertNotIn("/data/status", _PROTECTED_PATHS)


class AuthCheckUnitTest(unittest.TestCase):
    """Unit tests for _check_auth function."""

    def _make_handler(self, path, auth_header=None, api_token=None):
        """Create a minimal mock handler."""
        class FakeHandler:
            def __init__(self):
                self.headers = {}
                if auth_header:
                    self.headers["Authorization"] = auth_header
                if api_token:
                    self.headers["X-API-Token"] = api_token
                self._response = None

            def _send_error_response(self, status, error_type, message):
                self._response = (status, error_type, message)

        return FakeHandler()

    def test_no_token_allows_all(self):
        """When no token is configured, all paths are allowed."""
        handler = self._make_handler("/run")
        result = _check_auth(handler, "/run")
        self.assertTrue(result)
        self.assertIsNone(handler._response)

    def test_protected_path_with_valid_bearer_token(self):
        handler = self._make_handler("/run", auth_header="Bearer my-secret")
        # Simulate token set in config
        original = DEFAULT_CONFIG.get("security", {}).get("api_token")
        DEFAULT_CONFIG.setdefault("security", {})["api_token"] = "my-secret"
        try:
            result = _check_auth(handler, "/run")
            self.assertTrue(result)
            self.assertIsNone(handler._response)
        finally:
            DEFAULT_CONFIG["security"]["api_token"] = original

    def test_protected_path_with_valid_x_api_token(self):
        handler = self._make_handler("/run", api_token="my-secret")
        original = DEFAULT_CONFIG.get("security", {}).get("api_token")
        DEFAULT_CONFIG.setdefault("security", {})["api_token"] = "my-secret"
        try:
            result = _check_auth(handler, "/run")
            self.assertTrue(result)
            self.assertIsNone(handler._response)
        finally:
            DEFAULT_CONFIG["security"]["api_token"] = original

    def test_protected_path_with_wrong_token(self):
        handler = self._make_handler("/run", auth_header="Bearer wrong-token")
        original = DEFAULT_CONFIG.get("security", {}).get("api_token")
        DEFAULT_CONFIG.setdefault("security", {})["api_token"] = "my-secret"
        try:
            result = _check_auth(handler, "/run")
            self.assertFalse(result)
            self.assertEqual(handler._response[0], 401)
            self.assertEqual(handler._response[1], "unauthorized")
        finally:
            DEFAULT_CONFIG["security"]["api_token"] = original

    def test_protected_path_with_no_header(self):
        handler = self._make_handler("/run")
        original = DEFAULT_CONFIG.get("security", {}).get("api_token")
        DEFAULT_CONFIG.setdefault("security", {})["api_token"] = "my-secret"
        try:
            result = _check_auth(handler, "/run")
            self.assertFalse(result)
            self.assertEqual(handler._response[0], 401)
        finally:
            DEFAULT_CONFIG["security"]["api_token"] = original

    def test_unprotected_path_bypasses_auth(self):
        """Even with token configured, unprotected paths are allowed."""
        handler = self._make_handler("/health")
        original = DEFAULT_CONFIG.get("security", {}).get("api_token")
        DEFAULT_CONFIG.setdefault("security", {})["api_token"] = "my-secret"
        try:
            result = _check_auth(handler, "/health")
            self.assertTrue(result)
            self.assertIsNone(handler._response)
        finally:
            DEFAULT_CONFIG["security"]["api_token"] = original


class AuthIntegrationTest(unittest.TestCase):
    """Integration tests using a real HTTP server."""

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("localhost", 0), AgentHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()
        time.sleep(0.5)
        # Save original config state
        cls.original_token = DEFAULT_CONFIG.get("security", {}).get("api_token")
        DEFAULT_CONFIG.setdefault("security", {})["api_token"] = "test-token-123"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=1)
        DEFAULT_CONFIG["security"]["api_token"] = cls.original_token

    def test_get_health_without_token(self):
        """GET /health works without token (unprotected)."""
        url = f"http://localhost:{self.port}/health"
        with urllib.request.urlopen(url) as response:
            self.assertEqual(response.status, 200)

    def test_get_config_without_token(self):
        """GET /config works without token (unprotected)."""
        url = f"http://localhost:{self.port}/config"
        with urllib.request.urlopen(url) as response:
            self.assertEqual(response.status, 200)

    def test_post_run_without_token_returns_401(self):
        """POST /run without token returns 401 when token is configured."""
        url = f"http://localhost:{self.port}/run"
        payload = json.dumps({"query": "test"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req)
            self.fail("Expected 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)
            data = json.loads(e.read())
            self.assertEqual(data["error_type"], "unauthorized")

    def test_post_run_with_bearer_token_succeeds(self):
        """POST /run with valid Bearer token passes auth."""
        url = f"http://localhost:{self.port}/run"
        payload = json.dumps({"query": "test"}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer test-token-123",
        }
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        # Will fail due to invalid query, but should NOT be 401
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            self.assertNotEqual(e.code, 401)

    def test_post_run_with_x_api_token_succeeds(self):
        """POST /run with valid X-API-Token header passes auth."""
        url = f"http://localhost:{self.port}/run"
        payload = json.dumps({"query": "test"}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-API-Token": "test-token-123",
        }
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            self.assertNotEqual(e.code, 401)

    def test_post_run_with_wrong_token_returns_401(self):
        """POST /run with wrong token returns 401."""
        url = f"http://localhost:{self.port}/run"
        payload = json.dumps({"query": "test"}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer wrong-token",
        }
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            urllib.request.urlopen(req)
            self.fail("Expected 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_post_batch_without_token_returns_401(self):
        """POST /batch without token returns 401."""
        url = f"http://localhost:{self.port}/batch"
        payload = json.dumps({"queries": []}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req)
            self.fail("Expected 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_post_policy_reload_without_token_returns_401(self):
        """POST /policy/reload without token returns 401."""
        url = f"http://localhost:{self.port}/policy/reload"
        payload = json.dumps({}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req)
            self.fail("Expected 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_post_config_reload_without_token_returns_401(self):
        """POST /config/reload without token returns 401."""
        url = f"http://localhost:{self.port}/config/reload"
        payload = json.dumps({}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req)
            self.fail("Expected 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)


class DevModeNoTokenTest(unittest.TestCase):
    """Verify that without a configured token, all endpoints are accessible."""

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("localhost", 0), AgentHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()
        time.sleep(0.5)
        cls.original_token = DEFAULT_CONFIG.get("security", {}).get("api_token")
        DEFAULT_CONFIG["security"]["api_token"] = None

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=1)
        DEFAULT_CONFIG["security"]["api_token"] = cls.original_token

    def test_post_run_without_configured_token(self):
        """POST /run works when no token is configured (dev mode)."""
        url = f"http://localhost:{self.port}/run"
        payload = json.dumps({"query": "ORD-1001 出貨"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            # May return 400 for bad query, but NOT 401
            self.assertNotEqual(e.code, 401)


if __name__ == "__main__":
    unittest.main()
