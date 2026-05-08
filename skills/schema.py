"""
Shared schema helpers for skill output unification.

Provides a standardized response structure that all skills should follow.
This ensures CLI, API, Asana formatter, and audit log can consume outputs consistently.
"""

# Metadata describing the unified output schema.
# Used by GET /schema and can be consumed by front-end consumers.
SCHEMA_METADATA = {
    "version": "1.0",
    "top_level_shared_fields": {
        "skill": {"type": "string", "description": "Skill identifier (e.g., delivery-risk-analysis, team:comprehensive-analysis)"},
        "order_id": {"type": "string|null", "description": "Primary order ID when querying a single order"},
        "order_ids": {"type": "array", "description": "All order IDs extracted from the query"},
        "customer": {"type": "string|null", "description": "Customer name associated with the order"},
        "status": {"type": "string", "description": "Execution status: success or error"},
        "decision": {"type": "string", "description": "Core decision or status label from the skill"},
        "confidence": {"type": "string", "description": "Confidence level in the decision"},
        "blockers": {"type": "array", "description": "List of identified blockers or risks"},
        "owner": {"type": "string", "description": "Suggested responsible party"},
        "eta": {"type": "string|null", "description": "Expected due date or resolution timeline"},
        "next_action": {"type": "string|array", "description": "Recommended next step(s)"},
        "escalation": {"type": "string|null", "description": "Escalation path if needed"},
        "summary": {"type": "string", "description": "Human-readable one-line summary"},
        "reply_draft": {"type": "string|null", "description": "Pre-written message draft (customer or supplier)"},
        "trace": {"type": "array", "description": "Execution trace / audit trail"},
        "details": {"type": "object", "description": "Skill-specific supplementary data (see details section)"}
    },
    "details_usage": {
        "description": "The 'details' object contains skill-specific fields not covered by the shared schema.",
        "purpose": "Preserve semantic richness without polluting top-level namespace.",
        "examples": {
            "delivery-risk-analysis": ["evidence", "evidence_summary", "product", "customer_tier", "penalty_per_day", "expedite_option", "expedite_cost", "cost_notes"],
            "sales-response-draft": ["shipment_status", "key_message", "product"],
            "internal-action-summary": ["asana_note"],
            "quote-comparison-summary": ["materials", "recommended_supplier", "price_spread", "lead_time_summary", "risks", "supplier_scores", "tradeoffs"],
            "schedule-conflict-check": ["conflicts"],
            "expedite-options": ["options", "option_summary", "days_left"],
            "material-shortage-recovery": ["shortages", "options", "recovery_summary", "days_left"],
            "capacity-rebalance": ["pressures", "conflicts", "options", "rebalance_summary", "days_left", "machine_utilization"]
        }
    },
    "team_workflow_structure": {
        "description": "When skill starts with 'team:', the data object contains team execution results.",
        "top_level": {
            "team_name": {"type": "string", "description": "Team identifier (e.g., comprehensive-analysis)"},
            "intent": {"type": "string", "description": "Team intent string"},
            "results": {"type": "object", "description": "Map of alias -> individual skill output (each follows the unified schema)"},
            "trace": {"type": "array", "description": "Combined execution trace across all team steps"},
            "order_id": {"type": "string|null", "description": "Primary order ID"}
        }
    }
}


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
        "delivery-risk-analysis": ["product", "evidence", "evidence_summary", "customer_tier", "penalty_per_day", "expedite_option", "expedite_cost", "cost_notes"],
        "sales-response-draft": ["product", "key_message", "shipment_status"],
        "internal-action-summary": ["asana_note"],
        "quote-comparison-summary": ["materials", "material", "recommended_supplier", "price_spread", "lead_time_summary", "risks", "supplier_scores", "tradeoffs"],
        "schedule-conflict-check": ["conflicts"],
        "expedite-options": ["options", "option_summary", "days_left"],
        "material-shortage-recovery": ["shortages", "options", "recovery_summary", "days_left"],
        "capacity-rebalance": ["pressures", "conflicts", "options", "rebalance_summary", "days_left", "machine_utilization"],
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
        
    elif skill_name == "capacity-rebalance":
        rebal = data.get("rebalance_summary", {})
        rec = rebal.get("top_recommendation", "None")
        count = rebal.get("recommended_count", 0)
        pressures = rebal.get("total_pressures", 0)
        conflicts = rebal.get("total_conflicts", 0)
        if pressures == 0 and conflicts == 0:
            return f"Capacity analysis for Order {order_id}: no capacity issues detected."
        if count > 0:
            return f"Capacity rebalance for Order {order_id}: {pressures} pressure(s), {conflicts} conflict(s), {count} recommended option(s), top={rec}."
        return f"Capacity rebalance for Order {order_id}: {pressures} pressure(s), {conflicts} conflict(s), no strongly recommended options."

    elif skill_name == "material-shortage-recovery":
        rec_summary = data.get("recovery_summary", {})
        rec = rec_summary.get("top_recommendation", "None")
        count = rec_summary.get("recommended_count", 0)
        shortages = rec_summary.get("total_shortages", 0)
        if shortages == 0:
            return f"Material shortage analysis for Order {order_id}: no shortages detected."
        if count > 0:
            return f"Material shortage recovery for Order {order_id}: {shortages} shortage(s), {count} recommended option(s), top={rec}."
        return f"Material shortage recovery for Order {order_id}: {shortages} shortage(s), no strongly recommended options."

    elif skill_name == "expedite-options":
        opt_summary = data.get("option_summary", {})
        rec = opt_summary.get("top_recommendation", "None")
        count = opt_summary.get("recommended_count", 0)
        if count > 0:
            return f"Expedite analysis for Order {order_id}: {count} recommended option(s), top={rec}."
        return f"Expedite analysis for Order {order_id}: no strongly recommended options. Review feasibility details."

    return f"Skill {skill_name} completed with decision: {decision}."
