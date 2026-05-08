
"""
Metrics and Analytics

Computes system usage statistics from the audit log (runs.jsonl).
Used by the /metrics API endpoint and the Dashboard stats panel.

Zero external dependencies: stdlib json, os, datetime, collections only.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from collections import Counter


def _load_runs(log_dir=None):
    """Load all run records from the audit log.

    Args:
        log_dir: Directory containing runs.jsonl.

    Returns:
        List of run records, or empty list if log doesn't exist.
    """
    if log_dir is None:
        log_dir = os.environ.get("AGENT_LOG_DIR") or os.path.abspath("logs")

    log_path = os.path.join(log_dir, "runs.jsonl")
    if not os.path.isfile(log_path):
        return []

    records = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def compute_metrics(log_dir=None, window_hours=24):
    """Compute system metrics from the audit log.

    Args:
        log_dir: Directory containing runs.jsonl.
        window_hours: Time window in hours for "recent" metrics (default: 24).

    Returns:
        Dict with computed metrics:
        - total_runs: int
        - success_count: int
        - error_count: int
        - success_rate: float (0-100)
        - error_rate: float (0-100)
        - skill_distribution: dict (skill -> count), top 10
        - channel_distribution: dict (channel -> count)
        - recent_runs: int (within window_hours)
        - recent_success_rate: float (0-100)
        - last_run_timestamp: str or None
    """
    records = _load_runs(log_dir)
    if not records:
        return {
            "total_runs": 0,
            "success_count": 0,
            "error_count": 0,
            "success_rate": 0.0,
            "error_rate": 0.0,
            "skill_distribution": {},
            "channel_distribution": {},
            "recent_runs": 0,
            "recent_success_rate": 0.0,
            "last_run_timestamp": None,
            "window_hours": window_hours,
        }

    total = len(records)
    success = sum(1 for r in records if r.get("status") == "success")
    error = total - success

    # Skill distribution (use skill field, fallback to intent)
    skill_counts = Counter()
    for r in records:
        skill = r.get("skill") or r.get("intent") or "unknown"
        skill_counts[skill] += 1

    # Channel distribution
    channel_counts = Counter(r.get("channel", "unknown") for r in records)

    # Recent window metrics
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    recent_records = []
    for r in records:
        ts = r.get("timestamp", "")
        if ts:
            try:
                parsed = datetime.fromisoformat(ts)
                if parsed >= cutoff:
                    recent_records.append(r)
            except (ValueError, TypeError):
                pass

    recent_total = len(recent_records)
    recent_success = sum(1 for r in recent_records if r.get("status") == "success")

    # Last run timestamp
    timestamps = [r.get("timestamp") for r in records if r.get("timestamp")]
    last_run = max(timestamps) if timestamps else None

    return {
        "total_runs": total,
        "success_count": success,
        "error_count": error,
        "success_rate": round(success / total * 100, 1) if total > 0 else 0.0,
        "error_rate": round(error / total * 100, 1) if total > 0 else 0.0,
        "skill_distribution": dict(skill_counts.most_common(10)),
        "channel_distribution": dict(channel_counts),
        "recent_runs": recent_total,
        "recent_success_rate": round(recent_success / recent_total * 100, 1) if recent_total > 0 else 0.0,
        "last_run_timestamp": last_run,
        "window_hours": window_hours,
    }
