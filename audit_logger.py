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
