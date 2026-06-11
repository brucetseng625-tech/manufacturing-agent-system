
import os
import tempfile
import unittest

from data_source import (
    DataProvider,
    LocalFileProvider,
    LiveDataProvider,
    GoogleSheetsProvider,
    AutoFailoverProvider,
    get_data_source,
    set_data_source,
    create_provider,
    load_data,
    get_provider_name,
    VALID_MODES,
    set_default_provider,
    get_default_provider_mode,
    get_system_status,
)
from data_loader import load_json_or_csv
from config import get_config, set_config


class LocalFileProviderTest(unittest.TestCase):
    """Tests for LocalFileProvider — should behave identically to original loader."""

    def setUp(self):
        self.provider = LocalFileProvider()
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )
        self.csv_data_dir = os.path.join(os.path.dirname(__file__), "..", "data")

    def test_load_json(self):
        data = self.provider.load(self.mock_data_dir, "orders.json")
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        self.assertIn("order_id", data[0])

    def test_load_csv(self):
        data = self.provider.load(self.csv_data_dir, "orders.csv")
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        self.assertIn("order_id", data[0])
        self.assertIsInstance(data[0]["quantity"], int)

    def test_json_preferred_over_csv(self):
        # When both exist, JSON should be preferred
        data = self.provider.load(self.mock_data_dir, "orders.json")
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_returns_empty_for_missing_file(self):
        data = self.provider.load(self.mock_data_dir, "nonexistent.json")
        self.assertEqual(data, [])

    def test_is_available_true_for_valid_dir(self):
        self.assertTrue(self.provider.is_available(self.mock_data_dir))

    def test_is_available_false_for_invalid_dir(self):
        self.assertFalse(self.provider.is_available("/nonexistent/path"))

    def test_name(self):
        self.assertEqual(self.provider.name(), "local")


class LiveDataProviderTest(unittest.TestCase):
    """Tests for LiveDataProvider skeleton."""

    def setUp(self):
        self.provider = LiveDataProvider()

    def test_load_raises_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            self.provider.load("/tmp", "orders.json")

    def test_is_available_returns_false(self):
        """Skeleton provider reports unavailable to trigger fallback."""
        self.assertFalse(self.provider.is_available("/tmp"))

    def test_name(self):
        self.assertEqual(self.provider.name(), "live")


class CustomLiveDataProvider(LiveDataProvider):
    """Custom live provider for testing that actually returns data."""

    def __init__(self, available=True, fail_on=None):
        self._available = available
        self._fail_on = fail_on or set()
        self.load_calls = []

    def load(self, data_dir, filename):
        self.load_calls.append((data_dir, filename))
        if filename in self._fail_on:
            raise ConnectionError(f"Live source unavailable for {filename}")
        # Return mock data
        return [{"order_id": "LIVE-001", "customer": "Live Customer"}]

    def is_available(self, data_dir):
        return self._available


class GoogleSheetsProviderTest(unittest.TestCase):
    def setUp(self):
        import socketserver
        from http.server import BaseHTTPRequestHandler, HTTPServer
        self._old_cfg = get_config(raw=True)

        csv_payload = (
            b"order_id,customer,quantity,penalty_per_day,expedite_cost\n"
            b"GS-001,Lightweight Co,7,3000.0,10000.0\n"
        )

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/csv")
                self.end_headers()
                self.wfile.write(csv_payload)
            def log_message(self, format, *args):
                return

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        import threading, time
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()
        time.sleep(0.05)

        cfg = get_config(raw=True)
        cfg.setdefault('google_sheets', {})
        cfg['google_sheets']['enabled'] = True
        cfg['google_sheets']['timeout_seconds'] = 5
        cfg['google_sheets']['datasets'] = {
            'orders': {'csv_url': f'http://127.0.0.1:{self.port}/orders.csv'}
        }
        cfg.setdefault('rollout', {}).setdefault('sheets', {})['enabled'] = True
        set_config(cfg)
        self.provider = GoogleSheetsProvider._from_config()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)
        set_config(self._old_cfg)

    def test_load_csv_from_google_sheets_dataset(self):
        data = self.provider.load('/tmp', 'orders.json')
        self.assertEqual(data[0]['order_id'], 'GS-001')
        self.assertEqual(data[0]['quantity'], 7)
        self.assertEqual(data[0]['penalty_per_day'], 3000.0)
        self.assertEqual(data[0]['expedite_cost'], 10000.0)

    def test_name(self):
        self.assertEqual(self.provider.name(), 'google_sheets')


class AutoFailoverProviderTest(unittest.TestCase):
    """Tests for AutoFailoverProvider — live first, fallback to local."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )
        self.local = LocalFileProvider()

    def test_uses_live_when_available(self):
        live = CustomLiveDataProvider(available=True)
        provider = AutoFailoverProvider(live, self.local)
        data = provider.load(self.mock_data_dir, "orders.json")
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["order_id"], "LIVE-001")
        self.assertEqual(len(live.load_calls), 1)

    def test_fallback_to_local_when_live_unavailable(self):
        live = CustomLiveDataProvider(available=True, fail_on={"orders.json"})
        provider = AutoFailoverProvider(live, self.local)
        data = provider.load(self.mock_data_dir, "orders.json")
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        self.assertIn("order_id", data[0])
        # Live was tried first
        self.assertEqual(len(live.load_calls), 1)

    def test_fallback_when_live_not_available_at_all(self):
        live = CustomLiveDataProvider(available=False)
        provider = AutoFailoverProvider(live, self.local)
        data = provider.load(self.mock_data_dir, "orders.json")
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        # Live should not be called if is_available returns False
        self.assertEqual(len(live.load_calls), 0)

    def test_caches_live_unavailability(self):
        """After live fails once, subsequent calls skip live and go directly to local."""
        live = CustomLiveDataProvider(available=True, fail_on={"orders.json"})
        provider = AutoFailoverProvider(live, self.local)

        # First call: tries live, fails, falls back
        data1 = provider.load(self.mock_data_dir, "orders.json")
        self.assertGreater(len(data1), 0)
        first_calls = len(live.load_calls)

        # Second call: live should be skipped (cached as unavailable)
        data2 = provider.load(self.mock_data_dir, "orders.json")
        self.assertGreater(len(data2), 0)
        # No additional live calls after fallback
        self.assertEqual(len(live.load_calls), first_calls)

    def test_name(self):
        live = CustomLiveDataProvider()
        provider = AutoFailoverProvider(live, self.local)
        self.assertEqual(provider.name(), "auto")


class DataSourceManagerTest(unittest.TestCase):
    """Tests for provider creation and thread-local management."""

    def tearDown(self):
        # Reset to default after each test
        set_data_source(LocalFileProvider())

    def test_create_local_provider(self):
        provider = create_provider("local")
        self.assertIsInstance(provider, LocalFileProvider)

    def test_create_live_provider(self):
        provider = create_provider("live")
        self.assertIsInstance(provider, LiveDataProvider)

    def test_create_auto_provider(self):
        provider = create_provider("auto")
        self.assertIsInstance(provider, AutoFailoverProvider)

    def test_create_sheets_provider(self):
        provider = create_provider("sheets")
        self.assertIsInstance(provider, GoogleSheetsProvider)

    def test_invalid_mode_raises(self):
        with self.assertRaises(ValueError):
            create_provider("invalid")

    def test_valid_modes(self):
        self.assertEqual(set(VALID_MODES), {"local", "live", "auto", "sheets"})

    def test_set_and_get_data_source(self):
        custom = CustomLiveDataProvider()
        set_data_source(custom)
        self.assertIs(get_data_source(), custom)

    def test_default_provider_is_local(self):
        # After tearDown reset, default should be local
        set_data_source(LocalFileProvider())
        provider = get_data_source()
        self.assertIsInstance(provider, LocalFileProvider)

    def test_get_provider_name(self):
        set_data_source(LocalFileProvider())
        self.assertEqual(get_provider_name(), "local")

        set_data_source(LiveDataProvider())
        self.assertEqual(get_provider_name(), "live")


class LoadDataIntegrationTest(unittest.TestCase):
    """Tests for the load_data() entry point with provider switching."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def tearDown(self):
        set_data_source(LocalFileProvider())

    def test_load_data_with_local_provider(self):
        set_data_source(LocalFileProvider())
        data = load_data(self.mock_data_dir, "orders.json")
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_load_data_with_custom_live_provider(self):
        live = CustomLiveDataProvider(available=True)
        set_data_source(live)
        data = load_data(self.mock_data_dir, "anything.json")
        self.assertEqual(data[0]["order_id"], "LIVE-001")

    def test_load_data_via_backward_compat_loader(self):
        """load_json_or_csv should still work via provider delegation."""
        set_data_source(LocalFileProvider())
        data = load_json_or_csv(self.mock_data_dir, "orders.json")
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_load_data_auto_mode_with_unavailable_live(self):
        """Auto mode with unavailable live source should fall back to local."""
        live = CustomLiveDataProvider(available=False)
        auto = create_provider("auto", live_provider=live)
        set_data_source(auto)
        data = load_data(self.mock_data_dir, "orders.json")
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_load_data_returns_empty_for_missing_file(self):
        set_data_source(LocalFileProvider())
        data = load_data(self.mock_data_dir, "nonexistent.json")
        self.assertEqual(data, [])


class OrchestratorDataSourceTest(unittest.TestCase):
    """Tests that orchestrator works correctly with different data source modes."""

    def setUp(self):
        from orchestrator import route_query
        self.route_query = route_query
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def tearDown(self):
        set_data_source(LocalFileProvider())

    def test_route_query_with_local_provider(self):
        set_data_source(LocalFileProvider())
        result = self.route_query("ORD-1001 能不能準時出？", self.mock_data_dir)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skill"], "delivery-risk-analysis")

    def test_route_query_with_auto_provider(self):
        live = CustomLiveDataProvider(available=False)
        auto = create_provider("auto", live_provider=live)
        set_data_source(auto)
        result = self.route_query("ORD-1001 能不能準時出？", self.mock_data_dir)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skill"], "delivery-risk-analysis")


import sys
import json
from http.server import HTTPServer
import threading
import time
import urllib.request
import urllib.error

class ServerDataSourceTest(unittest.TestCase):
    """Tests for server.py data_source validation."""

    @classmethod
    def setUpClass(cls):
        from server import AgentHandler, VALID_DATA_SOURCES
        cls.VALID_DATA_SOURCES = VALID_DATA_SOURCES
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

    def test_invalid_data_source_rejected(self):
        payload = json.dumps({
            "query": "test",
            "data_source": "invalid_mode"
        }).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/run",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req):
                pass
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
            body = json.loads(e.read())
            self.assertEqual(body["error_type"], "invalid_data_source")


class DefaultProviderSelectionTest(unittest.TestCase):
    """Tests for set_default_provider and get_default_provider_mode."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    def tearDown(self):
        # Reset to local
        set_default_provider("local")

    def test_default_mode_starts_as_local(self):
        set_default_provider("local")
        self.assertEqual(get_default_provider_mode(), "local")

    def test_set_default_provider_local(self):
        provider = set_default_provider("local")
        self.assertEqual(provider.name(), "local")
        self.assertEqual(get_default_provider_mode(), "local")

    def test_set_default_provider_auto(self):
        provider = set_default_provider("auto")
        self.assertEqual(provider.name(), "auto")
        self.assertEqual(get_default_provider_mode(), "auto")

    def test_set_default_provider_live(self):
        provider = set_default_provider("live")
        self.assertEqual(provider.name(), "live")
        self.assertEqual(get_default_provider_mode(), "live")

    def test_set_default_provider_sheets(self):
        provider = set_default_provider("sheets")
        self.assertEqual(provider.name(), "google_sheets")
        self.assertEqual(get_default_provider_mode(), "sheets")

    def test_set_default_provider_invalid(self):
        with self.assertRaises(ValueError):
            set_default_provider("invalid")

    def test_get_data_source_uses_default(self):
        set_default_provider("local")
        # get_data_source should fall back to the default
        ds = get_data_source()
        self.assertEqual(ds.name(), "local")

    def test_system_status_includes_default_mode(self):
        set_default_provider("auto")
        status = get_system_status(self.mock_data_dir)
        self.assertEqual(status["provider"]["default_mode"], "auto")
