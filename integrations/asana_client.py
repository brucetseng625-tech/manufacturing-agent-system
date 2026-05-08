
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
    
    # Check if this is a team result
    if response.get("is_team"):
        team_name = data.get("team_name", "Unknown Team")
        lines.append(f"Team Workflow: `{team_name}`")
        lines.append("")
        results = data.get("results", {})
        if not isinstance(results, dict):
            lines.append("Warning: Invalid team results structure")
            return _append_trace(lines, data.get("trace", []))
        for alias, step in results.items():
            if not isinstance(step, dict):
                lines.append(f"**{alias.upper()}**: Unexpected result type")
                continue
            if "error" in step:
                lines.append(f"**{alias.upper()}**: FAILED - {step['error']}")
                lines.append("")
                continue
            step_decision = step.get("decision", "N/A")
            lines.append(f"**{alias.upper()}**")
            lines.append(f"Decision: `{step_decision}`")
            lines.append(f"Confidence: {step.get('confidence', 'N/A')}")
            blockers = step.get("blockers", [])
            if isinstance(blockers, list) and blockers:
                lines.append("Blockers:")
                for b in blockers[:2]:
                    lines.append(f"- {b}")
            lines.append("")
        summary = data.get("summary", {})
        if summary:
            total = summary.get("total_steps", 0)
            success = summary.get("success_count", 0)
            failed = summary.get("failed_count", 0)
            lines.append(f"**Summary**: {success}/{total} steps succeeded, {failed} failed")
            if summary.get("partial_success"):
                lines.append("Status: PARTIAL SUCCESS")
        trace = data.get("trace", [])
        return _append_trace(lines, trace)

    # Use standardized fields from unified schema
    # All skills now return: decision, confidence, owner, eta, blockers, next_action, escalation, summary
    
    # Skill-specific header info
    if intent == "delivery_risk_analysis":
        lines.extend([
            f"Order: {data.get('order_id')}",
            f"Customer: {data.get('customer')}",
        ])
    elif intent == "schedule_conflict_check":
        status = data.get("status", "unknown")
        conflicts = data.get("details", {}).get("conflicts", [])
        lines.extend([
            f"Conflict Status: `{status}`",
            f"Conflicts Found: {len(conflicts)}",
        ])
        trace = data.get("trace", [])
        return _append_trace(lines, trace)
    elif intent == "quote_comparison_summary":
        materials = data.get("details", {}).get("materials", [data])
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
        lines.extend([
            f"Order: {data.get('order_id')}",
            f"Customer: {data.get('customer')}",
            f"Shipment Status: `{data.get('details', {}).get('shipment_status')}`",
            f"Key Message: {data.get('details', {}).get('key_message')}",
        ])
    elif intent == "internal_action_summary":
        lines.extend([
            f"Order: {data.get('order_id')}",
            f"Customer: {data.get('customer')}",
        ])

    # Render standardized fields (common to most skills)
    lines.append(f"Decision: `{data.get('decision')}`")
    lines.append(f"Confidence: {data.get('confidence')}")
    lines.append(f"Owner: {data.get('owner')}")
    lines.append(f"ETA: {data.get('eta')}")
    
    blockers = data.get("blockers", [])
    if blockers:
        lines.append("Blockers:")
        for b in blockers:
            lines.append(f"- {b}")
    else:
        lines.append("Blockers: None")
        
    next_action = data.get("next_action")
    if next_action:
        if isinstance(next_action, list):
            lines.append("Next Action:")
            for a in next_action:
                lines.append(f"- {a}")
        else:
            lines.append(f"Next Action: {next_action}")
            
    escalation = data.get("escalation")
    if escalation:
        lines.append(f"Escalation: {escalation}")
    else:
        lines.append("Escalation: None")
        
    # Add summary if available
    summary = data.get("summary")
    if summary:
        lines.append(f"Summary: {summary}")
        
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
