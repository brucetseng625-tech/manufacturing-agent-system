
"""
Expedite Options Skill

For at-risk / cannot_ship_on_time orders, generates concrete expedite options
based on current production data, instead of generic recommendations.

Options evaluated:
1. Overtime — extend current machine hours
2. Extra shift — add production shift
3. Alternate machine — route to backup/alternate machine
4. Partial shipment — split delivery into phases

Each option includes feasibility, impact, cost, blockers, and recommendation.
"""
from datetime import datetime, timedelta

from data_loader import load_json_or_csv
from skills.delivery_risk import analyze_delivery_risk, _safe_int, _safe_float
from skills.schema import normalize_skill_response


def _days_until(due_date_str):
    """Calculate days remaining until due date."""
    try:
        due = datetime.fromisoformat(due_date_str)
        return (due - datetime.now()).days
    except (ValueError, TypeError):
        return 0


def _find_alternate_machines(wo_list, machines, schedule, target_order_id):
    """Find machines that could serve as alternates for the order's work orders."""
    wo_machine_ids = {wo["machine_id"] for wo in wo_list}
    alternates = []
    for m in machines:
        if m["machine_id"] not in wo_machine_ids:
            # Check if machine is running or has capacity
            load = _safe_int(m.get("load_percent"), 0)
            max_cap = _safe_int(m.get("max_capacity_percent"), 100)
            available_capacity = max_cap - load
            if available_capacity > 0 and m["status"] == "Running":
                alternates.append({
                    "machine_id": m["machine_id"],
                    "available_capacity_pct": available_capacity,
                    "overtime_available": m.get("overtime_available", False),
                })
        elif m["machine_id"] in wo_machine_ids:
            # Current machine has backup?
            backup = m.get("backup_available", False)
            if isinstance(backup, str):
                backup = backup.lower() in ("true", "1", "yes")
            if backup:
                alternates.append({
                    "machine_id": m["machine_id"],
                    "available_capacity_pct": "backup_available",
                    "overtime_available": m.get("overtime_available", False),
                })
    return alternates


def _check_partial_shipment_feasibility(order, work_orders, materials):
    """Assess if order can be partially shipped in phases."""
    total_qty = _safe_int(order.get("quantity"), 0)
    if total_qty <= 0:
        return False, 0

    # Check how many WOs are already in progress
    in_progress = sum(1 for wo in work_orders if wo["status"] == "In Progress")
    total_wos = len(work_orders)

    # If some WOs are progressing, partial shipment is feasible
    if in_progress > 0 and total_wos > 1:
        # Estimate partial qty from in-progress WOs
        partial_pct = sum(
            _safe_int(wo.get("progress_percent"), 0) / 100.0
            for wo in work_orders if wo["status"] == "In Progress"
        )
        # Roughly estimate: each WO handles equal share
        per_wo = total_qty / total_wos
        partial_qty = int(per_wo * sum(
            _safe_int(wo.get("progress_percent"), 0)
            for wo in work_orders if wo["status"] == "In Progress"
        ) / 100.0)
        return True, max(partial_qty, int(total_qty * 0.3))

    # If material shortage is the main blocker, check if partial material available
    short_materials = [m for m in materials if m["available_qty"] < m["required_qty"]]
    if short_materials and materials:
        total_required = sum(_safe_int(m["required_qty"], 0) for m in materials)
        total_available = sum(_safe_int(m["available_qty"], 0) for m in materials)
        if total_available > 0 and total_required > 0:
            ratio = total_available / total_required
            partial_qty = int(total_qty * min(ratio, 0.7))
            return True, max(partial_qty, int(total_qty * 0.3))

    return False, 0


def _evaluate_overtime(order, work_orders, machines, delivery_report):
    """Evaluate overtime option."""
    expedite_option = order.get("expedite_option", "none")
    expedite_cost = _safe_float(order.get("expedite_cost"), 0)

    if expedite_option != "overtime" and expedite_cost == 0:
        return {
            "name": "overtime",
            "label": "加班趕工 (Overtime)",
            "feasibility": "low",
            "feasibility_reason": "No overtime configuration for this order. Requires management approval.",
            "expected_impact": "May compress schedule by 1-2 days if approved.",
            "cost_implication": "Cost not configured. Estimate based on labor rates.",
            "cost_estimate": None,
            "key_assumptions": ["Overtime requires operator availability", "Machine maintenance window may conflict"],
            "blockers": ["expedite_option is not 'overtime' in order config"],
            "recommended": False,
        }

    days_left = _days_until(order.get("due_date", ""))

    # Check machine overtime availability
    wo_machine_ids = {wo["machine_id"] for wo in work_orders}
    ot_machines = []
    for m in machines:
        if m["machine_id"] in wo_machine_ids and m.get("overtime_available", False):
            ot_machines.append(m["machine_id"])

    if not ot_machines:
        return {
            "name": "overtime",
            "label": "加班趕工 (Overtime)",
            "feasibility": "medium",
            "feasibility_reason": "Order has overtime config but no assigned machine supports overtime.",
            "expected_impact": "Limited without machine-level overtime capability.",
            "cost_implication": f"Configured cost: ${expedite_cost:,.0f}",
            "cost_estimate": expedite_cost,
            "key_assumptions": ["Machine overtime capability needs to be enabled"],
            "blockers": [f"Machine {mid} does not have overtime_available=true" for mid in wo_machine_ids],
            "recommended": False,
        }

    impact_days = min(2, max(1, days_left // 3)) if days_left > 0 else 1

    return {
        "name": "overtime",
        "label": "加班趕工 (Overtime)",
        "feasibility": "high",
        "feasibility_reason": f"Overtime configured for order. Machines {', '.join(ot_machines)} support overtime.",
        "expected_impact": f"Estimated {impact_days} day(s) schedule compression by extending {', '.join(ot_machines)} operating hours.",
        "cost_implication": f"${expedite_cost:,.0f} estimated overtime cost.",
        "cost_estimate": expedite_cost,
        "key_assumptions": [f"Operators available for {impact_days} extra day(s)", "Material supply is sufficient"],
        "blockers": [],
        "recommended": days_left <= 3 and expedite_cost > 0,
    }


def _evaluate_extra_shift(order, work_orders, machines, delivery_report):
    """Evaluate extra shift option."""
    expedite_option = order.get("expedite_option", "none")
    expedite_cost = _safe_float(order.get("expedite_cost"), 0)

    days_left = _days_until(order.get("due_date", ""))

    if expedite_option != "extra_shift":
        return {
            "name": "extra_shift",
            "label": "增开班次 (Extra Shift)",
            "feasibility": "medium",
            "feasibility_reason": "Not pre-configured for this order. Requires staffing assessment.",
            "expected_impact": "Can add 8 hours/day per shift if staffed.",
            "cost_implication": "Cost not configured. Estimate: $5,000-$10,000 per shift per week.",
            "cost_estimate": None,
            "key_assumptions": ["Additional operators available", "Training time minimal"],
            "blockers": ["expedite_option is not 'extra_shift' in order config"],
            "recommended": False,
        }

    # Check operator availability for extra shift
    operators = load_json_or_csv(
        os.path.dirname(os.path.dirname(__file__)),
        "mock_data/operators.json"
    )
    # Check if there are operators on different shifts
    shifts = {op.get("shift", "day") for op in operators}
    available_operators = [op for op in operators if op.get("status") == "Available"]

    impact_days = min(3, max(1, days_left // 2)) if days_left > 0 else 1

    return {
        "name": "extra_shift",
        "label": "增开班次 (Extra Shift)",
        "feasibility": "high" if len(available_operators) >= 2 else "medium",
        "feasibility_reason": f"{len(available_operators)} operators available across {len(shifts)} shift(s).",
        "expected_impact": f"Estimated {impact_days} day(s) schedule compression with additional shift on affected machines.",
        "cost_implication": f"${expedite_cost:,.0f} configured extra shift cost.",
        "cost_estimate": expedite_cost,
        "key_assumptions": [f"Need {impact_days} additional shift cycles", "Machine capacity supports extra shift"],
        "blockers": [],
        "recommended": days_left <= 5 and len(available_operators) >= 2,
    }


def _evaluate_alternate_machine(order, work_orders, machines, schedule, delivery_report):
    """Evaluate alternate machine routing option."""
    days_left = _days_until(order.get("due_date", ""))
    alternates = _find_alternate_machines(work_orders, machines, schedule, order["order_id"])

    if not alternates:
        return {
            "name": "alternate_machine",
            "label": "替代機台 (Alternate Machine)",
            "feasibility": "low",
            "feasibility_reason": "No alternate machines with available capacity found.",
            "expected_impact": "N/A — no viable alternate routing.",
            "cost_implication": "N/A",
            "cost_estimate": None,
            "key_assumptions": [],
            "blockers": ["No machines with available capacity outside current allocation"],
            "recommended": False,
        }

    alt_ids = [a["machine_id"] for a in alternates]
    return {
        "name": "alternate_machine",
        "label": "替代機台 (Alternate Machine)",
        "feasibility": "medium" if len(alternates) >= 1 else "low",
        "feasibility_reason": f"Found {len(alternates)} alternate option(s): {', '.join(alt_ids)}.",
        "expected_impact": "May reduce bottleneck by redistributing work to alternate machine(s). Requires setup time.",
        "cost_implication": "Setup cost and potential quality variance. Estimate: $2,000-$5,000 per machine changeover.",
        "cost_estimate": 3000 * len(alternates),
        "key_assumptions": [
            "Tooling/fixtures compatible with alternate machine",
            "Quality validation required after changeover",
            "Setup time: ~4-8 hours per machine",
        ],
        "blockers": [],
        "recommended": len(alternates) >= 1 and days_left <= 7,
    }


def _evaluate_partial_shipment(order, work_orders, materials, delivery_report):
    """Evaluate partial/split shipment option."""
    days_left = _days_until(order.get("due_date", ""))
    feasible, partial_qty = _check_partial_shipment_feasibility(order, work_orders, materials)
    total_qty = _safe_int(order.get("quantity"), 0)

    if not feasible or partial_qty <= 0:
        return {
            "name": "partial_shipment",
            "label": "分批出貨 (Partial Shipment)",
            "feasibility": "low",
            "feasibility_reason": "Insufficient data to assess partial shipment feasibility.",
            "expected_impact": "N/A",
            "cost_implication": "Additional logistics cost for multiple shipments.",
            "cost_estimate": None,
            "key_assumptions": [],
            "blockers": ["Cannot determine partial quantity from current data"],
            "recommended": False,
        }

    remaining_qty = total_qty - partial_qty
    return {
        "name": "partial_shipment",
        "label": "分批出貨 (Partial Shipment)",
        "feasibility": "high" if partial_qty > total_qty * 0.5 else "medium",
        "feasibility_reason": f"Can ship ~{partial_qty}/{total_qty} units ({partial_qty/total_qty:.0%}) in first batch.",
        "expected_impact": f"Deliver {partial_qty} units on time, remaining {remaining_qty} units delayed. Mitigates customer penalty exposure.",
        "cost_implication": "Additional shipping cost for second shipment. Estimate: $500-$2,000.",
        "cost_estimate": 1000,
        "key_assumptions": [
            f"Customer accepts {partial_qty} unit initial delivery",
            f"Remaining {remaining_qty} units delivered within 1-2 weeks",
            "Quality validation per batch required",
        ],
        "blockers": [],
        "recommended": days_left <= 3 and partial_qty > total_qty * 0.3,
    }


def _compute_ranked_recommendation(options):
    """Rank options by feasibility and recommendation status."""
    priority = {"high": 3, "medium": 2, "low": 1}

    def score(opt):
        s = priority.get(opt["feasibility"], 0)
        if opt["recommended"]:
            s += 5
        if opt["cost_estimate"] is not None and opt["cost_estimate"] > 0:
            s += 1  # Has concrete cost = more actionable
        return s

    return sorted(options, key=score, reverse=True)


import os


def handle_expedite_options(order_ids, data_dir, query=None):
    """
    Generate expedite options for an at-risk order.

    Reuses delivery-risk-analysis to understand the current risk state,
    then evaluates 4 concrete recovery options.
    """
    if not order_ids:
        return {"error": "Order ID is required for expedite options."}

    order_id = order_ids[0]

    # Reuse delivery risk analysis to understand the situation
    delivery_report = analyze_delivery_risk(order_id, data_dir)
    if "error" in delivery_report:
        return delivery_report

    # Load additional data
    orders = load_json_or_csv(data_dir, "orders.json")
    work_orders = load_json_or_csv(data_dir, "work_orders.json")
    machines = load_json_or_csv(data_dir, "machines.json")
    schedule = load_json_or_csv(data_dir, "schedule.json")
    materials = load_json_or_csv(data_dir, "materials.json")

    order = next((o for o in orders if o["order_id"] == order_id), None)
    if not order:
        return {"error": f"Order {order_id} not found"}

    related_wos = [wo for wo in work_orders if wo["order_id"] == order_id]
    order_materials = [m for m in materials if m["order_id"] == order_id]

    # Evaluate all 4 options
    options = [
        _evaluate_overtime(order, related_wos, machines, delivery_report),
        _evaluate_extra_shift(order, related_wos, machines, delivery_report),
        _evaluate_alternate_machine(order, related_wos, machines, schedule, delivery_report),
        _evaluate_partial_shipment(order, related_wos, order_materials, delivery_report),
    ]

    # Rank options
    ranked = _compute_ranked_recommendation(options)

    # Determine overall decision context
    decision = delivery_report.get("decision", "unknown")
    days_left = _days_until(order.get("due_date", ""))

    # Generate actionable recommendation
    recommended = [opt for opt in ranked if opt["recommended"]]
    if recommended:
        summary_text = (
            f"Top recommendation: {recommended[0]['label']} — "
            f"{recommended[0]['expected_impact']}"
        )
    elif decision == "can_ship_on_time":
        summary_text = f"Order {order_id} is on track. No expedite action required."
    else:
        summary_text = (
            f"No strongly recommended option for {order_id}. "
            f"Review feasibility details for manual assessment."
        )

    raw_data = {
        "order_id": order_id,
        "customer": order.get("customer"),
        "decision": decision,
        "confidence": delivery_report.get("confidence", "unknown"),
        "blockers": delivery_report.get("blockers", []),
        "owner": "Production Manager",
        "eta": order.get("due_date"),
        "next_action": summary_text,
        "escalation": delivery_report.get("escalation", "None"),
        "days_left": days_left,
        "options": ranked,
        "option_summary": {
            "total_evaluated": len(options),
            "recommended_count": len(recommended),
            "top_recommendation": recommended[0]["label"] if recommended else "None",
            "top_cost_estimate": recommended[0]["cost_estimate"] if recommended else None,
        },
        "trace": [
            "loaded order and work orders",
            "reused delivery-risk-analysis for risk assessment",
            "evaluated 4 expedite options (overtime, extra_shift, alternate_machine, partial_shipment)",
            "ranked options by feasibility and recommendation score",
        ],
    }

    return normalize_skill_response("expedite-options", raw_data)
