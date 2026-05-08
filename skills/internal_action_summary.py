from skills.delivery_risk import analyze_delivery_risk

def handle_internal_action_summary(order_ids, data_dir, query=None):
    """
    Generate an internal follow-up summary for PM / Ops / Production.
    Reuses delivery risk analysis to avoid rewriting logic.
    """
    if not order_ids:
        return {"error": "Order ID is required for internal action summary."}

    delivery_report = analyze_delivery_risk(order_ids[0], data_dir)
    if "error" in delivery_report:
        return delivery_report

    decision = delivery_report.get("decision")
    blockers = delivery_report.get("blockers", [])
    actionable_blockers = [b for b in blockers if not str(b).startswith("No critical blockers")]

    immediate_actions = []
    owner = "Production Supervisor"
    escalation = "None"

    if decision == "can_ship_on_time":
        immediate_actions.append("Continue normal production monitoring.")
        immediate_actions.append("Confirm raw material inventory for next batch.")
        owner = "Line Leader"
        escalation = "None"
    elif decision == "at_risk":
        immediate_actions.append("Verify blocker recovery timeline.")
        immediate_actions.append("Prepare overtime plan if schedule slips.")
        owner = "Production Supervisor"
        escalation = "Escalate to Operations Manager if blockers persist > 4 hours."
    else: # cannot_ship_on_time
        immediate_actions.append("Stop and assess: prioritize recovery path.")
        immediate_actions.append("Draft customer delay notification (see sales-response-draft).")
        immediate_actions.append("Request management decision on rescheduling vs. cancellation.")
        owner = "Operations Manager"
        escalation = "Immediate escalation required. Notify Sales and Production Director."

    # Generate Asana note
    asana_note = f"Action Required for {delivery_report['order_id']}: "
    asana_note += f"Status: {decision}. "
    if actionable_blockers:
        asana_note += f"Blocker: {actionable_blockers[0]}. "
    asana_note += f"Owner: {owner}. "
    asana_note += "Next Step: Execute immediate actions."

    return {
        "order_id": delivery_report["order_id"],
        "customer": delivery_report["customer"],
        "current_decision": decision,
        "confidence": delivery_report["confidence"],
        "top_blockers": actionable_blockers[:3],
        "immediate_actions": immediate_actions,
        "owner_suggestion": owner,
        "escalation_suggestion": escalation,
        "asana_note": asana_note,
        "trace": delivery_report["trace"] + ["generated internal action summary"],
        "eta": delivery_report["due_date"],
    }
