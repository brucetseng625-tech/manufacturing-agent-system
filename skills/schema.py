"""
Shared schema helpers for skill output unification.

Provides a standardized response structure that all skills should follow.
This ensures CLI, API, Asana formatter, and audit log can consume outputs consistently.
"""

def normalize_skill_response(skill_name, base_data, overrides=None):
    """
    Normalize a skill's output to the unified schema.
    
    Standard Fields:
    - skill: str
    - order_id: str or None
    - order_ids: list
    - customer: str or None
    - status: str (success/error)
    - decision: str
    - confidence: str
    - blockers: list
    - owner: str
    - eta: str or None
    - next_action: str or list
    - escalation: str or None
    - summary: str
    - reply_draft: str
    - trace: list
    - details: dict (skill-specific details)
    
    Args:
        skill_name: Name of the skill (e.g., "delivery-risk-analysis")
        base_data: Raw output from the skill
        overrides: Dict to override any standard field
        
    Returns:
        Normalized response dict
    """
    standardized = {
        "skill": skill_name,
        "order_id": base_data.get("order_id"),
        "order_ids": base_data.get("order_ids", [base_data.get("order_id")] if base_data.get("order_id") else []),
        "customer": base_data.get("customer"),
        "status": base_data.get("status", "success"),
        "decision": base_data.get("decision") or base_data.get("current_decision") or base_data.get("shipment_status") or "unknown",
        "confidence": base_data.get("confidence", "unknown"),
        "blockers": base_data.get("blockers") or base_data.get("top_blockers") or base_data.get("risk_summary") or [],
        "owner": base_data.get("owner") or base_data.get("owner_suggestion") or "Unassigned",
        "eta": base_data.get("eta") or base_data.get("due_date"),
        "next_action": base_data.get("next_action") or base_data.get("immediate_actions") or base_data.get("recommendation") or base_data.get("internal_guidance") or [],
        "escalation": base_data.get("escalation") or base_data.get("escalation_suggestion"),
        "summary": base_data.get("summary") or _generate_summary(base_data, skill_name),
        "reply_draft": base_data.get("reply_draft") or base_data.get("customer_reply") or base_data.get("customer_reply_draft") or base_data.get("supplier_reply_draft") or base_data.get("asana_note"),
        "trace": base_data.get("trace", []),
        "details": {},  # Will be populated with skill-specific fields
    }
    
    # Preserve skill-specific fields in details
    skill_specific_keys = {
        "delivery-risk-analysis": ["product", "evidence", "evidence_summary"],
        "sales-response-draft": ["product", "key_message", "shipment_status"],
        "internal-action-summary": ["asana_note"],
        "quote-comparison-summary": ["materials", "material", "recommended_supplier", "price_spread", "lead_time_summary", "risks"],
        "schedule-conflict-check": ["conflicts"],
    }
    
    specific_keys = skill_specific_keys.get(skill_name, [])
    for key in specific_keys:
        if key in base_data:
            standardized["details"][key] = base_data[key]
            
    # Apply overrides
    if overrides:
        standardized.update(overrides)
        
    return standardized


def _generate_summary(data, skill_name):
    """Generate a human-readable summary based on skill type."""
    decision = data.get("decision") or data.get("current_decision") or "unknown"
    order_id = data.get("order_id", "N/A")
    customer = data.get("customer", "Unknown")
    
    if skill_name == "delivery-risk-analysis":
        blockers = data.get("blockers") or []
        actionable = [b for b in blockers if not str(b).startswith("No critical blockers")]
        if not actionable:
            return f"Order {order_id} for {customer} is on track for delivery."
        return f"Order {order_id} for {customer} has {len(actionable)} blocker(s). Decision: {decision}."
        
    elif skill_name == "sales-response-draft":
        return f"Customer reply draft generated for {customer} regarding Order {order_id}. Status: {decision}."
        
    elif skill_name == "internal-action-summary":
        owner = data.get("owner") or data.get("owner_suggestion", "Unassigned")
        return f"Action plan for {customer}/Order {order_id}: Owner={owner}, Decision={decision}."
        
    elif skill_name == "quote-comparison-summary":
        materials = data.get("materials", [data])
        count = len(materials)
        return f"Quote comparison completed for {count} material(s)."
        
    elif skill_name == "schedule-conflict-check":
        conflicts = data.get("conflicts", [])
        if conflicts:
            return f"Schedule conflict detected: {len(conflicts)} overlap(s) found."
        return "No schedule conflicts detected."
        
    return f"Skill {skill_name} completed with decision: {decision}."
