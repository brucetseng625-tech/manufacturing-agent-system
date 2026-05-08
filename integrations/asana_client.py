
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
    
    # Standard fields to display if available
    # Map skill-specific keys to standard keys
    standard_data = {}
    
    if intent == "delivery_risk_analysis":
        standard_data["decision"] = data.get("decision")
        standard_data["confidence"] = data.get("confidence")
        standard_data["owner"] = data.get("owner")
        standard_data["eta"] = data.get("due_date")
        standard_data["blockers"] = data.get("blockers", [])
        standard_data["next_action"] = data.get("recommendation")
        standard_data["escalation"] = None # Inferred from blockers count usually
        
        # Blockers processing
        actionable_blockers = [
            blocker for blocker in standard_data["blockers"]
            if not str(blocker).startswith("No critical blockers")
        ]
        standard_data["blockers"] = actionable_blockers
        
        lines.extend([
            f"Order: {data.get('order_id')}",
            f"Customer: {data.get('customer')}",
        ])
        
    elif intent == "schedule_conflict_check":
        status = data.get("status", "unknown")
        lines.extend([
            f"Conflict Status: `{status}`",
            f"Conflicts Found: {len(data.get('conflicts', []))}",
        ])
        trace = data.get("trace", [])
        # Fall through to trace printing at end
        return _append_trace(lines, trace)
        
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
        return _append_trace(lines, trace)
        
    elif intent == "sales_response_draft":
        standard_data["decision"] = data.get("decision")
        standard_data["confidence"] = data.get("confidence")
        standard_data["owner"] = data.get("owner")
        standard_data["eta"] = data.get("due_date")
        standard_data["blockers"] = data.get("risk_summary", [])
        standard_data["next_action"] = data.get("internal_guidance")
        standard_data["escalation"] = None
        
        lines.extend([
            f"Order: {data.get('order_id')}",
            f"Customer: {data.get('customer')}",
            f"Shipment Status: `{data.get('shipment_status')}`",
            f"Key Message: {data.get('key_message')}",
        ])
        
    elif intent == "internal_action_summary":
        standard_data["decision"] = data.get("current_decision")
        standard_data["confidence"] = data.get("confidence")
        standard_data["owner"] = data.get("owner_suggestion")
        standard_data["eta"] = data.get("eta")
        standard_data["blockers"] = data.get("top_blockers", [])
        standard_data["next_action"] = data.get("immediate_actions")
        standard_data["escalation"] = data.get("escalation_suggestion")
        
        lines.extend([
            f"Order: {data.get('order_id')}",
            f"Customer: {data.get('customer')}",
        ])

    # Render standardized fields for production/ops skills
    if standard_data:
        lines.append(f"Decision: `{standard_data['decision']}`")
        lines.append(f"Confidence: {standard_data['confidence']}")
        lines.append(f"Owner: {standard_data['owner']}")
        lines.append(f"ETA: {standard_data['eta']}")
        
        if standard_data["blockers"]:
            lines.append("Blockers:")
            for b in standard_data["blockers"]:
                lines.append(f"- {b}")
        else:
            lines.append("Blockers: None")
            
        if standard_data["next_action"]:
            if isinstance(standard_data["next_action"], list):
                lines.append("Next Action:")
                for a in standard_data["next_action"]:
                    lines.append(f"- {a}")
            else:
                lines.append(f"Next Action: {standard_data['next_action']}")
                
        if standard_data.get("escalation"):
            lines.append(f"Escalation: {standard_data['escalation']}")
        else:
            lines.append("Escalation: None")
            
        trace = data.get("trace", [])

    return _append_trace(lines, trace)

def _append_trace(lines, trace):
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
