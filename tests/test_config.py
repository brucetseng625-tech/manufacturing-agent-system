import json
import os
import tempfile
import unittest
from unittest.mock import patch

from config import (
    DEFAULT_CONFIG,
    get_config,
    get_config_metadata,
    get_config_value,
    load_config,
    reload_config,
    sanitize_config,
    set_config,
    validate_config,
)


class ConfigDefaultsTest(unittest.TestCase):
    def setUp(self):
        reload_config("/nonexistent/config.json")

    def test_default_sections_exist(self):
        for section in ("server", "runtime", "paths", "security", "integrations"):
            self.assertIn(section, DEFAULT_CONFIG)

    def test_default_values(self):
        self.assertEqual(DEFAULT_CONFIG["server"]["port"], 8000)
        self.assertEqual(DEFAULT_CONFIG["runtime"]["default_data_source"], "local")
        self.assertEqual(DEFAULT_CONFIG["runtime"]["workspace_mode"], "erp")
        self.assertEqual(DEFAULT_CONFIG["runtime"]["history_last"], 10)


class ConfigLoadingTest(unittest.TestCase):
    def setUp(self):
        set_config(DEFAULT_CONFIG)

    def test_load_default_when_no_file(self):
        cfg = load_config("/nonexistent/config.json")
        self.assertEqual(cfg["_source"], "default")
        self.assertEqual(cfg["server"]["port"], 8000)

    def test_load_custom_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump({"server": {"port": 9000}, "runtime": {"history_last": 5}}, tmp)
            tmp_path = tmp.name
        try:
            cfg = load_config(tmp_path)
            self.assertEqual(cfg["server"]["port"], 9000)
            self.assertEqual(cfg["runtime"]["history_last"], 5)
            self.assertEqual(cfg["runtime"]["default_data_source"], "local")
        finally:
            os.unlink(tmp_path)

    def test_env_override(self):
        with patch.dict(os.environ, {"MAS_SERVER_PORT": "9100", "MAS_DEFAULT_DATA_SOURCE": "auto"}):
            cfg = load_config("/nonexistent/config.json")
            self.assertEqual(cfg["server"]["port"], 9100)
            self.assertEqual(cfg["runtime"]["default_data_source"], "auto")

    def test_validation_rejects_invalid_port(self):
        with self.assertRaises(ValueError):
            validate_config({"server": {"port": 70000}, "runtime": {"default_data_source": "local", "history_last": 10, "metrics_window_hours": 24}})

    def test_validation_rejects_invalid_data_source(self):
        with self.assertRaises(ValueError):
            validate_config({"server": {"port": 8000}, "runtime": {"default_data_source": "bad", "history_last": 10, "metrics_window_hours": 24}})


class ConfigAccessTest(unittest.TestCase):
    def setUp(self):
        reload_config("/nonexistent/config.json")
        set_config(DEFAULT_CONFIG)

    def test_get_config_value(self):
        self.assertEqual(get_config_value("server.port"), 8000)
        self.assertEqual(get_config_value("runtime.history_last"), 10)

    def test_sanitize_config_masks_tokens(self):
        cfg = {
            "security": {"api_token": "secret-value"},
            "nested": {"child_secret": "abc"},
        }
        sanitized = sanitize_config(cfg)
        self.assertEqual(sanitized["security"]["api_token"], "***REDACTED***")
        self.assertEqual(sanitized["nested"]["child_secret"], "***REDACTED***")

    def test_reload_config_success(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump({"server": {"port": 8100}}, tmp)
            tmp_path = tmp.name
        try:
            result = reload_config(tmp_path)
            self.assertTrue(result["success"])
            self.assertEqual(get_config(raw=True)["server"]["port"], 8100)
            self.assertGreaterEqual(get_config_metadata()["reload_count"], 1)
        finally:
            os.unlink(tmp_path)

    def test_reload_config_failure(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            tmp.write("{bad json")
            tmp_path = tmp.name
        try:
            result = reload_config(tmp_path)
            self.assertFalse(result["success"])
            self.assertTrue(result["error"])
        finally:
            os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main()


class ConfigSheetsModeTest(unittest.TestCase):
    def test_validate_accepts_sheets_mode(self):
        from config import validate_config
        cfg = {"runtime": {"default_data_source": "sheets", "history_last": 10, "metrics_window_hours": 24}, "server": {"port": 8000}}
        self.assertTrue(validate_config(cfg))
