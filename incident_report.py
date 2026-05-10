"""Incident report generation.

Aggregates data from timeline, audit chain, alerts, and system status
to produce a structured incident report.

Usage:
    from incident_report import generate_incident_report

    report = generate_incident_report()  # Current system snapshot
    report = generate_incident_report(window_minutes=60)  # Last 60 minutes
"""

import json
import os
import time
import threading

from audit_logger import query_runs, resolve_log_dir
from alert import get_alert_manager
from timeline import build_timeline
from audit_chain import query_audit_log, get_audit_summary
from data_source import get_system_status, get_provider_status, get_provider_health, get_degradation_status
from config import get_config_value
from incident_closure import get_closure

# Thread-safe report cache
_report_cache_lock = threading.Lock()
_last_report = None
_last_report_time = None
_last_report_cache_key = None
_report_cache_seconds = 30  # Cache reports for 30 seconds


def generate_incident_report(window_minutes=60, log_dir=None):
    """Generate an incident report aggregating all available data sources.

    Args:
        window_minutes: Time window for data aggregation (default 60).
        log_dir: Optional log directory override.

    Returns:
        dict with:
            report_id: Unique report identifier
            generated_at: ISO timestamp
            window_minutes: The time window used
            system_status: Current system state snapshot
            incident_summary: High-level summary text
            related_alerts: List of alert events in window
            related_audit: List of audit entries in window
            timeline_preview: Recent timeline events
            affected_provider: Current provider info
            resolution_status: Whether system is currently healthy
    """
    global _last_report, _last_report_time, _last_report_cache_key

    # Check cache
    now = time.time()
    cache_key = (window_minutes, log_dir)
    with _report_cache_lock:
        if _last_report is not None and _last_report_time is not None:
            if now - _last_report_time < _report_cache_seconds:
                if _last_report_cache_key == cache_key:
                    return dict(_last_report)

    resolved_log_dir = log_dir or resolve_log_dir()

    # Gather current system state
    try:
        system_status = get_system_status(resolved_log_dir)
    except Exception:
        system_status = {"system": "unknown", "provider": {}, "health": {}, "degradation": {}}

    # Gather alerts
    try:
        am = get_alert_manager()
        all_alerts = am.get_all_alerts()
    except Exception:
        all_alerts = []

    # Gather audit entries
    try:
        audit_data = query_audit_log(limit=100, log_dir=resolved_log_dir)
        audit_entries = audit_data.get("entries", [])
        audit_summary = get_audit_summary(log_dir=resolved_log_dir)
    except Exception:
        audit_entries = []
        audit_summary = {"total_entries": 0, "by_action": {}, "by_result": {}}

    # Gather timeline preview
    try:
        timeline_events = build_timeline(log_dir=resolved_log_dir, last_n=20)
    except Exception:
        timeline_events = []

    # Determine resolution status
    current_state = system_status.get("system", "unknown")
    is_resolved = current_state == "ok"
    is_degraded = system_status.get("degradation", {}).get("is_degraded", False)

    if is_degraded:
        resolution_status = "degraded"
    elif is_resolved:
        resolution_status = "resolved"
    else:
        resolution_status = "unresolved"

    # Build incident summary
    incident_summary = _build_summary(system_status, all_alerts, audit_entries)

    # Build affected provider info
    provider_info = _build_provider_info(system_status)

    report = {
        "report_id": f"incident-{int(now)}",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "window_minutes": window_minutes,
        "system_status": {
            "overall": current_state,
            "health": system_status.get("health", {}).get("status", "unknown"),
            "provider": system_status.get("provider", {}).get("name", "unknown"),
            "degraded": is_degraded,
        },
        "incident_summary": incident_summary,
        "related_alerts": _filter_alerts_for_report(all_alerts),
        "related_audit": audit_entries[:20],  # Top 20 recent
        "audit_summary": audit_summary,
        "timeline_preview": timeline_events[:10],  # Top 10 recent
        "affected_provider": provider_info,
        "resolution_status": resolution_status,
        "recommendations": _build_recommendations(system_status, is_degraded, is_resolved),
    }
    report["closure"] = get_closure(report["report_id"])

    # Cache
    with _report_cache_lock:
        _last_report = report.copy()
        _last_report_cache_key = cache_key
        _last_report_time = now

    return report


def _filter_alerts_for_report(alerts):
    """Filter and format alerts for the report."""
    result = []
    for alert in alerts:
        result.append({
            "alert_id": alert.get("alert_id", "unknown"),
            "alert_type": alert.get("alert_type", "unknown"),
            "status": alert.get("status", "firing"),
            "fired_at": alert.get("fired_at"),
            "acknowledged_at": alert.get("acknowledged_at"),
            "resolved_at": alert.get("resolved_at"),
        })
    return result


def _build_provider_info(system_status):
    """Build affected provider information."""
    provider = system_status.get("provider", {})
    degradation = system_status.get("degradation", {})
    health = system_status.get("health", {})

    return {
        "name": provider.get("name", "unknown"),
        "readiness": provider.get("readiness", "unknown"),
        "capabilities": provider.get("capabilities", []),
        "health_status": health.get("status", "unknown"),
        "active_path": degradation.get("active_path", "unknown"),
        "degradation_reason": degradation.get("reason", ""),
        "default_mode": provider.get("default_mode", "local"),
    }


def _build_summary(system_status, alerts, audit_entries):
    """Build a human-readable incident summary."""
    parts = []
    overall = system_status.get("system", "unknown")
    parts.append(f"System status: {overall}")

    # Count active alerts
    active_alerts = [a for a in alerts if a.get("status") == "firing"]
    if active_alerts:
        parts.append(f"{len(active_alerts)} active alert(s)")

    # Count denied operations
    denied_ops = [a for a in audit_entries if a.get("result") == "denied"]
    if denied_ops:
        parts.append(f"{len(denied_ops)} guarded operation(s) denied")

    # Provider state
    provider_name = system_status.get("provider", {}).get("name", "unknown")
    readiness = system_status.get("provider", {}).get("readiness", "unknown")
    parts.append(f"Provider: {provider_name} ({readiness})")

    # Degradation
    is_degraded = system_status.get("degradation", {}).get("is_degraded", False)
    if is_degraded:
        reason = system_status.get("degradation", {}).get("reason", "degraded mode")
        parts.append(f"Degradation: {reason}")

    return "; ".join(parts)


def _build_recommendations(system_status, is_degraded, is_resolved):
    """Build recommendations based on current system state."""
    recommendations = []

    if not is_resolved:
        recommendations.append("Review active alerts and acknowledge/resolved as appropriate")

    if is_degraded:
        degradation = system_status.get("degradation", {})
        recommendations.extend(degradation.get("recommendations", []))

    # Check for recent audit denials
    audit_summary = get_audit_summary()
    if audit_summary.get("by_result", {}).get("denied", 0) > 0:
        recommendations.append("Review recent guardrail denials in the audit log")

    if not recommendations:
        recommendations.append("System is healthy — no immediate action required")

    return recommendations
