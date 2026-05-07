
import json
import os

def analyze_delivery_risk(order_id, mock_data_dir):
    """
    MVP Skill: Analyze if an order can ship on time based on mock data.
    """
    # Load Data
    orders = json.load(open(f"{mock_data_dir}/orders.json"))
    work_orders = json.load(open(f"{mock_data_dir}/work_orders.json"))
    materials = json.load(open(f"{mock_data_dir}/materials.json"))
    machines = json.load(open(f"{mock_data_dir}/machines.json"))
    
    # Find Target Order
    order = next((o for o in orders if o["order_id"] == order_id), None)
    if not order:
        return {"error": f"Order {order_id} not found"}
        
    # Find Related Work Orders
    related_wos = [w for w in work_orders if w["order_id"] == order_id]
    
    # Check Materials
    order_materials = [m for m in materials if m["order_id"] == order_id]
    shortages = [m for m in order_materials if m["status"] == "Shortage"]
    
    # Check Machine/Time Risks
    machine_risks = []
    for wo in related_wos:
        machine = next((m for m in machines if m["machine_id"] == wo["machine_id"]), None)
        if machine:
            if machine["status"] == "Down":
                machine_risks.append(f"Machine {wo['machine_id']} is DOWN for maintenance.")
            if wo["estimated_completion"] > order["due_date"]:
                machine_risks.append(f"WO {wo['wo_id']} estimated finish ({wo['estimated_completion']}) exceeds due date.")
                
    # Decision Logic
    risks = shortages + machine_risks
    decision = "can_ship_on_time" if not risks else ("at_risk" if len(risks) < 3 else "cannot_ship_on_time")
    
    # Generate Report
    report = {
        "order_id": order_id,
        "decision": decision,
        "confidence": "High" if not risks else "Low",
        "blockers": risks,
        "evidence_summary": f"Checked {len(related_wos)} WOs and {len(order_materials)} material items.",
        "recommendation": "Proceed" if not risks else "Escalate for material procurement and machine scheduling adjustment.",
        "customer_reply": "We are reviewing the schedule and will confirm shortly." if risks else "Production is on track for delivery."
    }
    return report
