"""
Observability and Traceability Layer

Provides:
1. Run ID generation (format: run-YYYYMMDD-XXXXXX)
2. Thread-local run context for tracing across components
3. Structured event logging (JSONL) covering execution lifecycle

Design principles:
- Additive only: never break existing contracts
- Zero external dependencies: stdlib uuid, json, os, datetime, threading
- Thread-safe: thread-local context for parallel team execution
- Fail-safe: logging failures never crash the application
"""
import json
import os
import sys
import uuid
import datetime
import threading

_local = threading.local()


def generate_run_id():
    """Generate a unique run ID.

    Format: run-YYYYMMDD-XXXXXX where XXXXXX is a 6-char hex UUID fragment.
    Example: run-20260508-a3f2c1

    Returns:
        str: Unique run identifier.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    short_uuid = uuid.uuid4().hex[:6]
    return f"run-{now.strftime('%Y%m%d')}-{short_uuid}"


def get_run_id():
    """Get the current thread's run ID.

    Returns None if no run context has been set.
    """
    return getattr(_local, "run_id", None)


def set_run_id(run_id):
    """Set the run ID for the current thread."""
    _local.run_id = run_id


def clear_run_id():
    """Clear the run ID for the current thread."""
    _local.run_id = None


# === Structured Event Logging ===

def _resolve_log_dir(log_dir=None):
    """Resolve the observability log directory."""
    return log_dir or os.environ.get("AGENT_LOG_DIR") or os.path.abspath("logs")


def _write_event(event):
    """Append a structured JSONL event to the event log.

    Never raises — catches and silences all exceptions.

    Args:
        event (dict): Event record with at least 'event' and 'timestamp' keys.
    """
    try:
        log_dir = _resolve_log_dir()
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "events.jsonl")

        # Inject run_id if not already present
        if "run_id" not in event:
            current = get_run_id()
            if current:
                event["run_id"] = current

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    except Exception:
        # Fail-safe: Never crash due to logging failure
        pass


def log_event(event_type, **kwargs):
    """Log a structured lifecycle event.

    Args:
        event_type (str): Event category (e.g., 'request', 'routing', 'skill_start',
                         'skill_end', 'team_start', 'team_end', 'error', 'asana_post',
                         'audit_write', 'complete').
        **kwargs: Additional event data (skill, intent, order_ids, duration, etc.).
    """
    event = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "event": event_type,
    }
    event.update(kwargs)
    _write_event(event)


def log_request(query, channel, run_id=None, data_source=None):
    """Log incoming request event."""
    log_event("request", query=query, channel=channel, run_id=run_id, data_source=data_source)


def log_routing(intent, skill_name=None, team_name=None, order_ids=None, match_score=None):
    """Log routing decision event."""
    log_event("routing", intent=intent, skill=skill_name, team=team_name,
              order_ids=order_ids or [], match_score=match_score)


def log_skill_start(skill_name, order_ids=None):
    """Log skill execution start."""
    log_event("skill_start", skill=skill_name, order_ids=order_ids or [])


def log_skill_end(skill_name, status, duration_ms=None, order_ids=None):
    """Log skill execution completion."""
    log_event("skill_end", skill=skill_name, status=status,
              duration_ms=duration_ms, order_ids=order_ids or [])


def log_team_start(team_name, steps=None):
    """Log team workflow start."""
    log_event("team_start", team=team_name, steps=steps or [])


def log_team_end(team_name, status, success_count=None, total_steps=None, duration_ms=None):
    """Log team workflow completion."""
    log_event("team_end", team=team_name, status=status,
              success_count=success_count, total_steps=total_steps, duration_ms=duration_ms)


def log_error(error_type, message, run_id=None, skill=None, query=None):
    """Log error event."""
    log_event("error", error_type=error_type, message=message,
              run_id=run_id, skill=skill, query=query)


def log_asana_post(task_gid, success, run_id=None):
    """Log Asana comment post attempt."""
    log_event("asana_post", task_gid=task_gid, success=success, run_id=run_id)


def log_complete(run_id, status, channel, intent, skill=None, duration_ms=None):
    """Log run completion event."""
    log_event("complete", run_id=run_id, status=status, channel=channel,
              intent=intent, skill=skill, duration_ms=duration_ms)
