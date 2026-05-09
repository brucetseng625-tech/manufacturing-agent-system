"""Approval workflow queue for guarded operations.

Tracks pending approval items when guardrails require approval but no token
is provided. Operators can view, approve, or reject items from the dashboard.

Design:
- In-memory queue with max history (oldest items pruned)
- Items created when guardrail returns approval_required error
- Each item has: id, operation, source_ip, requested_at, status, guardrail_reason
- Approving an item records an approval token that subsequent requests can use
- All state transitions logged to audit chain

Usage:
    from approval_queue import create_pending_item, list_pending, approve_item, reject_item

    # When guardrail denies due to missing approval token:
    item = create_pending_item(operation="policy:reload", source_ip="127.0.0.1", details={...})

    # List pending items
    items = list_pending()

    # Operator approves
    approve_item(item["id"], approved_by="operator")

    # Or rejects
    reject_item(item["id"], reason="Not needed")
"""

import time
import threading
import json

from audit_chain import append_audit_entry

# ─── Constants ───────────────────────────────────────────────────────────────

MAX_HISTORY = 100  # Max total items (pending + resolved) in memory

# ─── Module State ────────────────────────────────────────────────────────────

_lock = threading.Lock()
_counter = 0  # Monotonic counter for item IDs
_items = {}   # id -> item dict
_order = []   # list of ids in insertion order (for LRU pruning)


def _next_id():
    """Generate the next approval item ID."""
    global _counter
    _counter += 1
    return "approval-{}".format(_counter)


def _prune_if_needed():
    """Remove oldest resolved items if history exceeds max."""
    if len(_items) <= MAX_HISTORY:
        return

    # Remove oldest resolved items first
    removed = 0
    new_order = []
    for item_id in _order:
        item = _items.get(item_id)
        if item and item.get("status") in ("approved", "rejected", "expired") and removed < 20:
            del _items[item_id]
            removed += 1
        else:
            new_order.append(item_id)

    _order[:] = new_order


# ─── Queue Operations ───────────────────────────────────────────────────────

def create_pending_item(operation, source_ip=None, details=None, guardrail_config=None):
    """Create a new pending approval item.

    Called when a guardrail returns approval_required error (missing/invalid token).

    Args:
        operation: Guard label (e.g., "policy:reload", "provider:select")
        source_ip: Client IP address
        details: Optional dict with request details
        guardrail_config: The guardrail config that triggered the approval requirement

    Returns:
        dict with the created item.
    """
    with _lock:
        item_id = _next_id()
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        item = {
            "id": item_id,
            "operation": operation,
            "source_ip": source_ip or "unknown",
            "details": details or {},
            "guardrail_config": guardrail_config or {},
            "status": "pending",
            "created_at": now,
            "approved_at": None,
            "rejected_at": None,
            "approved_by": None,
            "rejection_reason": None,
        }

        _items[item_id] = item
        _order.append(item_id)
        _prune_if_needed()

    # Log to audit chain
    append_audit_entry(
        action="approval:created",
        operator="system",
        source_ip=source_ip or "unknown",
        details={
            "approval_id": item_id,
            "operation": operation,
            "details": details or {},
        },
        result="pending",
    )

    return dict(item)


def list_pending(status_filter=None, limit=50):
    """List approval queue items.

    Args:
        status_filter: Filter by status ("pending", "approved", "rejected", "expired", or None for all)
        limit: Max items to return

    Returns:
        list of item dicts, newest first.
    """
    with _lock:
        items = list(_items.values())

    # Sort newest first (highest counter last in insertion order)
    items.sort(key=lambda x: x["id"], reverse=True)

    if status_filter:
        items = [i for i in items if i.get("status") == status_filter]

    return items[:limit]


def get_item(item_id):
    """Get a single approval item by ID.

    Args:
        item_id: The approval ID (e.g., "approval-1")

    Returns:
        dict or None if not found.
    """
    with _lock:
        item = _items.get(item_id)
        if item is None:
            return None
        return dict(item)


def approve_item(item_id, approved_by=None, approval_token=None):
    """Approve a pending approval item.

    Args:
        item_id: The approval ID
        approved_by: Who approved it (e.g., "operator", "api")
        approval_token: Optional token to associate with this approval

    Returns:
        dict with updated item, or error dict if not found/invalid.
    """
    with _lock:
        item = _items.get(item_id)
        if item is None:
            return {"error": "approval_not_found", "id": item_id}

        if item["status"] != "pending":
            return {"error": "approval_already_resolved", "id": item_id, "status": item["status"]}

        item["status"] = "approved"
        item["approved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        item["approved_by"] = approved_by or "operator"
        if approval_token:
            item["approval_token"] = approval_token

    # Log to audit chain
    append_audit_entry(
        action="approval:approved",
        operator=approved_by or "operator",
        source_ip="127.0.0.1",
        details={
            "approval_id": item_id,
            "operation": item["operation"],
            "approved_by": approved_by or "operator",
        },
        result="success",
    )

    return dict(item)


def reject_item(item_id, reason=None, rejected_by=None):
    """Reject a pending approval item.

    Args:
        item_id: The approval ID
        reason: Optional rejection reason
        rejected_by: Who rejected it

    Returns:
        dict with updated item, or error dict if not found/invalid.
    """
    with _lock:
        item = _items.get(item_id)
        if item is None:
            return {"error": "approval_not_found", "id": item_id}

        if item["status"] != "pending":
            return {"error": "approval_already_resolved", "id": item_id, "status": item["status"]}

        item["status"] = "rejected"
        item["rejected_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        item["rejection_reason"] = reason or ""
        item["rejected_by"] = rejected_by or "operator"

    # Log to audit chain
    append_audit_entry(
        action="approval:rejected",
        operator=rejected_by or "operator",
        source_ip="127.0.0.1",
        details={
            "approval_id": item_id,
            "operation": item["operation"],
            "reason": reason or "",
        },
        result="rejected",
    )

    return dict(item)


def get_approval_stats():
    """Get summary statistics for the approval queue.

    Returns:
        dict with counts by status and recent activity.
    """
    with _lock:
        items = list(_items.values())

    by_status = {}
    for item in items:
        s = item.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1

    by_operation = {}
    for item in items:
        op = item.get("operation", "unknown")
        by_operation[op] = by_operation.get(op, 0) + 1

    return {
        "total_items": len(items),
        "by_status": by_status,
        "by_operation": by_operation,
        "pending_count": by_status.get("pending", 0),
    }


def reset_queue():
    """Clear all items from the queue.

    Used for testing or operator-initiated reset.
    """
    global _counter
    with _lock:
        _items.clear()
        _order.clear()
        _counter = 0

    append_audit_entry(
        action="approval:reset",
        operator="api",
        source_ip="127.0.0.1",
        details={"operation": "reset_queue"},
        result="success",
    )


def check_approved_token(operation):
    """Check if there's an approved token for a given operation.

    Used by guardrails to see if a pending item was already approved.

    Args:
        operation: Guard label string

    Returns:
        str or None: Approved token if found, None otherwise.
    """
    with _lock:
        for item in _items.values():
            if (item["operation"] == operation and
                    item["status"] == "approved" and
                    "approval_token" in item):
                return item["approval_token"]
    return None
