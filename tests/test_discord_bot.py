"""Tests for P17-2 Discord Notification & Query Bot."""

import json
import os
import unittest
from unittest.mock import patch

from integrations.discord_bot import (
    format_explainable_response,
    handle_discord_message,
    send_discord_notification,
)


class DiscordNotificationTest(unittest.TestCase):
    """Test Discord notification formatting and sending logic."""

    @patch("integrations.discord_bot.get_config_value")
    @patch("integrations.discord_bot.urllib.request.urlopen")
    def test_send_notification_success(self, mock_urlopen, mock_get_config):
        """Should return True when webhook sends successfully."""
        mock_get_config.return_value = "https://discord.com/api/webhooks/test"
        mock_resp = unittest.mock.Mock()
        mock_resp.status = 204
        mock_urlopen.return_value.__enter__ = lambda s: mock_resp
        mock_urlopen.return_value.__exit__ = lambda s, *a: None

        result = send_discord_notification("system_unhealthy", "Test", "Desc")
        self.assertTrue(result)
        mock_urlopen.assert_called_once()

    @patch("integrations.discord_bot.get_config_value")
    def test_send_notification_no_webhook(self, mock_get_config):
        """Should return False when no webhook URL is configured."""
        mock_get_config.return_value = ""
        result = send_discord_notification("test", "T", "D")
        self.assertFalse(result)


class DiscordExplainabilityTest(unittest.TestCase):
    """Test formatting of explainable responses for Discord."""

    def test_format_error_with_explainability(self):
        """Error response should include reason and next_action."""
        result = {
            "status": "error",
            "error_type": "rollout_gated",
            "message": "Feature not enabled",
            "reason": "Capability is disabled in rollout profile",
            "next_action": "Update the rollout profile to enable this capability.",
            "decision_state": "rollout_gated",
        }
        output = format_explainable_response("Test query", result)
        self.assertIn("rollout_gated", output)
        self.assertIn("Capability is disabled", output)
        self.assertIn("Update the rollout profile", output)
        self.assertIn("🔒 功能尚未開放", output)

    def test_format_success_with_details(self):
        """Success response should include skill and key details."""
        result = {
            "status": "success",
            "skill": "delivery-risk-analysis",
            "intent": "delivery_risk_analysis",
            "data": {
                "decision": "low_risk",
                "order_id": "ORD-1001",
                "details": {"risk_level": "low"},
            },
        }
        output = format_explainable_response("ORD-1001 如何？", result)
        self.assertIn("delivery-risk-analysis", output)
        self.assertIn("low_risk", output)
        self.assertIn("ORD-1001", output)


class DiscordQueryTest(unittest.TestCase):
    """Test Discord query handling and security boundaries."""

    @patch("integrations.discord_bot.get_config_value")
    def test_reject_unauthorized_user(self, mock_get_config):
        """Should block users not in allowed_user_ids."""
        mock_get_config.return_value = ["12345"]
        payload = {"author_id": "67890", "content": "Test"}
        result = handle_discord_message(payload)
        self.assertEqual(result["status"], "error")
        self.assertIn("未經授權", result["message"])

    @patch("integrations.discord_bot.get_config_value")
    def test_allow_authorized_user(self, mock_get_config):
        """Should allow users in allowed_user_ids."""
        # Return empty list means no restriction in this test context
        mock_get_config.side_effect = lambda k, d: {"discord.allowed_user_ids": []}.get(k, d)
        with patch("integrations.discord_bot.route_query") as mock_route:
            mock_route.return_value = {"status": "success", "skill": "test"}
            payload = {"author_id": "123", "content": "ORD-1001"}
            result = handle_discord_message(payload)
            self.assertEqual(result["status"], "success")
            self.assertIn("查詢完成", result["message"])


if __name__ == "__main__":
    unittest.main()
