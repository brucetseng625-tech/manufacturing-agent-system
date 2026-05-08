def _safe_int(value, default=0):
    """Safely convert a value to int, handling string inputs from CSV."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_float(value, default=0.0):
    """Safely convert a value to float, handling string inputs from CSV."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default
from data_loader import load_json_or_csv
from skills.schema import normalize_skill_response
from skills.policy import get_policy

from skills.schedule_conflict_check import check_schedule_conflict


def analyze_delivery_risk(order_id, mock_data_dir):
    """
    MVP Skill: Analyze if an order can ship on time based on mock data.
    Enhanced with inventory depth, supplier lead time, capacity risk, and expedite cost.
    """
    orders = load_json_or_csv(mock_data_dir, "orders.json")
    work_orders = load_json_or_csv(mock_data_dir, "work_orders.json")
    materials = load_json_or_csv(mock_data_dir, "materials.json")
    machines = load_json_or_csv(mock_data_dir, "machines.json")
    operators = load_json_or_csv(mock_data_dir, "operators.json")

    order = next((o for o in orders if o["order_id"] == order_id), None)
    if not order:
        return {"error": f"Order {order_id} not found"}

    related_wos = [w for w in work_orders if w["order_id"] == order_id]
    order_materials = [m for m in materials if m["order_id"] == order_id]

        # New: extract order-level extended fields (handle CSV string types)
    customer_tier = order.get("customer_tier", "Standard")
    penalty_per_day = _safe_float(order.get("penalty_per_day"), 0)
    expedite_option = order.get("expedite_option", "none")
    expedite_cost = _safe_float(order.get("expedite_cost"), 0)

    evidence = [
        f"Order {order_id}: customer {order['customer']}, product {order['product']}, "
        f"qty {order['quantity']}, due {order['due_date']}, priority {order['priority']}.",
        f"Checked {len(related_wos)} work orders and {len(order_materials)} material items.",
    ]
    if customer_tier:
        evidence.append(f"Customer tier: {customer_tier}, penalty risk: ${penalty_per_day}/day.")
    blockers = []
    cost_notes = []

    for material in order_materials:
        mat_shortage_note = (
            f"Material {material['material']}: {material['available_qty']}/"
            f"{material['required_qty']} available, status {material['status']}."
        )
        # New: inventory depth check (safety stock)
        safety_stock = _safe_int(material.get("safety_stock"), 0)
        if material["available_qty"] < material["required_qty"]:
            shortage_qty = material["required_qty"] - material["available_qty"]
            lead_time = _safe_int(material.get("supplier_lead_time_days"), 0)
            reliability = _safe_float(material.get("supplier_reliability"), 0.5)

            mat_shortage_note += (
                f" Shortage of {shortage_qty} units. Supplier lead time: {lead_time}d, "
                f"reliability: {reliability:.0%}."
            )
            evidence.append(mat_shortage_note)

            # Assess if reorder can recover in time
            effective_lead_days = int(lead_time / max(reliability, 0.1)) if reliability > 0 else lead_time * 2
            if safety_stock > 0 and material["available_qty"] <= safety_stock:
                blockers.append(
                    f"Material shortage + below safety stock: {material['material']} has "
                    f"{material['available_qty']}/{material['required_qty']} (safety stock: {safety_stock})."
                )
            elif material["status"] == "Shortage":
                blockers.append(
                    f"Material shortage: {material['material']} has "
                    f"{material['available_qty']}/{material['required_qty']} available."
                )

            # New: assess reorder feasibility
            if lead_time > 0:
                from datetime import datetime, timedelta
                try:
                    due = datetime.fromisoformat(order["due_date"])
                    today = datetime.now()
                    days_left = (due - today).days
                    if effective_lead_days > days_left:
                        blockers.append(
                            f"Reorder unlikely to arrive in time: {material['material']} needs "
                            f"~{effective_lead_days}d effective lead time, but only {days_left}d until due date."
                        )
                    else:
                        cost_notes.append(
                            f"Reorder feasible for {material['material']}: {lead_time}d lead time "
                            f"fits within {days_left}d remaining (reliability-adjusted: ~{effective_lead_days}d)."
                        )
                except (ValueError, TypeError):
                    pass
        else:
            evidence.append(mat_shortage_note)
            if safety_stock > 0 and material["available_qty"] <= safety_stock:
                cost_notes.append(
                    f"Inventory depth warning: {material['material']} available ({material['available_qty']}) "
                    f"at or below safety stock ({safety_stock})."
                )

    for wo in related_wos:
        machine = next((m for m in machines if m["machine_id"] == wo["machine_id"]), None)
        evidence.append(
            f"WO {wo['wo_id']}: {wo['status']}, {wo['progress_percent']}% complete, "
            f"machine {wo['machine_id']}, estimated completion {wo['estimated_completion']}."
        )
        if machine:
            # New: check backup availability
            backup_available = machine.get("backup_available", False)
            if isinstance(backup_available, str):
                backup_available = backup_available.lower() in ("true", "1", "yes")
            max_capacity = _safe_int(machine.get("max_capacity_percent"), 100)
            load = _safe_int(machine.get("load_percent"), 0)

            if machine["status"] == "Down":
                if backup_available:
                    evidence.append(
                        f"Machine {wo['machine_id']} is down, but backup is available."
                    )
                else:
                    blockers.append(
                        f"Machine {wo['machine_id']} is down for maintenance until "
                        f"{machine['next_maintenance']} (no backup available)."
                    )
            if load > max_capacity * 0.9:
                cost_notes.append(
                    f"Capacity pressure: {wo['machine_id']} at {load}% of {max_capacity}% max capacity."
                )
            if wo["estimated_completion"] > order["due_date"]:
                blockers.append(
                    f"WO {wo['wo_id']} finishes on {wo['estimated_completion']}, "
                    f"after due date {order['due_date']}."
                )

    absent_operators = [operator for operator in operators if operator["status"] != "Available"]
    for operator in operators:
        evidence.append(
            f"Operator {operator['operator_id']}: skill {operator['skill']}, "
            f"shift {operator['shift']}, status {operator['status']}."
        )
    for operator in absent_operators:
        blockers.append(
            f"Operator coverage risk: {operator['skill']} on {operator['shift']} shift is "
            f"{operator['status']}."
        )

    schedule_report = check_schedule_conflict([order_id], mock_data_dir)
    evidence.append(f"Schedule conflict status: {schedule_report.get('decision', schedule_report.get('status', 'unknown'))}.")
    conflicts = schedule_report.get("details", {}).get("conflicts", [])
    for conflict in conflicts:
        blockers.append(
            f"Schedule conflict: {', '.join(conflict['orders'])} overlap on "
            f"{conflict['machine_id']} from {conflict['overlap_start']} to "
            f"{conflict['overlap_end']}. Suggested action: {conflict['suggestion']}"
        )

    # --- Decision logic enhanced with new fields ---
    policy = get_policy()
    dr = policy.get("delivery_risk", {})
    at_risk_max = dr.get("at_risk_blocker_max", 2)
    vip_penalty = dr.get("vip_penalty_threshold", 2000)

    if not blockers:
        decision = "can_ship_on_time"
        confidence = "High"
        recommendation = "Proceed with the current production plan and keep normal monitoring."
        customer_reply = "Production is on track for the committed delivery date."
    elif len(blockers) <= at_risk_max:
        decision = "at_risk"
        # New: adjust confidence based on expedite option availability
        if expedite_option != "none" and expedite_cost > 0:
            confidence = "Medium"
            cost_notes.append(f"Expedite option available: {expedite_option} at ${expedite_cost:,.0f}.")
        else:
            confidence = "Low"

        recommendation = (
            f"Escalate the blockers, reserve inspection capacity, and confirm whether overtime "
            f"or alternate machine allocation can recover the schedule."
        )
        if expedite_option != "none":
            recommendation += f" Consider activating {expedite_option} (cost: ${expedite_cost:,.0f})."
        customer_reply = (
            "We are reviewing the latest production schedule and will confirm the delivery "
            "commitment shortly."
        )
    else:
        decision = "cannot_ship_on_time"
        # New: VIP customers with high penalties get different confidence framing
        if customer_tier == "VIP" and penalty_per_day > vip_penalty:
            confidence = "High"
            cost_notes.append(
                f"VIP customer with high penalty exposure (${penalty_per_day:,.0f}/day). "
                f"Immediate escalation required."
            )
        else:
            confidence = "High"

        recommendation = (
            "Escalate immediately for material procurement, alternate machine allocation, "
            "operator coverage, and customer delivery renegotiation."
        )
        if expedite_option != "none" and expedite_cost > 0:
            recommendation += (
                f" Expedite via {expedite_option} may reduce delay (estimated cost: ${expedite_cost:,.0f})."
            )
        customer_reply = (
            "Current production constraints may affect the committed delivery date. We are "
            "working on recovery actions and will provide an updated delivery commitment."
        )

    raw_report = {
        "order_id": order_id,
        "customer": order["customer"],
        "product": order["product"],
        "due_date": order["due_date"],
        "decision": decision,
        "confidence": confidence,
        "blockers": blockers or ["No critical blockers found in current mock data."],
        "evidence": evidence,
        "evidence_summary": f"Checked {len(related_wos)} work orders, {len(order_materials)} material items, {len(machines)} machines, and {len(operators)} operators.",
        "recommendation": recommendation,
        "customer_reply": customer_reply,
        "customer_tier": customer_tier,
        "penalty_per_day": penalty_per_day,
        "expedite_option": expedite_option,
        "expedite_cost": expedite_cost,
        "cost_notes": cost_notes,
        "trace": [
            "loaded orders",
            "loaded work orders",
            "loaded materials",
            "loaded machines",
            "loaded operators",
            "checked schedule conflicts",
            "evaluated delivery risk with inventory/supplier/capacity data",
        ],
        "owner": "Production Team",
        "eta": order["due_date"],
        "next_action": recommendation,
        "escalation": _compute_escalation(len(blockers), customer_tier, penalty_per_day),
    }

    return normalize_skill_response("delivery-risk-analysis", raw_report)


def _compute_escalation(blocker_count, customer_tier, penalty_per_day):
    """Compute escalation path considering customer tier and penalty exposure."""
    policy = get_policy()
    esc = policy.get("delivery_risk", {}).get("escalation", {})
    vip_vp_penalty = esc.get("vip_vp_level_penalty", 2000)
    immediate_threshold = esc.get("immediate_blocker_count", 3)
    monitor_threshold = esc.get("monitor_blocker_count", 1)

    if customer_tier == "VIP" and penalty_per_day > vip_vp_penalty:
        return "Immediate VP-level escalation required (VIP customer, high penalty exposure)."
    if blocker_count > immediate_threshold - 1:
        return "Escalate immediately to production manager."
    if blocker_count > monitor_threshold - 1:
        return "Escalate if blockers persist beyond 24 hours."
    return "None"
