
import os
import json
import requests

ASANA_API_URL = "https://app.asana.com/api/1.0"

def get_token():
    """Get Asana PAT from environment variable."""
    token = os.environ.get("ASANA_ACCESS_TOKEN")
    if not token:
        raise ValueError("ASANA_ACCESS_TOKEN environment variable is not set.")
    return token

def post_comment(task_gid, comment_text):
    """
    Post a comment to an Asana task.
    Returns True if successful, False otherwise.
    Does not raise exceptions for network errors; logs and returns False.
    """
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    url = f"{ASANA_API_URL}/tasks/{task_gid}/stories"
    payload = {"data": {"text": comment_text}}
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"⚠️  Failed to post Asana comment: {e}")
        return False

def format_success_report(response):
    """Format orchestrator success response into a comment."""
    intent = response.get("intent", "unknown")
    data = response.get("data", {})
    
    lines = [
        "**Agent Execution Result**",
        f"Intent: `{intent}`",
        f"Status: ✅ Success",
        ""
    ]
    
    if intent == "delivery_risk_analysis":
        lines.extend([
            f"Order: {data.get('order_id')}",
            f"Decision: `{data.get('decision')}`",
            f"Confidence: {data.get('confidence')}",
            f"Blockers: {len(data.get('blockers', []))}",
        ])
    elif intent == "schedule_conflict_check":
        status = data.get("status", "unknown")
        lines.extend([
            f"Conflict Status: `{status}`",
            f"Conflicts Found: {len(data.get('conflicts', []))}",
        ])
        
    return "\n".join(lines)

def format_error_report(response):
    """Format orchestrator error response into a comment."""
    error_type = response.get("type", "unknown")
    details = response.get("details", "No details provided.")
    
    lines = [
        "**Agent Execution Result**",
        f"Status: ❌ Failed",
        f"Error Type: `{error_type}`",
        ""
    ]
    
    if isinstance(details, list):
        lines.append("Errors:")
        for item in details[:5]: # Limit to 5 errors
            lines.append(f"- {item}")
        if len(details) > 5:
            lines.append(f"... and {len(details) - 5} more.")
    else:
        lines.append(f"Details: {details}")
        
    return "\n".join(lines)
