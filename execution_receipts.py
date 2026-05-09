"""Execution receipts for automated operations.

Provides a unified, operator-facing record for all automated execution
outcomes — both approval-linked retries and auto-remediation runs.

Design:
- In-memory capped receipt log (oldest pruned when limit reached)
- Thread-safe for concurrent writes
- Immutable once recorded — receipts are append-only history
- Integrates with existing audit chain for full traceability

Sources:
- approval-retry: outcomes from POST /approvals/{id}/approve-and-retry
- auto-remediation: outcomes from auto-remediation hook evaluations

Usage:
    from execution_receipts import record_receipt, query_receipts, get_receipts_summary

    # Record after an approval retry
    record_receipt(source="approval-retry", operation="policy:reload",
                   status="success", approval_id="approval-3",
                   details={"status_code": 200})

    # Record after auto-remediation
    record_receipt(source="auto-remediation", operation="alerts:reset",
                   status="executed", trigger="circuit_breaker_open",
                   hook="reset_on_cb_open", details={"dry_run": False})

    # Query receipts
    receipts = query_receipts(source="auto-remediation", status="executed")
    summary = get_receipts_summary()
"""

import time
import threading
import uuid

from audit_chain import append_audit_entry

# ─── Constants ───────────────────────────────────────────────────────────────

MAX_RECEIPTS = 200  # Max receipts kept in memory

VALID_SOURCES = {"approval-retry", "auto-remediation"}
VALID_STATUSES = {
    "success", "failed", "skipped", "cooldown", "policy_denied",
    "executed", "dry_run", "error",
}

# ─── Module State ────────────────────────────────────────────────────────────

_lock = threading.Lock()
_receipts = []  # list of receipt dicts, insertion order


def _next_id():
    """Generate a unique receipt ID."""
    return "rcpt-{}".format(uuid.uuid4().hex[:8])


def _prune():
    """Remove oldest receipts if over limit."""
    global _receipts
    if len(_receipts) > MAX_RECEIPTS:
        _receipts = _receipts[-MAX_RECEIPTS:]


def record_receipt(source, operation, status, approval_id=None, trigger=None,
                   hook=None, duration_ms=None, details=None):
    """Record an execution receipt.

    Args:
        source: "approval-retry" or "auto-remediation"
        operation: The operation performed (e.g. "policy:reload", "alerts:reset")
        status: Execution result status string
        approval_id: Approval item ID (for approval-retry source)
        trigger: Alert trigger name (for auto-remediation source)
        hook: Hook name (for auto-remediation source)
        duration_ms: Execution duration in milliseconds (optional)
        details: Optional dict with additional context

    Returns:
        The recorded receipt dict.
    """
    receipt = {
        "receipt_id": _next_id(),
        "source": source,
        "operation": operation,
        "status": status,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    if approval_id is not None:
        receipt["approval_id"] = approval_id
    if trigger is not None:
        receipt["trigger"] = trigger
    if hook is not None:
        receipt["hook"] = hook
    if duration_ms is not None:
        receipt["duration_ms"] = duration_ms
    if details:
        receipt["details"] = details

    with _lock:
        _receipts.append(receipt)
        _prune()

    # Also log to audit chain for traceability
    audit_details = {
        "receipt_id": receipt["receipt_id"],
        "source": source,
        "operation": operation,
        "status": status,
    }
    if approval_id:
        audit_details["approval_id"] = approval_id
    if trigger:
        audit_details["trigger"] = trigger
    if hook:
        audit_details["hook"] = hook
    append_audit_entry(
        action="execution_receipt",
        operator="system" if source == "auto-remediation" else "operator",
        source_ip="127.0.0.1",
        details=audit_details,
        result=status,
    )

    return receipt


def query_receipts(source=None, status=None, operation=None, limit=20,
                   offset=0):
    """Query execution receipts with optional filters.

    Args:
        source: Filter by source ("approval-retry" or "auto-remediation")
        status: Filter by status string
        operation: Filter by operation name
        limit: Max receipts to return (default 20)
        offset: Skip first N receipts (default 0)

    Returns:
        dict with:
            receipts: list of matching receipts, newest first
            total: total matching count
    """
    with _lock:
        filtered = list(_receipts)

    if source:
        filtered = [r for r in filtered if r.get("source") == source]
    if status:
        filtered = [r for r in filtered if r.get("status") == status]
    if operation:
        filtered = [r for r in filtered if r.get("operation") == operation]

    total = len(filtered)
    # Newest first
    filtered.reverse()
    page = filtered[offset: offset + limit]

    return {"receipts": page, "total": total}


def get_receipts_summary():
    """Get high-level summary of all execution receipts.

    Returns:
        dict with:
            total: total receipt count
            by_source: count per source
            by_status: count per status
            by_operation: count per operation
    """
    with _lock:
        all_receipts = list(_receipts)

    by_source = {}
    by_status = {}
    by_operation = {}

    for r in all_receipts:
        s = r.get("source", "unknown")
        st = r.get("status", "unknown")
        op = r.get("operation", "unknown")
        by_source[s] = by_source.get(s, 0) + 1
        by_status[st] = by_status.get(st, 0) + 1
        by_operation[op] = by_operation.get(op, 0) + 1

    return {
        "total": len(all_receipts),
        "by_source": by_source,
        "by_status": by_status,
        "by_operation": by_operation,
    }


def reset_receipts():
    """Clear all receipts. Used for testing or operator reset."""
    with _lock:
        _receipts.clear()

    append_audit_entry(
        action="execution_receipt",
        operator="api",
        source_ip="127.0.0.1",
        details={"operation": "reset_receipts"},
        result="success",
    )
