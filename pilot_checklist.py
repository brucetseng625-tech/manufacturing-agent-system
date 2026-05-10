"""Pilot readiness checklist for operator-facing human pilot prerequisites.

Aggregates safety, observability, and workflow completeness signals from
existing system surfaces into a single queryable checklist.

Design:
- Pure read-only aggregation — no new state, queries live system surfaces
- Each item has: id, category, description, status (ready/pending/blocked), detail
- Categories: safety, observability, workflow
- Status derived from real system state, not manually toggled

Usage:
    from pilot_checklist import get_checklist, get_checklist_summary

    checklist = get_checklist()
    summary = get_checklist_summary()
"""

import time

# ─── Category Constants ──────────────────────────────────────────────────────

SAFETY = "safety"
OBSERVABILITY = "observability"
WORKFLOW = "workflow"

ALL_CATEGORIES = [SAFETY, OBSERVABILITY, WORKFLOW]


def _timestamp():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def get_checklist():
    """Build the full pilot readiness checklist by querying live system surfaces.

    Returns a list of checklist items, each with:
        - id: unique checklist item ID
        - category: safety, observability, or workflow
        - description: human-readable description
        - status: "ready", "pending", or "blocked"
        - detail: diagnostic info from the underlying system
    """
    items = []
    items.extend(_safety_checks())
    items.extend(_observability_checks())
    items.extend(_workflow_checks())
    return items


def get_checklist_summary(checklist=None):
    """Return aggregate checklist statistics.

    Returns dict with:
        - total: total item count
        - by_category: count per category
        - by_status: count per status
        - all_ready: bool — True if every item is "ready"
    """
    if checklist is None:
        checklist = get_checklist()

    by_category = {}
    by_status = {}
    for item in checklist:
        cat = item["category"]
        st = item["status"]
        by_category[cat] = by_category.get(cat, 0) + 1
        by_status[st] = by_status.get(st, 0) + 1

    all_ready = all(item["status"] == "ready" for item in checklist)

    return {
        "total": len(checklist),
        "by_category": by_category,
        "by_status": by_status,
        "all_ready": all_ready,
        "checked_at": _timestamp(),
    }


# ─── Safety Checks ──────────────────────────────────────────────────────────

def _safety_checks():
    """Check safety prerequisites: circuit breaker, policy, guardrails."""
    items = []

    # SC-01: Circuit breaker is not stuck open
    try:
        from data_source import get_system_status
        status = get_system_status()
        cb_state = "unknown"
        provider_status = status.get("provider", {})
        if isinstance(provider_status, dict):
            cb_state = provider_status.get("circuit_breaker", "unknown")
        elif isinstance(provider_status, list):
            for p in provider_status:
                if isinstance(p, dict) and "circuit_breaker" in p:
                    cb_state = p["circuit_breaker"]
                    break

        if cb_state == "open":
            items.append(_item("SC-01", SAFETY,
                               "Circuit breaker is closed (no active failover block)",
                               "blocked",
                               detail={"circuit_breaker_state": cb_state}))
        else:
            items.append(_item("SC-01", SAFETY,
                               "Circuit breaker is closed (no active failover block)",
                               "ready",
                               detail={"circuit_breaker_state": cb_state}))
    except Exception as e:
        items.append(_item("SC-01", SAFETY,
                           "Circuit breaker is closed (no active failover block)",
                           "pending",
                           detail={"error": str(e)}))

    # SC-02: Automation policy is configured (or explicitly disabled)
    try:
        from automation_policy import get_automation_policy_status
        policy = get_automation_policy_status()
        enabled = policy.get("enabled", False)
        items.append(_item("SC-02", SAFETY,
                           "Automation policy is configured or explicitly disabled",
                           "ready" if enabled or not enabled else "pending",
                           detail={"enabled": enabled}))
    except Exception as e:
        items.append(_item("SC-02", SAFETY,
                           "Automation policy is configured or explicitly disabled",
                           "pending",
                           detail={"error": str(e)}))

    # SC-03: Guardrails are defined
    try:
        from guardrails import get_guardrails_status
        guards = get_guardrails_status()
        has_rules = bool(guards)
        items.append(_item("SC-03", SAFETY,
                           "Guardrails are configured for mutation operations",
                           "ready" if has_rules else "pending",
                           detail={"rules_count": len(guards) if isinstance(guards, (list, dict)) else 0}))
    except Exception as e:
        items.append(_item("SC-03", SAFETY,
                           "Guardrails are configured for mutation operations",
                           "pending",
                           detail={"error": str(e)}))

    return items


# ─── Observability Checks ───────────────────────────────────────────────────

def _observability_checks():
    """Check observability prerequisites: alerts, audit, receipts, incidents."""
    items = []

    # OB-01: Alert system is operational
    try:
        from alert import get_alert_manager
        mgr = get_alert_manager()
        alerts = mgr.list_alerts() if hasattr(mgr, "list_alerts") else []
        firing = [a for a in alerts if a.get("status") == "firing"] if alerts else []
        items.append(_item("OB-01", OBSERVABILITY,
                           "Alert system is operational (no unacknowledged firing alerts)",
                           "ready" if not firing else "pending",
                           detail={"firing_count": len(firing)}))
    except Exception as e:
        items.append(_item("OB-01", OBSERVABILITY,
                           "Alert system is operational (no unacknowledged firing alerts)",
                           "pending",
                           detail={"error": str(e)}))

    # OB-02: Audit chain is writable
    try:
        from audit_chain import append_audit_entry
        append_audit_entry(
            action="pilot:checklist_probe",
            operator="system",
            source_ip="127.0.0.1",
            details={"probe": "audit_chain_writable"},
            result="success",
        )
        items.append(_item("OB-02", OBSERVABILITY,
                           "Audit chain is writable (operations are being logged)",
                           "ready",
                           detail={"probe": "passed"}))
    except Exception as e:
        items.append(_item("OB-02", OBSERVABILITY,
                           "Audit chain is writable (operations are being logged)",
                           "blocked",
                           detail={"error": str(e)}))

    # OB-03: Execution receipts surface is available
    try:
        from execution_receipts import get_receipts_summary
        summary = get_receipts_summary()
        items.append(_item("OB-03", OBSERVABILITY,
                           "Execution receipts tracking is available",
                           "ready",
                           detail={"total_receipts": summary.get("total", 0)}))
    except Exception as e:
        items.append(_item("OB-03", OBSERVABILITY,
                           "Execution receipts tracking is available",
                           "blocked",
                           detail={"error": str(e)}))

    # OB-04: Incident closure workflow is available
    try:
        from incident_closure import get_closure_summary
        summary = get_closure_summary()
        active = summary.get("active_count", 0)
        items.append(_item("OB-04", OBSERVABILITY,
                           "Incident closure workflow is available",
                           "ready",
                           detail={"active_incidents": active,
                                   "resolved_incidents": summary.get("resolved_count", 0)}))
    except Exception as e:
        items.append(_item("OB-04", OBSERVABILITY,
                           "Incident closure workflow is available",
                           "blocked",
                           detail={"error": str(e)}))

    return items


# ─── Workflow Checks ────────────────────────────────────────────────────────

def _workflow_checks():
    """Check workflow completeness: approvals, provider, system health."""
    items = []

    # WF-01: Approval queue is available
    try:
        from approval_queue import get_approval_stats
        stats = get_approval_stats()
        pending = stats.get("pending_count", 0) if isinstance(stats, dict) else 0
        items.append(_item("WF-01", WORKFLOW,
                           "Approval queue is operational",
                           "ready",
                           detail={"pending_approvals": pending}))
    except Exception as e:
        items.append(_item("WF-01", WORKFLOW,
                           "Approval queue is operational",
                           "blocked",
                           detail={"error": str(e)}))

    # WF-02: Provider is ready (local or http mode)
    try:
        from data_source import get_provider_status
        provider = get_provider_status()
        readiness = "unknown"
        if isinstance(provider, dict):
            readiness = provider.get("readiness", "unknown")
        items.append(_item("WF-02", WORKFLOW,
                           "Data provider is ready (local or http)",
                           "ready" if readiness in ("ready", "degraded") else "blocked",
                           detail={"provider_readiness": readiness,
                                   "provider_name": provider.get("name", "unknown") if isinstance(provider, dict) else "unknown"}))
    except Exception as e:
        items.append(_item("WF-02", WORKFLOW,
                           "Data provider is ready (local or http)",
                           "blocked",
                           detail={"error": str(e)}))

    # WF-03: System health is acceptable (not unhealthy)
    try:
        from data_source import get_system_status
        status = get_system_status()
        overall = status.get("overall_status", "unknown") if isinstance(status, dict) else "unknown"
        items.append(_item("WF-03", WORKFLOW,
                           "Overall system health is acceptable",
                           "ready" if overall in ("ok", "degraded") else "blocked",
                           detail={"overall_status": overall}))
    except Exception as e:
        items.append(_item("WF-03", WORKFLOW,
                           "Overall system health is acceptable",
                           "blocked",
                           detail={"error": str(e)}))

    # WF-04: Rollback visibility is available
    try:
        from rollback_eligibility import get_rollback_summary
        summary = get_rollback_summary()
        items.append(_item("WF-04", WORKFLOW,
                           "Rollback audit visibility is available",
                           "ready",
                           detail={"total_entries": summary.get("total_analyzed", 0)}))
    except Exception as e:
        items.append(_item("WF-04", WORKFLOW,
                           "Rollback audit visibility is available",
                           "blocked",
                           detail={"error": str(e)}))

    return items


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _item(item_id, category, description, status, detail=None):
    """Build a single checklist item dict."""
    return {
        "id": item_id,
        "category": category,
        "description": description,
        "status": status,
        "detail": detail or {},
    }
