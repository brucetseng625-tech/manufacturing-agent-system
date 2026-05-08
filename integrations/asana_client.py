
import os
import json
import urllib.error
import urllib.request

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
    try:
        token = get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        url = f"{ASANA_API_URL}/tasks/{task_gid}/stories"
        payload = json.dumps({"data": {"text": comment_text}}).encode("utf-8")
        request = urllib.request.Request(url, data=payload, headers=headers, method="POST")

        with urllib.request.urlopen(request, timeout=10):
            pass
        return True
    except (ValueError, urllib.error.HTTPError, urllib.error.URLError) as e:
        print(f"Failed to post Asana comment: {e}")
        return False

def format_success_report(response):
    """Format orchestrator success response into a comment."""
    intent = response.get("intent", "unknown")
    data = response.get("data", {})
    trace = []
    
    lines = [
        "**Agent Execution Result**",
        f"Query: {response.get('query', '')}",
        f"Intent: `{intent}`",
        f"Order IDs: `{', '.join(response.get('order_ids', []))}`",
        "Status: Success",
        ""
    ]
    
    if intent == "delivery_risk_analysis":
        blockers = data.get("blockers", [])
        actionable_blockers = [
            blocker
            for blocker in blockers
            if not str(blocker).startswith("No critical blockers")
        ]
        lines.extend([
            f"Order: {data.get('order_id')}",
            f"Decision: `{data.get('decision')}`",
            f"Confidence: {data.get('confidence')}",
            f"Blockers: {len(actionable_blockers)}",
        ])
        if actionable_blockers:
            lines.append("Top Blockers:")
            for blocker in actionable_blockers[:5]:
                lines.append(f"- {blocker}")
        trace = data.get("trace", [])
    elif intent == "schedule_conflict_check":
        status = data.get("status", "unknown")
        lines.extend([
            f"Conflict Status: `{status}`",
            f"Conflicts Found: {len(data.get('conflicts', []))}",
        ])
        trace = data.get("trace", [])
    elif intent == "quote_comparison_summary":
        materials = data.get("materials", [data])
        lines.append(f"Materials Compared: {len(materials)}")
        for material in materials[:5]:
            lines.extend([
                f"- {material.get('material')}: recommend `{material.get('recommended_supplier')}`",
                f"  Decision: {material.get('decision')}",
                f"  Confidence: {material.get('confidence')}",
                f"  Price Spread: {material.get('price_spread')}",
            ])
        trace = data.get("trace", [])
        if not trace and len(materials) == 1:
            trace = materials[0].get("trace", [])
    elif intent == "sales_response_draft":
        lines.extend([
            f"Order: {data.get('order_id')}",
            f"Shipment Status: `{data.get('shipment_status')}`",
            f"Decision: `{data.get('decision')}`",
            f"Confidence: {data.get('confidence')}",
            f"Key Message: {data.get('key_message')}",
        ])
        risk_summary = data.get("risk_summary", [])
        if risk_summary:
            lines.append("Top Risks:")
            for risk in risk_summary[:3]:
                lines.append(f"- {risk}")
        trace = data.get("trace", [])

    if trace:
        lines.extend(["", "Trace:"])
        for item in trace[:8]:
            lines.append(f"- {item}")

    return "\n".join(lines)

def format_error_report(response):
    """Format orchestrator error response into a comment."""
    error_type = response.get("type", "unknown")
    details = response.get("details", "No details provided.")
    
    lines = [
        "**Agent Execution Result**",
        f"Query: {response.get('query', '')}",
        f"Order IDs: `{', '.join(response.get('order_ids', []))}`",
        "Status: Failed",
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
