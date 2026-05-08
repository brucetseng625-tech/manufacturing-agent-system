
from data_loader import load_json_or_csv

from skills.schedule_conflict_check import check_schedule_conflict


def analyze_delivery_risk(order_id, mock_data_dir):
    """
    MVP Skill: Analyze if an order can ship on time based on mock data.
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

    evidence = [
        f"Order {order_id}: customer {order['customer']}, product {order['product']}, "
        f"qty {order['quantity']}, due {order['due_date']}, priority {order['priority']}.",
        f"Checked {len(related_wos)} work orders and {len(order_materials)} material items.",
    ]
    blockers = []

    for material in order_materials:
        evidence.append(
            f"Material {material['material']}: {material['available_qty']}/"
            f"{material['required_qty']} available, status {material['status']}."
        )
        if material["status"] == "Shortage":
            blockers.append(
                f"Material shortage: {material['material']} has "
                f"{material['available_qty']}/{material['required_qty']} available."
            )

    for wo in related_wos:
        machine = next((m for m in machines if m["machine_id"] == wo["machine_id"]), None)
        evidence.append(
            f"WO {wo['wo_id']}: {wo['status']}, {wo['progress_percent']}% complete, "
            f"machine {wo['machine_id']}, estimated completion {wo['estimated_completion']}."
        )
        if machine:
            if machine["status"] == "Down":
                blockers.append(
                    f"Machine {wo['machine_id']} is down for maintenance until "
                    f"{machine['next_maintenance']}."
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
    evidence.append(f"Schedule conflict status: {schedule_report['status']}.")
    for conflict in schedule_report["conflicts"]:
        blockers.append(
            f"Schedule conflict: {', '.join(conflict['orders'])} overlap on "
            f"{conflict['machine_id']} from {conflict['overlap_start']} to "
            f"{conflict['overlap_end']}. Suggested action: {conflict['suggestion']}"
        )

    if not blockers:
        decision = "can_ship_on_time"
        confidence = "High"
        recommendation = "Proceed with the current production plan and keep normal monitoring."
        customer_reply = "Production is on track for the committed delivery date."
    elif len(blockers) <= 2:
        decision = "at_risk"
        confidence = "Medium"
        recommendation = (
            "Escalate the blockers, reserve inspection capacity, and confirm whether overtime "
            "or alternate machine allocation can recover the schedule."
        )
        customer_reply = (
            "We are reviewing the latest production schedule and will confirm the delivery "
            "commitment shortly."
        )
    else:
        decision = "cannot_ship_on_time"
        confidence = "High"
        recommendation = (
            "Escalate immediately for material procurement, alternate machine allocation, "
            "operator coverage, and customer delivery renegotiation."
        )
        customer_reply = (
            "Current production constraints may affect the committed delivery date. We are "
            "working on recovery actions and will provide an updated delivery commitment."
        )

    report = {
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
        "trace": [
            "loaded orders",
            "loaded work orders",
            "loaded materials",
            "loaded machines",
            "loaded operators",
            "checked schedule conflicts",
            "evaluated delivery risk",
        ],
        "owner": "Production Team",
        "next_action": recommendation,
    }
    return report
