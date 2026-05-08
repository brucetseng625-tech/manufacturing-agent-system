import json
import os
import datetime
import sys


def resolve_log_dir(log_dir=None):
    return log_dir or os.environ.get("AGENT_LOG_DIR") or os.path.abspath("logs")


def log_run(result, channel, asana_task=None, asana_posted=None, log_dir=None):
    """
    Append a structured JSONL record for the current run.

    Args:
        result (dict): Orchestrator result dict.
        channel (str): "cli" or "http".
        asana_task (str, optional): Asana Task GID.
        asana_posted (bool, optional): Whether Asana post was successful.
        log_dir (str): Directory to store logs (default: "logs").
    """
    try:
        resolved_log_dir = resolve_log_dir(log_dir)
        os.makedirs(resolved_log_dir, exist_ok=True)
        log_path = os.path.join(resolved_log_dir, "runs.jsonl")

        # Extract trace from data if available, else empty list
        trace = []
        if result.get("status") == "success" and result.get("data"):
            trace = result["data"].get("trace", [])

        # Extract skill from result, fallback to intent or null
        skill = result.get("skill") or result.get("intent")

        record = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "channel": channel,
            "query": result.get("query", ""),
            "data_dir": result.get("data_dir", ""),
            "status": result.get("status"),
            "intent": result.get("intent"),
            "order_ids": result.get("order_ids", []),
            "skill": skill,
            "run_id": result.get("run_id"),
            "asana_task": asana_task,
            "asana_posted": asana_posted,
            "error_type": result.get("type") if result.get("status") == "error" else None,
            "trace": trace,
        }
        
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            
    except Exception as e:
        # Fail-safe: Never crash the main application due to logging failure
        print(f"Warning: Failed to write audit log: {e}", file=sys.stderr)


def query_runs(log_dir=None, last_n=None, status=None, intent=None, skill=None, channel=None, run_id=None):
    """
    Query run history from the JSONL audit log with filtering support.

    Args:
        log_dir (str): Directory containing runs.jsonl (default: resolve_log_dir()).
        last_n (int): Return only the last N records.
        status (str): Filter by status ("success" or "error").
        intent (str): Filter by intent (e.g., "delivery_risk_analysis").
        skill (str): Filter by skill name (e.g., "delivery-risk-analysis", supports "team:").
        channel (str): Filter by channel ("cli" or "http").
        run_id (str): Filter by specific run ID (e.g., "run-20260508-a3f2c1").

    Returns:
        list[dict]: Matching records, newest first.
    """
    resolved_log_dir = resolve_log_dir(log_dir)
    log_path = os.path.join(resolved_log_dir, "runs.jsonl")

    if not os.path.exists(log_path):
        return []

    records = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # Skip malformed lines silently
                continue
            records.append(record)

    # Filter
    filtered = []
    for r in records:
        if status is not None and r.get("status") != status:
            continue
        if intent is not None and r.get("intent") != intent:
            continue
        if skill is not None:
            record_skill = r.get("skill") or ""
            if skill not in record_skill:
                continue
        if channel is not None and r.get("channel") != channel:
            continue
        if run_id is not None and r.get("run_id") != run_id:
            continue
        filtered.append(r)

    # Newest first
    filtered.reverse()

    # Limit
    if last_n is not None:
        filtered = filtered[:last_n]

    return filtered


def format_run_summary(runs, compact=False):
    """
    Format a list of run records into a human-readable summary.

    Args:
        runs (list[dict]): Records from query_runs().
        compact (bool): If True, use one-line-per-run format.

    Returns:
        str: Formatted summary text.
    """
    if not runs:
        return "No runs found matching the criteria."

    lines = []
    lines.append(f"Run History ({len(runs)} record(s)):")
    lines.append("=" * 60)

    for i, r in enumerate(runs, 1):
        ts = r.get("timestamp", "unknown")[:19]
        status = r.get("status", "unknown")
        channel = r.get("channel", "?")
        query = r.get("query", "")
        skill = r.get("skill", r.get("intent", "unknown"))
        order_ids = ", ".join(r.get("order_ids", [])) or "-"
        error_type = r.get("error_type", "")
        run_id = r.get("run_id", "-")

        if compact:
            status_icon = "OK" if status == "success" else f"FAIL({error_type})"
            lines.append(f"[{ts}] {status_icon} | {run_id} | {channel} | {skill} | {query} | orders: {order_ids}")
        else:
            lines.append(f"\n#{i} [{ts}] ({channel.upper()})")
            lines.append(f"  Run ID:  {run_id}")
            lines.append(f"  Status:  {status.upper()}")
            lines.append(f"  Skill:   {skill}")
            lines.append(f"  Query:   {query}")
            lines.append(f"  Orders:  {order_ids}")
            if error_type:
                lines.append(f"  Error:   {error_type}")

    return "\n".join(lines)
