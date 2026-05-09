"""Incident timeline: aggregate audit runs, alerts, and access log into
a unified, reverse-chronological event stream.

Read-only surface — no mutation of existing log layers.
"""

import json
import os
import time
from audit_logger import query_runs, resolve_log_dir
from alert import get_alert_manager


def _parse_access_log(log_dir=None, last_n=100):
    """Parse recent access log entries.

    Returns list of dicts with timestamp, method, path, status_code,
    duration_ms, client, run_id.
    """
    log_dir = log_dir or resolve_log_dir()
    path = os.path.join(log_dir, "access.log")
    if not os.path.exists(path):
        return []

    entries = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception:
        return []

    # Return most recent
    return entries[-last_n:]


def build_timeline(log_dir=None, last_n=50, event_type=None):
    """Build a unified incident timeline from all available sources.

    Aggregates:
    - Audit log (runs.jsonl) as 'run' events
    - Alert log (in-memory) as 'alert' events
    - Access log (access.log) as 'access' events

    Args:
        log_dir: Optional override for log directory.
        last_n: Maximum total events to return (default 50).
        event_type: Optional filter: 'run', 'alert', 'access'.

    Returns:
        list[dict]: Events sorted newest-first, each with:
            - timestamp: ISO 8601 string
            - event_type: 'run' | 'alert' | 'access'
            - summary: compact human-readable text
            - run_id: present for run events
            - alert_id: present for alert events
            - detail: full source payload
    """
    events = []

    # 1. Audit log → run events
    runs = query_runs(log_dir=log_dir, last_n=last_n)
    for r in runs:
        status = r.get("status", "unknown")
        skill = r.get("skill") or r.get("intent") or "unknown"
        run_id = r.get("run_id", "")
        channel = r.get("channel", "?")
        query = r.get("query", "")[:80]
        error = r.get("error_type", "")

        if status == "error":
            summary = f"[{status.upper()}] {skill} via {channel}: {error}"
        else:
            summary = f"[{status.upper()}] {skill} via {channel}"
            if query:
                summary += f" — {query}"

        events.append({
            "timestamp": r.get("timestamp", ""),
            "event_type": "run",
            "summary": summary,
            "run_id": run_id,
            "alert_id": None,
            "detail": r,
        })

    # 2. Alert log → alert events
    alerts = get_alert_manager().get_all_alerts()
    for a in alerts:
        alert_type = a.get("type", "unknown")
        severity = a.get("severity", "unknown")
        alert_id = a.get("id", "")
        status = a.get("status", "unknown")
        ts = a.get("timestamp", "")

        summary = f"[{severity.upper()}] Alert {alert_id}: {alert_type} ({status})"

        events.append({
            "timestamp": ts,
            "event_type": "alert",
            "summary": summary,
            "run_id": None,
            "alert_id": alert_id,
            "detail": a,
        })

    # 3. Access log → access events (only non-200 or write operations)
    access_entries = _parse_access_log(log_dir, last_n=last_n)
    for entry in access_entries:
        status_code = entry.get("status_code", 0)
        method = entry.get("method", "GET")
        path = entry.get("path", "/")
        run_id = entry.get("run_id")

        # Skip mundane GET requests that returned 200
        if method == "GET" and status_code == 200:
            continue

        if status_code >= 400:
            summary = f"[HTTP {status_code}] {method} {path}"
        elif method in ("POST", "PUT", "DELETE"):
            summary = f"[{method}] {path} → {status_code}"
        else:
            summary = f"[HTTP {status_code}] {method} {path}"

        ts = entry.get("timestamp", "")
        events.append({
            "timestamp": ts,
            "event_type": "access",
            "summary": summary,
            "run_id": run_id,
            "alert_id": None,
            "detail": entry,
        })

    # Sort newest-first by timestamp (string comparison works for ISO 8601)
    events.sort(key=lambda e: e.get("timestamp", ""), reverse=True)

    # Filter by event type if requested
    if event_type:
        events = [e for e in events if e["event_type"] == event_type]

    # Limit
    return events[:last_n]


def timeline_summary(events):
    """Return a compact summary of the timeline."""
    if not events:
        return "No timeline events found."

    by_type = {}
    for e in events:
        t = e["event_type"]
        by_type[t] = by_type.get(t, 0) + 1

    lines = [f"Timeline ({len(events)} events):"]
    lines.append("=" * 60)
    lines.append(f"  Runs:   {by_type.get('run', 0)}")
    lines.append(f"  Alerts: {by_type.get('alert', 0)}")
    lines.append(f"  Access: {by_type.get('access', 0)}")
    lines.append("")

    for e in events[:20]:
        ts = e["timestamp"][:19] if e["timestamp"] else "unknown"
        lines.append(f"  [{ts}] {e['summary']}")

    return "\n".join(lines)
