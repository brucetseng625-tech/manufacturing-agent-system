"""Tests for P17-2 Discord Notification & Query Bot."""

import json
import os
import unittest
from unittest.mock import patch

from integrations.discord_bot import (
    format_explainable_response,
    format_approval_list,
    format_approval_item_detail,
    format_approval_action_result,
    handle_discord_approval_command,
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


class DiscordApprovalFormattingTest(unittest.TestCase):
    """Test P17-3 approval formatting functions for Discord."""

    def test_format_approval_list_empty(self):
        """Should show 'no pending items' when list is empty."""
        output = format_approval_list([])
        self.assertIn("沒有待審批項目", output)

    def test_format_approval_list_with_items(self):
        """Should format items with operation, id, and status."""
        items = [
            {"id": "approval-1", "operation": "config:reload", "status": "pending", "created_at": "2026-05-14T10:00:00Z", "details": {"endpoint": "/config/reload"}, "risk_level": "medium"},
        ]
        output = format_approval_list(items)
        self.assertIn("approval-1", output)
        self.assertIn("config:reload", output)
        self.assertIn("待審批項目", output)

    def test_format_approval_item_detail_not_found(self):
        """Should show error message for None item."""
        output = format_approval_item_detail(None)
        self.assertIn("找不到", output)

    def test_format_approval_item_detail_with_data(self):
        """Should show full detail for an approval item."""
        item = {
            "id": "approval-5",
            "operation": "policy:reload",
            "status": "pending",
            "created_at": "2026-05-14T12:00:00Z",
            "source_ip": "127.0.0.1",
            "details": {"endpoint": "/policy/reload", "guardrail": "policy:reload"},
            "original_request": {"method": "POST", "path": "/policy/reload", "body": {"config_path": "config.json"}},
        }
        output = format_approval_item_detail(item)
        self.assertIn("approval-5", output)
        self.assertIn("policy:reload", output)
        self.assertIn("原始請求", output)
        self.assertIn("POST /policy/reload", output)
        self.assertIn("操作提示", output)

    def test_format_approval_action_result_approved(self):
        """Should format successful approval result."""
        result = {"id": "approval-3", "operation": "config:reload", "status": "approved"}
        output = format_approval_action_result("approved", result)
        self.assertIn("已審批", output)
        self.assertIn("approval-3", output)
        self.assertIn("approve-and-retry", output)

    def test_format_approval_action_result_rejected_with_reason(self):
        """Should format rejection result with reason."""
        result = {"id": "approval-4", "operation": "provider:select", "status": "rejected", "rejection_reason": "Not needed now"}
        output = format_approval_action_result("rejected", result)
        self.assertIn("已拒絕", output)
        self.assertIn("Not needed now", output)

    def test_format_approval_action_result_not_found(self):
        """Should format error for missing approval."""
        result = {"error": "approval_not_found", "id": "approval-999"}
        output = format_approval_action_result("approved", result)
        self.assertIn("找不到", output)
        self.assertIn("approval-999", output)

    def test_format_approval_action_result_already_resolved(self):
        """Should warn when item already resolved."""
        result = {"error": "approval_already_resolved", "id": "approval-1", "status": "approved"}
        output = format_approval_action_result("approved", result)
        self.assertIn("已處理", output)
        self.assertIn("已審批", output)


class DiscordApprovalCommandTest(unittest.TestCase):
    """Test P17-3 Discord approval command routing."""

    @patch("integrations.discord_bot.get_config_value")
    def test_reject_unauthorized_approval(self, mock_get_config):
        """Should block unauthorized users from approval commands."""
        mock_get_config.return_value = ["12345"]
        result = handle_discord_approval_command({"author_id": "67890", "content": "approval list"})
        self.assertEqual(result["status"], "error")
        self.assertIn("未經授權", result["message"])

    @patch("integrations.discord_bot.get_config_value")
    @patch("integrations.discord_bot.list_pending")
    def test_approval_list_command(self, mock_list, mock_get_config):
        """Should return formatted list of pending approvals."""
        mock_get_config.return_value = []
        mock_list.return_value = [{"id": "approval-1", "operation": "config:reload", "status": "pending", "created_at": "2026-05-14T10:00:00Z", "details": {"endpoint": "/config/reload"}}]
        result = handle_discord_approval_command({"author_id": "123", "content": "approval list"})
        self.assertEqual(result["status"], "success")
        self.assertIn("approval-1", result["message"])
        mock_list.assert_called_once()

    @patch("integrations.discord_bot.get_config_value")
    @patch("integrations.discord_bot.list_pending")
    def test_approval_list_with_filter(self, mock_list, mock_get_config):
        """Should pass status filter to list_pending."""
        mock_get_config.return_value = []
        mock_list.return_value = []
        result = handle_discord_approval_command({"author_id": "123", "content": "approval list approved"})
        self.assertEqual(result["status"], "success")
        mock_list.assert_called_once_with(status_filter="approved")

    @patch("integrations.discord_bot.get_config_value")
    @patch("integrations.discord_bot.get_item")
    def test_approval_detail_command(self, mock_get, mock_get_config):
        """Should return detail for a specific approval item."""
        mock_get_config.return_value = []
        mock_get.return_value = {"id": "approval-2", "operation": "policy:reload", "status": "pending", "created_at": "2026-05-14T10:00:00Z", "source_ip": "127.0.0.1", "details": {}, "original_request": None}
        result = handle_discord_approval_command({"author_id": "123", "content": "approval approval-2"})
        self.assertEqual(result["status"], "success")
        self.assertIn("approval-2", result["message"])
        mock_get.assert_called_once_with("approval-2")

    @patch("integrations.discord_bot.get_config_value")
    @patch("integrations.discord_bot.approve_item")
    def test_approve_command(self, mock_approve, mock_get_config):
        """Should approve an item and return confirmation."""
        mock_get_config.return_value = []
        mock_approve.return_value = {"id": "approval-3", "operation": "config:reload", "status": "approved"}
        result = handle_discord_approval_command({"author_id": "123", "content": "approve approval-3"})
        self.assertEqual(result["status"], "success")
        self.assertIn("已審批", result["message"])
        mock_approve.assert_called_once()

    @patch("integrations.discord_bot.get_config_value")
    @patch("integrations.discord_bot.reject_item")
    def test_reject_command_with_reason(self, mock_reject, mock_get_config):
        """Should reject an item with a reason."""
        mock_get_config.return_value = []
        mock_reject.return_value = {"id": "approval-4", "operation": "provider:select", "status": "rejected", "rejection_reason": "Not needed"}
        result = handle_discord_approval_command({"author_id": "123", "content": "reject approval-4 Not needed"})
        self.assertEqual(result["status"], "success")
        self.assertIn("已拒絕", result["message"])
        mock_reject.assert_called_once()

    @patch("integrations.discord_bot.get_config_value")
    def test_unknown_approval_command(self, mock_get_config):
        """Should show help for unrecognized commands."""
        mock_get_config.return_value = []
        result = handle_discord_approval_command({"author_id": "123", "content": "approval foo bar baz"})
        self.assertIn("未知的審批指令", result["message"])
        self.assertIn("approval list", result["message"])
