
import os
import unittest
from unittest.mock import patch, MagicMock
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

    @patch("integrations.asana_client.requests.post")
    def test_post_comment_success(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status = MagicMock()
        
        with patch.dict(os.environ, {"ASANA_ACCESS_TOKEN": "fake-token"}):
            result = post_comment("123456", "Test comment")
            self.assertTrue(result)
            mock_post.assert_called_once()

    @patch("integrations.asana_client.requests.post")
    def test_post_comment_network_error(self, mock_post):
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError("Network error")
        
        with patch.dict(os.environ, {"ASANA_ACCESS_TOKEN": "fake-token"}):
            result = post_comment("123456", "Test comment")
            self.assertFalse(result)

    def test_format_success_report_delivery(self):
        response = {
            "intent": "delivery_risk_analysis",
            "data": {
                "order_id": "ORD-1001",
                "decision": "can_ship_on_time",
                "confidence": "High",
                "blockers": []
            }
        }
        comment = format_success_report(response)
        self.assertIn("delivery_risk_analysis", comment)
        self.assertIn("ORD-1001", comment)
        self.assertIn("can_ship_on_time", comment)

    def test_format_error_report_validation(self):
        response = {
            "type": "validation_failed",
            "details": ["Missing required field 'order_id'", "Invalid date"]
        }
        comment = format_error_report(response)
        self.assertIn("validation_failed", comment)
        self.assertIn("Missing required field", comment)
