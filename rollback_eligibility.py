"""Rollback eligibility analysis for audit trail entries.

Read-only visibility layer that determines which audited operations
can potentially be rolled back, which cannot, and why.

Design principles:
- Read-only: no mutation, analysis only
- Config-driven: rollback rules defined by action type
- Deterministic: same input always produces same eligibility result
- Context-aware: links related audit entries, incidents, and approvals

Usage:
    from rollback_eligibility import analyze_entry, query_rollback_eligibility

    # Analyze a single audit entry
    result = analyze_entry(entry)

    # Query all entries with eligibility analysis
    result = query_rollback_eligibility(limit=50)
"""

import sys
import os
import threading

# Allow importing from project root when running as standalone
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from audit_chain import query_audit_log, get_audit_summary

# ─── Constants ───────────────────────────────────────────────────────────────

# Rollback eligibility rules per action type.
# Each entry defines:
#   eligible: bool — whether this action type can be rolled back
#   reason: str — human-readable explanation
#   category: str — grouping for UI/summary purposes
#   requires_context: bool — whether eligibility depends on details
#   related_action: str — if eligible, what action would perform rollback

_ROLLBACK_RULES = {
    # Guarded operations (state changes)
    "config:reload": {
        "eligible": False,
        "reason": "Configuration reload replaces in-memory state; no previous snapshot preserved",
        "category": "guarded_operation",
        "requires_context": False,
        "related_action": None,
    },
    "policy:reload": {
        "eligible": False,
        "reason": "Policy reload replaces in-memory rules; no previous version retained",
        "category": "guarded_operation",
        "requires_context": False,
        "related_action": None,
    },
    "provider:select": {
        "eligible": True,
        "reason": "Provider selection can be reversed by selecting the previous provider",
        "category": "guarded_operation",
        "requires_context": True,
        "related_action": "provider:select",
    },
    "alerts:reset": {
        "eligible": False,
        "reason": "Alert reset clears firing state; alerts will re-fire if conditions persist",
        "category": "guarded_operation",
        "requires_context": False,
        "related_action": None,
    },

    # Approval lifecycle events
    "approval:created": {
        "eligible": False,
        "reason": "Approval request was created but not yet executed; no state to rollback",
        "category": "approval_lifecycle",
        "requires_context": False,
        "related_action": None,
    },
    "approval:approved": {
        "eligible": True,
        "reason": "Approved operation was executed; rollback depends on the underlying operation type",
        "category": "approval_lifecycle",
        "requires_context": True,
        "related_action": None,  # determined by operation in details
    },
    "approval:rejected": {
        "eligible": False,
        "reason": "Operation was rejected and never executed; nothing to rollback",
        "category": "approval_lifecycle",
        "requires_context": False,
        "related_action": None,
    },
    "approval:reset": {
        "eligible": False,
        "reason": "Approval queue was cleared; this is an administrative action with no operational impact",
        "category": "approval_lifecycle",
        "requires_context": False,
        "related_action": None,
    },

    # Automation events
    "auto_remediation": {
        "eligible": False,
        "reason": "Auto-remediation actions are read-only or state resets; no persistent changes to revert",
        "category": "automation",
        "requires_context": True,
        "related_action": None,
    },
    "automation:policy_denied": {
        "eligible": False,
        "reason": "Operation was denied by automation policy; never executed",
        "category": "automation",
        "requires_context": False,
        "related_action": None,
    },
}

# Default rule for unknown action types
_DEFAULT_RULE = {
    "eligible": False,
    "reason": "Unknown action type; rollback eligibility cannot be determined",
    "category": "unknown",
    "requires_context": False,
    "related_action": None,
}

_MAX_ENTRIES = 200


# ─── Core Analysis ──────────────────────────────────────────────────────────

def analyze_entry(entry):
    """Analyze a single audit entry for rollback eligibility.

    Args:
        entry: dict from audit log with action, details, result, timestamp.

    Returns:
        dict with:
            action: original action string
            timestamp: from audit entry
            result: from audit entry
            eligible: bool
            reason: str explanation
            category: str grouping
            operator: from audit entry
            details_summary: condensed detail info
            rollback_action: str or None — what action would perform rollback
    """
    action = entry.get("action", "unknown")
    details = entry.get("details", {})
    result = entry.get("result", "unknown")

    rule = _ROLLBACK_RULES.get(action, _DEFAULT_RULE)
    eligible = rule["eligible"]
    reason = rule["reason"]
    category = rule["category"]
    rollback_action = rule["related_action"]

    # Action-specific overrides based on details
    if action == "approval:approved":
        op = details.get("operation", "")
        if op in _ROLLBACK_RULES:
            op_rule = _ROLLBACK_RULES[op]
            eligible = op_rule["eligible"]
            reason = f"Approved operation '{op}': {op_rule['reason']}"
            rollback_action = op_rule["related_action"]

    elif action == "auto_remediation":
        inner_action = details.get("action", details.get("operation", ""))
        dry_run = details.get("dry_run", False)
        if dry_run:
            eligible = False
            reason = "Auto-remediation ran in dry-run mode; no side effects occurred"
        elif inner_action in ("alerts:reset",):
            eligible = False
            reason = f"Auto-remediation performed '{inner_action}'; state reset cannot be undone"

    # Already-executed actions that failed are never rollbackable
    if result == "failed":
        eligible = False
        reason = f"Operation failed ({result}); no successful state to rollback"
    elif result in ("denied", "dry_run"):
        eligible = False
        reason = f"Operation did not execute (result={result}); nothing to rollback"

    # Build a condensed details summary
    details_summary = _summarize_details(action, details)

    return {
        "action": action,
        "timestamp": entry.get("timestamp", ""),
        "result": result,
        "operator": entry.get("operator", "unknown"),
        "eligible": eligible,
        "reason": reason,
        "category": category,
        "details_summary": details_summary,
        "rollback_action": rollback_action,
    }


def _summarize_details(action, details):
    """Extract key fields from audit details for display."""
    if not details:
        return {}

    key_fields = {
        "config:reload": ["source", "config_path"],
        "policy:reload": ["source", "config_path"],
        "provider:select": ["provider", "mode"],
        "auto_remediation": ["hook", "trigger", "action", "dry_run"],
        "approval:approved": ["operation", "approval_id", "approved_by"],
        "approval:created": ["operation", "reason"],
        "approval:rejected": ["operation", "reason"],
    }

    fields = key_fields.get(action, [])
    summary = {}
    for field in fields:
        if field in details:
            summary[field] = details[field]

    # If no specific fields matched, include everything (capped)
    if not summary and len(details) <= 5:
        summary = details
    elif not summary:
        summary = {"_truncated": True, "keys": list(details.keys())[:5]}

    return summary


# ─── Query Interface ────────────────────────────────────────────────────────

def query_rollback_eligibility(limit=50, category_filter=None,
                                eligible_filter=None, offset=0, log_dir=None):
    """Query audit entries with rollback eligibility analysis.

    Args:
        limit: Max entries to return (default 50).
        category_filter: Filter by category (e.g., "guarded_operation").
        eligible_filter: Filter by eligibility (True/False/None).
        offset: Skip first N entries.
        log_dir: Optional log directory override.

    Returns:
        dict with:
            entries: list of analyzed entries
            total: total matching count
            summary: aggregate statistics
    """
    # Fetch raw audit entries
    raw = query_audit_log(limit=_MAX_ENTRIES, log_dir=log_dir)
    all_entries = raw["entries"]

    # Analyze each entry
    analyzed = [analyze_entry(e) for e in all_entries]

    # Apply filters
    if category_filter:
        analyzed = [e for e in analyzed if e["category"] == category_filter]
    if eligible_filter is not None:
        analyzed = [e for e in analyzed if e["eligible"] == eligible_filter]

    total = len(analyzed)
    paginated = analyzed[offset:offset + limit]

    # Build summary
    summary = _build_summary(analyzed)

    return {
        "entries": paginated,
        "total": total,
        "summary": summary,
    }


def _build_summary(entries):
    """Build aggregate statistics from analyzed entries."""
    by_category = {}
    by_action = {}
    eligible_count = 0
    ineligible_count = 0

    for e in entries:
        cat = e["category"]
        by_category[cat] = by_category.get(cat, 0) + 1

        act = e["action"]
        by_action[act] = by_action.get(act, 0) + 1

        if e["eligible"]:
            eligible_count += 1
        else:
            ineligible_count += 1

    return {
        "total_analyzed": len(entries),
        "eligible_count": eligible_count,
        "ineligible_count": ineligible_count,
        "by_category": by_category,
        "by_action": by_action,
    }


def get_rollback_summary(log_dir=None):
    """Get a high-level rollback eligibility summary.

    Returns:
        dict with:
            total_entries: int
            eligible_count: int
            ineligible_count: int
            by_category: dict
            top_ineligible_actions: list of (action, count) tuples
    """
    data = query_rollback_eligibility(limit=_MAX_ENTRIES, log_dir=log_dir)
    summary = data["summary"]

    # Find most common ineligible actions
    action_counts = {}
    for entry in data["entries"]:
        if not entry["eligible"]:
            act = entry["action"]
            action_counts[act] = action_counts.get(act, 0) + 1

    top_ineligible = sorted(
        action_counts.items(), key=lambda x: x[1], reverse=True
    )[:5]

    return {
        "total_entries": summary["total_analyzed"],
        "eligible_count": summary["eligible_count"],
        "ineligible_count": summary["ineligible_count"],
        "by_category": summary["by_category"],
        "top_ineligible_actions": [
            {"action": a, "count": c} for a, c in top_ineligible
        ],
    }
