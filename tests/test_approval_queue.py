"""Tests for approval_queue — approval workflow queue management."""

import unittest
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from approval_queue import (
    create_pending_item,
    list_pending,
    get_item,
    approve_item,
    reject_item,
    get_approval_stats,
    reset_queue,
    check_approved_token,
    serialize_item_for_api,
    _items,
    _order,
    _counter,
)


class ApprovalQueueBasicTest(unittest.TestCase):
    """Tests for basic queue operations."""

    def setUp(self):
        reset_queue()

    def test_create_item(self):
        """Creating an item should return it with pending status."""
        item = create_pending_item("policy:reload", source_ip="10.0.0.1")
        self.assertEqual(item["operation"], "policy:reload")
        self.assertEqual(item["source_ip"], "10.0.0.1")
        self.assertEqual(item["status"], "pending")
        self.assertIsNotNone(item["id"])
        self.assertTrue(item["id"].startswith("approval-"))

    def test_create_with_details(self):
        """Details should be stored in the item."""
        item = create_pending_item("provider:select", source_ip="127.0.0.1",
                                   details={"mode": "auto"},
                                   guardrail_config={"require_approval": True})
        self.assertEqual(item["details"]["mode"], "auto")
        self.assertTrue(item["guardrail_config"]["require_approval"])

    def test_list_pending_returns_items(self):
        """Should return created items."""
        create_pending_item("policy:reload")
        create_pending_item("config:reload")
        items = list_pending()
        self.assertEqual(len(items), 2)

    def test_list_pending_newest_first(self):
        """Items should be returned newest first."""
        item1 = create_pending_item("first")
        item2 = create_pending_item("second")
        item3 = create_pending_item("third")
        items = list_pending()
        self.assertEqual(items[0]["id"], item3["id"])
        self.assertEqual(items[1]["id"], item2["id"])
        self.assertEqual(items[2]["id"], item1["id"])

    def test_list_pending_with_status_filter(self):
        """Should filter by status."""
        item1 = create_pending_item("first")
        item2 = create_pending_item("second")
        approve_item(item2["id"])
        items = list_pending(status_filter="pending")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], item1["id"])

    def test_list_pending_with_limit(self):
        """Should respect limit."""
        for i in range(10):
            create_pending_item(f"item-{i}")
        items = list_pending(limit=3)
        self.assertEqual(len(items), 3)

    def test_get_item(self):
        """Should retrieve item by ID."""
        item = create_pending_item("test")
        retrieved = get_item(item["id"])
        self.assertEqual(retrieved["id"], item["id"])
        self.assertEqual(retrieved["operation"], "test")

    def test_get_item_not_found(self):
        """Should return None for non-existent item."""
        self.assertIsNone(get_item("approval-999"))


class ApprovalQueueApprovalTest(unittest.TestCase):
    """Tests for approve/reject operations."""

    def setUp(self):
        reset_queue()

    def test_approve_item(self):
        """Should change status to approved."""
        item = create_pending_item("policy:reload")
        result = approve_item(item["id"], approved_by="operator")
        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["approved_by"], "operator")
        self.assertIsNotNone(result["approved_at"])

    def test_approve_with_token(self):
        """Should store approval token."""
        item = create_pending_item("provider:select")
        result = approve_item(item["id"], approval_token="secret-123")
        self.assertEqual(result["approval_token"], "secret-123")

    def test_approve_not_found(self):
        """Should return error for non-existent item."""
        result = approve_item("approval-999")
        self.assertEqual(result["error"], "approval_not_found")

    def test_approve_already_resolved(self):
        """Should return error for already approved item."""
        item = create_pending_item("test")
        approve_item(item["id"])
        result = approve_item(item["id"])
        self.assertEqual(result["error"], "approval_already_resolved")

    def test_reject_item(self):
        """Should change status to rejected."""
        item = create_pending_item("policy:reload")
        result = reject_item(item["id"], reason="Not needed", rejected_by="admin")
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["rejection_reason"], "Not needed")
        self.assertEqual(result["rejected_by"], "admin")

    def test_reject_not_found(self):
        """Should return error for non-existent item."""
        result = reject_item("approval-999")
        self.assertEqual(result["error"], "approval_not_found")

    def test_reject_already_resolved(self):
        """Should return error for already rejected item."""
        item = create_pending_item("test")
        reject_item(item["id"])
        result = reject_item(item["id"])
        self.assertEqual(result["error"], "approval_already_resolved")


class ApprovalQueueStatsTest(unittest.TestCase):
    """Tests for statistics."""

    def setUp(self):
        reset_queue()

    def test_stats_counts(self):
        """Should count items by status."""
        item1 = create_pending_item("policy:reload")
        item2 = create_pending_item("config:reload")
        approve_item(item1["id"])
        reject_item(item2["id"])

        stats = get_approval_stats()
        self.assertEqual(stats["total_items"], 2)
        self.assertEqual(stats["by_status"]["approved"], 1)
        self.assertEqual(stats["by_status"]["rejected"], 1)
        self.assertEqual(stats["pending_count"], 0)

    def test_stats_by_operation(self):
        """Should count items by operation."""
        create_pending_item("policy:reload")
        create_pending_item("policy:reload")
        create_pending_item("config:reload")

        stats = get_approval_stats()
        self.assertEqual(stats["by_operation"]["policy:reload"], 2)
        self.assertEqual(stats["by_operation"]["config:reload"], 1)

    def test_stats_empty(self):
        """Should return zero counts for empty queue."""
        stats = get_approval_stats()
        self.assertEqual(stats["total_items"], 0)
        self.assertEqual(stats["pending_count"], 0)


class ApprovalQueueResetTest(unittest.TestCase):
    """Tests for queue reset."""

    def setUp(self):
        reset_queue()

    def test_reset_clears_items(self):
        """Reset should clear all items."""
        create_pending_item("test1")
        create_pending_item("test2")
        self.assertEqual(len(list_pending()), 2)

        reset_queue()
        self.assertEqual(len(list_pending()), 0)

    def test_reset_clears_order(self):
        """Reset should clear insertion order."""
        create_pending_item("test")
        self.assertEqual(len(_order), 1)

        reset_queue()
        self.assertEqual(len(_order), 0)


class ApprovalQueueTokenTest(unittest.TestCase):
    """Tests for approved token lookup."""

    def setUp(self):
        reset_queue()

    def test_check_approved_token_returns_token(self):
        """Should return token for approved item."""
        item = create_pending_item("provider:select")
        approve_item(item["id"], approval_token="token-abc")
        token = check_approved_token("provider:select")
        self.assertEqual(token, "token-abc")

    def test_check_approved_token_no_approval(self):
        """Should return None if no approved item."""
        create_pending_item("provider:select")
        token = check_approved_token("provider:select")
        self.assertIsNone(token)

    def test_check_approved_token_rejected(self):
        """Should return None for rejected item."""
        item = create_pending_item("provider:select")
        reject_item(item["id"])
        token = check_approved_token("provider:select")
        self.assertIsNone(token)


class ApprovalQueueOriginalRequestTest(unittest.TestCase):
    """Tests for original_request storage and retrieval."""

    def setUp(self):
        reset_queue()

    def test_create_with_original_request(self):
        """Should store original request details."""
        orig = {"method": "POST", "path": "/policy/reload", "body": {"config_path": "/etc/p.json"}}
        item = create_pending_item("policy:reload", original_request=orig)
        self.assertEqual(item["original_request"], orig)

    def test_original_request_in_approved_item(self):
        """Original request should persist after approval."""
        orig = {"method": "POST", "path": "/config/reload", "body": None}
        item = create_pending_item("config:reload", original_request=orig)
        approved = approve_item(item["id"])
        self.assertEqual(approved["original_request"], orig)

    def test_retry_result_field_exists(self):
        """Item should have retry_result field initialized to None."""
        item = create_pending_item("test")
        self.assertIsNone(item["retry_result"])

    def test_serialize_item_for_api_adds_request_preview(self):
        """API serialization should include a replay preview summary."""
        orig = {"method": "POST", "path": "/provider/select", "body": {"mode": "auto"}}
        item = create_pending_item("provider:select", original_request=orig)
        serialized = serialize_item_for_api(item)
        self.assertEqual(serialized["request_preview"]["method"], "POST")
        self.assertEqual(serialized["request_preview"]["path"], "/provider/select")
        self.assertEqual(serialized["request_preview"]["body_summary"], "mode=auto")
        self.assertEqual(serialized["risk_level"], "medium")

    def test_serialize_item_for_api_redacts_sensitive_body_values(self):
        """Preview body should redact token-like fields."""
        orig = {
            "method": "POST",
            "path": "/config/reload",
            "body": {"config_path": "/tmp/config.json", "approval_token": "secret-123"},
        }
        item = create_pending_item("config:reload", original_request=orig)
        serialized = serialize_item_for_api(item)
        self.assertEqual(serialized["request_preview"]["body"]["approval_token"], "***REDACTED***")
        self.assertNotIn("secret-123", serialized["request_preview"]["body_summary"])

    def test_serialize_item_for_api_hides_stored_approval_token(self):
        """Serialized items should not leak stored approval tokens."""
        item = create_pending_item("provider:select")
        approved = approve_item(item["id"], approval_token="secret-123")
        serialized = serialize_item_for_api(approved)
        self.assertNotIn("approval_token", serialized)


if __name__ == "__main__":
    unittest.main()
