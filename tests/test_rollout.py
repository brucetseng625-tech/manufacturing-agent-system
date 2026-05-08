
import os
import unittest
from unittest.mock import patch

from data_source import (
    LocalFileProvider,
    LiveDataProvider,
    AutoFailoverProvider,
    ProviderReadiness,
)


class LocalProviderRolloutTest(unittest.TestCase):
    """Tests for LocalFileProvider rollout controls."""

    def setUp(self):
        self.provider = LocalFileProvider()
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )

    @patch("data_source.get_config_value", return_value=True)
    def test_local_enabled_default(self, mock_cfg):
        mock_cfg.return_value = True
        self.assertTrue(self.provider.is_available(self.mock_data_dir))
        self.assertEqual(self.provider.readiness(self.mock_data_dir), ProviderReadiness.READY.value)

    @patch("data_source.get_config_value", return_value=False)
    def test_local_disabled_by_rollout(self, mock_cfg):
        mock_cfg.return_value = False
        self.assertFalse(self.provider.is_available(self.mock_data_dir))
        self.assertEqual(self.provider.readiness(self.mock_data_dir), ProviderReadiness.DISABLED.value)
        health = self.provider.health_check(self.mock_data_dir)
        self.assertEqual(health["status"], "disabled")


class LiveProviderRolloutTest(unittest.TestCase):
    """Tests for LiveDataProvider rollout controls."""

    def setUp(self):
        self.provider = LiveDataProvider()

    @patch("data_source.get_config_value", return_value=True)
    def test_live_enabled_default(self, mock_cfg):
        mock_cfg.return_value = True
        # Live provider is not configured by default, but not disabled by rollout
        self.assertFalse(self.provider.is_available("/tmp"))
        self.assertEqual(self.provider.readiness(), ProviderReadiness.NOT_CONFIGURED.value)

    @patch("data_source.get_config_value", return_value=False)
    def test_live_disabled_by_rollout(self, mock_cfg):
        mock_cfg.return_value = False
        self.assertFalse(self.provider.is_available("/tmp"))
        self.assertEqual(self.provider.readiness(), ProviderReadiness.DISABLED.value)
        health = self.provider.health_check()
        self.assertEqual(health["status"], "disabled")


class AutoFailoverProviderRolloutTest(unittest.TestCase):
    """Tests for AutoFailoverProvider rollout controls."""

    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), "..", "mock_data"
        )
        self.local = LocalFileProvider()
        self.live = LiveDataProvider()
        self.provider = AutoFailoverProvider(self.live, self.local)

    @patch("data_source.get_config_value", return_value=True)
    def test_auto_enabled_default(self, mock_cfg):
        mock_cfg.side_effect = lambda key, default: True
        # Auto readiness depends on live/local availability
        # Live is not configured, local is available -> degraded
        self.assertTrue(self.provider.is_available(self.mock_data_dir))

    @patch("data_source.get_config_value", return_value=False)
    def test_auto_disabled_by_rollout(self, mock_cfg):
        mock_cfg.side_effect = lambda key, default: False
        self.assertFalse(self.provider.is_available(self.mock_data_dir))
        self.assertEqual(self.provider.readiness(self.mock_data_dir), ProviderReadiness.DISABLED.value)
        health = self.provider.health_check(self.mock_data_dir)
        self.assertEqual(health["status"], "disabled")
        status = self.provider.status(self.mock_data_dir)
        self.assertEqual(status["readiness"], ProviderReadiness.DISABLED.value)
        self.assertFalse(status["available"])


if __name__ == "__main__":
    unittest.main()
