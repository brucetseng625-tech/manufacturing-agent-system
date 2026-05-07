
import os
import unittest
from unittest.mock import patch, MagicMock
import urllib.error
from integrations.asana_client import (
    get_token, 
    post_comment, 
    format_success_report, 
    format_error_report
)

class AsanaClientTest(unittest.TestCase):
    def test_get_token_success(self):
        with patch.dict(os.environ, {"ASANA_ACCESS_TOKEN": "test-token-123"}):
            token = get_token()
            self.assertEqual(token, "test-token-123")

    def test_get_token_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                get_token()

    @patch("integrations.asana_client.urllib.request.urlopen")
    def test_post_comment_success(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value = MagicMock()

        with patch.dict(os.environ, {"ASANA_ACCESS_TOKEN": "fake-token"}):
            result = post_comment("123456", "Test comment")
            self.assertTrue(result)
            mock_urlopen.assert_called_once()

    @patch("integrations.asana_client.urllib.request.urlopen")
    def test_post_comment_network_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Network error")

        with patch.dict(os.environ, {"ASANA_ACCESS_TOKEN": "fake-token"}):
            result = post_comment("123456", "Test comment")
            self.assertFalse(result)

    def test_post_comment_missing_token_returns_false(self):
        with patch.dict(os.environ, {}, clear=True):
            result = post_comment("123456", "Test comment")
            self.assertFalse(result)

    def test_format_success_report_delivery(self):
        response = {
            "intent": "delivery_risk_analysis",
            "data": {
                "order_id": "ORD-1001",
                "decision": "can_ship_on_time",
                "confidence": "High",
                "blockers": ["No critical blockers found in current mock data."]
            }
        }
        comment = format_success_report(response)
        self.assertIn("delivery_risk_analysis", comment)
        self.assertIn("ORD-1001", comment)
        self.assertIn("can_ship_on_time", comment)
        self.assertIn("Status: Success", comment)
        self.assertIn("Blockers: 0", comment)

    def test_format_success_report_delivery_lists_actionable_blockers(self):
        response = {
            "intent": "delivery_risk_analysis",
            "data": {
                "order_id": "ORD-1001",
                "decision": "at_risk",
                "confidence": "Medium",
                "blockers": ["Material shortage: Steel"]
            }
        }
        comment = format_success_report(response)
        self.assertIn("Blockers: 1", comment)
        self.assertIn("Material shortage: Steel", comment)

    def test_format_error_report_validation(self):
        response = {
            "type": "validation_failed",
            "details": ["Missing required field 'order_id'", "Invalid date"]
        }
        comment = format_error_report(response)
        self.assertIn("validation_failed", comment)
        self.assertIn("Missing required field", comment)
        self.assertIn("Status: Failed", comment)
