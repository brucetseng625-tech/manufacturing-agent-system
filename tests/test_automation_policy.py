"""Tests for automation_policy — config-driven automation policy controls."""

import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from automation_policy import (
    check_automation_allowed,
    is_automation_enabled,
    get_allowed_actions,
    get_denied_actions,
    get_automation_policy_status,
)
from config import set_config


class AutomationPolicyDisabledTest(unittest.TestCase):
    """Tests when automation policy is disabled (default)."""

    def setUp(self):
        set_config({})

    def test_disabled_by_default(self):
        """Should be disabled by default."""
        self.assertFalse(is_automation_enabled())

    def test_allows_all_when_disabled(self):
        """Should allow any action when policy is disabled."""
        allowed, reason = check_automation_allowed("alerts:reset")
        self.assertTrue(allowed)
        self.assertIsNone(reason)

    def test_empty_allowed_when_disabled(self):
        """Should return None when not configured."""
        self.assertIsNone(get_allowed_actions())

    def test_empty_denied_when_disabled(self):
        """Should return empty list when not configured."""
        self.assertEqual(get_denied_actions(), [])


class AutomationPolicyEnabledTest(unittest.TestCase):
    """Tests when automation policy is enabled."""

    def setUp(self):
        set_config({})

    def test_enabled_via_config(self):
        """Should be enabled when config says so."""
        set_config({"automation_policy": {"enabled": True}})
        self.assertTrue(is_automation_enabled())

    def test_allowed_action_when_in_list(self):
        """Should allow action if in allowed_actions list."""
        set_config({
            "automation_policy": {
                "enabled": True,
                "allowed_actions": ["alerts:reset", "config:reload"],
            }
        })
        allowed, reason = check_automation_allowed("alerts:reset")
        self.assertTrue(allowed)
        self.assertIsNone(reason)

    def test_denied_action_when_not_in_list(self):
        """Should deny action if not in allowed_actions list."""
        set_config({
            "automation_policy": {
                "enabled": True,
                "allowed_actions": ["alerts:reset"],
            }
        })
        allowed, reason = check_automation_allowed("config:reload")
        self.assertFalse(allowed)
        self.assertIn("not in the allowed", reason)

    def test_explicit_denied_action(self):
        """Should deny action if in denied_actions list."""
        set_config({
            "automation_policy": {
                "enabled": True,
                "denied_actions": ["provider:switch"],
            }
        })
        allowed, reason = check_automation_allowed("provider:switch")
        self.assertFalse(allowed)
        self.assertIn("denied", reason)

    def test_denied_overrides_allowed(self):
        """Denied list should take precedence over allowed list."""
        set_config({
            "automation_policy": {
                "enabled": True,
                "allowed_actions": ["alerts:reset", "config:reload"],
                "denied_actions": ["config:reload"],
            }
        })
        # config:reload is in both — denied should win
        allowed, reason = check_automation_allowed("config:reload")
        self.assertFalse(allowed)

    def test_approval_retry_action(self):
        """Should handle approval:retry action type."""
        set_config({
            "automation_policy": {
                "enabled": True,
                "allowed_actions": ["approval:retry"],
            }
        })
        allowed, reason = check_automation_allowed("approval:retry")
        self.assertTrue(allowed)

    def test_empty_allowed_list_denies_all(self):
        """When enabled but allowed_actions is empty, deny everything."""
        set_config({
            "automation_policy": {
                "enabled": True,
                "allowed_actions": [],
            }
        })
        allowed, reason = check_automation_allowed("alerts:reset")
        self.assertFalse(allowed)


class AutomationPolicyStatusTest(unittest.TestCase):
    """Tests for policy status inspection."""

    def setUp(self):
        set_config({})

    def test_status_returns_enabled_flag(self):
        """Status should include enabled flag."""
        set_config({"automation_policy": {"enabled": True}})
        status = get_automation_policy_status()
        self.assertTrue(status["enabled"])

    def test_status_returns_allowed_actions(self):
        """Status should return allowed actions."""
        set_config({
            "automation_policy": {
                "enabled": True,
                "allowed_actions": ["alerts:reset", "config:reload"],
                "denied_actions": ["provider:switch"],
            }
        })
        status = get_automation_policy_status()
        self.assertEqual(status["allowed_actions"], ["alerts:reset", "config:reload"])
        self.assertEqual(status["denied_actions"], ["provider:switch"])


if __name__ == "__main__":
    unittest.main()
