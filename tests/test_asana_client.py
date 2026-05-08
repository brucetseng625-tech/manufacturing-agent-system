
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
                "customer": "Test Customer",
                "decision": "can_ship_on_time",
                "confidence": "High",
                "due_date": "2026-05-20",
                "blockers": ["No critical blockers found in current mock data."],
                "owner": "Production Team",
                "recommendation": "Proceed with normal production.",
                "trace": ["loaded orders", "evaluated delivery risk"],
            }
        }
        comment = format_success_report(response)
        self.assertIn("delivery_risk_analysis", comment)
        self.assertIn("ORD-1001", comment)
        self.assertIn("can_ship_on_time", comment)
        self.assertIn("Status: Success", comment)
        self.assertIn("Owner: Production Team", comment)
        self.assertIn("ETA: 2026-05-20", comment)
        self.assertIn("Blockers: None", comment)
        self.assertIn("Next Action: Proceed with normal production.", comment)
        self.assertIn("Escalation: None", comment)

    def test_format_success_report_delivery_lists_actionable_blockers(self):
        response = {
            "intent": "delivery_risk_analysis",
            "data": {
                "order_id": "ORD-1001",
                "customer": "Test Customer",
                "decision": "at_risk",
                "confidence": "Medium",
                "due_date": "2026-05-20",
                "blockers": ["Material shortage: Steel"],
                "owner": "Production Team",
                "recommendation": "Escalate to Ops Manager.",
                "trace": ["loaded orders", "evaluated delivery risk"],
            }
        }
        comment = format_success_report(response)
        self.assertIn("Blockers:", comment)
        self.assertIn("Material shortage: Steel", comment)
        self.assertIn("Next Action: Escalate to Ops Manager.", comment)

    def test_format_success_report_quote_summary(self):
        response = {
            "intent": "quote_comparison_summary",
            "data": {
                "material": "Steel",
                "recommended_supplier": "Supplier A",
                "decision": "Recommended: Supplier A for Steel",
                "confidence": "high",
                "price_spread": 15.0,
                "trace": ["loaded 3 quotes for Steel"],
            },
        }

        comment = format_success_report(response)

        self.assertIn("quote_comparison_summary", comment)
        self.assertIn("Materials Compared: 1", comment)
        self.assertIn("Steel", comment)
        self.assertIn("Supplier A", comment)
        self.assertIn("Price Spread: 15.0", comment)

    def test_format_success_report_sales_response(self):
        response = {
            "intent": "sales_response_draft",
            "data": {
                "order_id": "ORD-1001",
                "customer": "Test Customer",
                "shipment_status": "recovery_in_progress",
                "decision": "cannot_ship_on_time",
                "confidence": "High",
                "key_message": "Current production constraints may affect the committed delivery date.",
                "due_date": "2026-05-20",
                "owner": "Sales Team",
                "risk_summary": ["Material shortage: Steel"],
                "internal_guidance": "Draft customer delay notification.",
                "trace": ["loaded orders", "generated sales response draft"],
            },
        }

        comment = format_success_report(response)

        self.assertIn("sales_response_draft", comment)
        self.assertIn("recovery_in_progress", comment)
        self.assertIn("Blockers:", comment)
        self.assertIn("Material shortage: Steel", comment)
        self.assertIn("Next Action: Draft customer delay notification.", comment)
        self.assertIn("Owner: Sales Team", comment)
        self.assertIn("generated sales response draft", comment)

    def test_format_error_report_validation(self):
        response = {
            "type": "validation_failed",
            "details": ["Missing required field 'order_id'", "Invalid date"]
        }
        comment = format_error_report(response)
        self.assertIn("validation_failed", comment)
        self.assertIn("Missing required field", comment)
        self.assertIn("Status: Failed", comment)
