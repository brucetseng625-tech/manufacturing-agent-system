"""Audit chain for critical operator actions.

Tracks administrative operations (config reload, policy reload, provider switch,
alert reset, guardrail decisions) in a persistent JSONL log.

Unlike runs.jsonl which tracks skill executions, this focuses on operator-level
actions that change system state or affect access control.

Each entry:
{
  "timestamp": "2026-05-09T12:00:00Z",
  "action": "config:reload" | "policy:reload" | "provider:select" | "alerts:reset" | "guardrail:denied" | "guardrail:approved",
  "operator": "api" | "cli" | "dashboard",
  "source_ip": "127.0.0.1",
  "details": {...},
  "result": "success" | "denied" | "failed",
  "run_id": "run-xxx" | null
}

Log location: logs/audit.jsonl (configurable via MAS_AUDIT_LOG env)
"""

import json
import os
import threading
import time

_AUDIT_LOCK = threading.Lock()
_AUDIT_FILE = None
_AUDIT_ENABLED = True


def _resolve_audit_log_path(log_dir=None):
    """Resolve the audit log file path."""
    env_path = os.environ.get("MAS_AUDIT_LOG")
    if env_path:
        return env_path
    base_dir = log_dir or os.environ.get("AGENT_LOG_DIR") or os.path.abspath("logs")
    return os.path.join(base_dir, "audit.jsonl")


def _ensure_audit_log(log_dir=None):
    """Ensure the audit log file exists and is open."""
    global _AUDIT_FILE, _AUDIT_ENABLED
    if _AUDIT_FILE is not None:
        return
    path = _resolve_audit_log_path(log_dir)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _AUDIT_FILE = open(path, "a", encoding="utf-8")
        _AUDIT_ENABLED = True
    except Exception:
        _AUDIT_ENABLED = False


def _close_audit_log():
    """Close the audit log file (for testing)."""
    global _AUDIT_FILE
    if _AUDIT_FILE is not None:
        try:
            _AUDIT_FILE.close()
        except Exception:
            pass
        _AUDIT_FILE = None


def append_audit_entry(action, operator="api", source_ip=None, details=None,
                       result="success", run_id=None, log_dir=None):
    """Append an audit entry to the JSONL log.

    Args:
        action: Operation identifier (e.g., "config:reload", "provider:select")
        operator: Who performed the action ("api", "cli", "dashboard")
        source_ip: Client IP address
        details: dict with action-specific details
        result: "success", "denied", or "failed"
        run_id: Optional associated run ID
        log_dir: Optional log directory override

    Thread-safe: uses a lock to prevent interleaved writes.
    """
    _ensure_audit_log(log_dir)
    if not _AUDIT_ENABLED or _AUDIT_FILE is None:
        return

    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "action": action,
        "operator": operator,
        "source_ip": source_ip or "unknown",
        "details": details or {},
        "result": result,
        "run_id": run_id,
    }

    with _AUDIT_LOCK:
        try:
            _AUDIT_FILE.write(json.dumps(entry) + "\n")
            _AUDIT_FILE.flush()
        except Exception:
            pass


def query_audit_log(limit=50, action_filter=None, result_filter=None,
                    offset=0, log_dir=None):
    """Query the audit log.

    Args:
        limit: Max entries to return (default 50)
        action_filter: Filter by action type (e.g., "config:reload")
        result_filter: Filter by result ("success", "denied", "failed")
        offset: Skip first N entries
        log_dir: Optional log directory override

    Returns:
        dict with {"entries": [...], "total": int}
        Entries are returned newest-first (reverse chronological).
    """
    path = _resolve_audit_log_path(log_dir)
    entries = []
    total = 0

    try:
        if not os.path.exists(path):
            return {"entries": [], "total": 0}

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Apply filters
                if action_filter and entry.get("action") != action_filter:
                    continue
                if result_filter and entry.get("result") != result_filter:
                    continue

                total += 1
                entries.append(entry)
    except Exception:
        return {"entries": [], "total": 0}

    # Reverse chronological (newest first), then paginate
    entries.reverse()
    paginated = entries[offset:offset + limit]

    return {"entries": paginated, "total": total}


def get_audit_summary(log_dir=None):
    """Get a summary of audit log statistics.

    Returns:
        dict with:
            total_entries: int
            by_action: dict of action -> count
            by_result: dict of result -> count
            last_entry: most recent entry or None
    """
    data = query_audit_log(limit=10000, log_dir=log_dir)
    entries = data["entries"]

    by_action = {}
    by_result = {}
    for e in entries:
        action = e.get("action", "unknown")
        result = e.get("result", "unknown")
        by_action[action] = by_action.get(action, 0) + 1
        by_result[result] = by_result.get(result, 0) + 1

    # entries are newest-first, so last_entry is entries[0] if any
    last_entry = entries[0] if entries else None

    return {
        "total_entries": data["total"],
        "by_action": by_action,
        "by_result": by_result,
        "last_entry": last_entry,
    }
