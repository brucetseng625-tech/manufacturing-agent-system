"""
Capacity Rebalance Skill

Analyzes multi-order / multi-machine capacity pressure and provides
concrete rebalancing recommendations, not just schedule conflict detection.

Rebalance options evaluated:
1. Reassign to alternate machine — move work orders to underutilized machines
2. Resequence work orders — reorder based on priority/due date
3. Split load across shifts — distribute capacity across shifts
4. Defer low-priority order — move lower priority orders to free capacity

Each option includes feasibility, impact, capacity effect, timing, and recommendation.
"""
from datetime import datetime

from data_source import load_data, get_provider_name
from skills.delivery_risk import analyze_delivery_risk, _safe_int, _safe_float
from skills.schedule_conflict_check import check_schedule_conflict
from skills.schema import normalize_skill_response


def _days_until(due_date_str):
    """Calculate days remaining until due date."""
    try:
        due = datetime.fromisoformat(due_date_str)
        return (due - datetime.now()).days
    except (ValueError, TypeError):
        return 0


def _analyze_machine_loads(machines, work_orders):
    """Analyze current machine utilization across all work orders."""
    machine_map = {}
    for m in machines:
        mid = m["machine_id"]
        load = _safe_int(m.get("load_percent"), 0)
        max_cap = _safe_int(m.get("max_capacity_percent"), 100)
        available_cap = max_cap - load
        machine_map[mid] = {
            "machine_id": mid,
            "status": m.get("status", "Unknown"),
            "load_percent": load,
            "max_capacity_percent": max_cap,
            "available_capacity_percent": available_cap,
            "backup_available": m.get("backup_available", False),
            "overtime_available": m.get("overtime_available", False),
            "assigned_wos": [wo for wo in work_orders if wo.get("machine_id") == mid],
        }
    return machine_map


def _identify_pressure_points(order_id, order, work_orders, machine_map, schedule, all_orders):
    """Identify specific capacity pressure points for the target order."""
    pressures = []
    related_wos = [wo for wo in work_orders if wo.get("order_id") == order_id]

    for wo in related_wos:
        mid = wo.get("machine_id")
        m = machine_map.get(mid)
        if not m:
            continue

        # Check 1: Machine down
        if m["status"] == "Down":
            if m["backup_available"]:
                pressures.append({
                    "type": "machine_down_backup",
                    "machine_id": mid,
                    "severity": "medium",
                    "detail": f"{mid} is down but backup available.",
                })
            else:
                pressures.append({
                    "type": "machine_down_no_backup",
                    "machine_id": mid,
                    "severity": "high",
                    "detail": f"{mid} is down with no backup. WO {wo['wo_id']} blocked.",
                })

        # Check 2: Capacity pressure
        if m["load_percent"] > m["max_capacity_percent"] * 0.9:
            pressures.append({
                "type": "capacity_pressure",
                "machine_id": mid,
                "severity": "high",
                "detail": f"{mid} at {m['load_percent']}% of {m['max_capacity_percent']}% max.",
            })

        # Check 3: Schedule conflict
        conflicts = schedule_conflicts_for_order(order_id, schedule, order, all_orders)
        for c in conflicts:
            pressures.append({
                "type": "schedule_conflict",
                "machine_id": mid,
                "severity": "high",
                "detail": f"Conflict on {mid}: {', '.join(c['orders'])} overlap.",
                "conflict": c,
            })

        # Check 4: Late completion
        wo_est = wo.get("estimated_completion", "")
        due = order.get("due_date", "")
        if wo_est > due and wo["status"] != "Completed":
            pressures.append({
                "type": "late_completion",
                "machine_id": mid,
                "severity": "high",
                "detail": f"WO {wo['wo_id']} est. {wo_est} after due {due}.",
            })

    return pressures


def schedule_conflicts_for_order(order_id, schedule, order, all_orders):
    """Find schedule conflicts involving this order."""
    conflicts = []
    order_slots = [s for s in schedule if s.get("order_id") == order_id]
    for slot in order_slots:
        mid = slot.get("machine_id")
        t1_start = slot.get("start", "")
        t1_end = slot.get("end", "")
        if not t1_start or not t1_end:
            continue

        for other in schedule:
            if other.get("order_id") == order_id:
                continue
            if other.get("machine_id") != mid:
                continue
            t2_start = other.get("start", "")
            t2_end = other.get("end", "")
            if not t2_start or not t2_end:
                continue

            try:
                s1, e1 = datetime.fromisoformat(t1_start), datetime.fromisoformat(t1_end)
                s2, e2 = datetime.fromisoformat(t2_start), datetime.fromisoformat(t2_end)
                if s1 < e2 and s2 < e1:
                    conflicts.append({
                        "machine_id": mid,
                        "orders": [order_id, other["order_id"]],
                        "overlap_start": max(s1, s2).isoformat(),
                        "overlap_end": min(e1, e2).isoformat(),
                    })
            except (ValueError, TypeError):
                pass

    return conflicts


def _evaluate_reassign_machine(order_id, order, work_orders, machine_map, all_orders):
    """Evaluate reassigning work orders to alternate machines."""
    related_wos = [wo for wo in work_orders if wo.get("order_id") == order_id]
    current_machine_ids = {wo.get("machine_id") for wo in related_wos}

    # Find alternate machines with available capacity
    alternates = []
    for mid, m in machine_map.items():
        if mid in current_machine_ids:
            # Check backup availability
            if m["backup_available"]:
                alternates.append({
                    "machine_id": mid,
                    "type": "backup",
                    "available_cap": m["available_capacity_percent"],
                })
            continue

        # Only consider running machines with capacity
        if m["status"] != "Running":
            continue
        if m["available_capacity_percent"] <= 0:
            continue

        # Check if alternate machine has enough capacity for the WOs
        alternates.append({
            "machine_id": mid,
            "type": "alternate",
            "available_cap": m["available_capacity_percent"],
        })

    if not alternates:
        return {
            "name": "reassign_machine",
            "label": "重新分配機台 (Reassign Machine)",
            "feasibility": "low",
            "feasibility_reason": "No alternate machines with available capacity found.",
            "expected_impact": "N/A — no viable reassignment target.",
            "capacity_effect": "No capacity relief possible through reassignment.",
            "timing_implication": "N/A",
            "cost_implication": "N/A",
            "cost_estimate": None,
            "assumptions": [],
            "blockers": ["No machines with available capacity outside current allocation"],
            "recommended": False,
        }

    alt_ids = [a["machine_id"] for a in alternates]
    total_available_cap = sum(a["available_cap"] for a in alternates)

    # Check if reassignment requires setup (tooling/fixtures)
    setup_note = "Requires setup and tooling verification."
    backup_alt = [a for a in alternates if a["type"] == "backup"]
    if backup_alt:
        setup_note = "Backup machine may require minimal setup."

    days_left = _days_until(order.get("due_date", ""))

    return {
        "name": "reassign_machine",
        "label": "重新分配機台 (Reassign Machine)",
        "feasibility": "high" if total_available_cap >= 30 else "medium",
        "feasibility_reason": (
            f"Found {len(alternates)} alternate option(s): {', '.join(alt_ids)}. "
            f"Total available capacity: {total_available_cap}%."
        ),
        "expected_impact": (
            f"Redistribute work from overloaded machines to {', '.join(alt_ids)}. "
            f"Reduces bottleneck and may resolve schedule conflicts."
        ),
        "capacity_effect": (
            f"Available capacity on alternate machine(s): {total_available_cap}%. "
            f"Can absorb work from current overloaded allocation."
        ),
        "timing_implication": (
            f"Setup time: ~4-8 hours. {'Backup machine minimizes setup.' if backup_alt else setup_note} "
            f"Net time impact: +0.5-1d for changeover, potentially saves 1-2d from reduced queue."
        ),
        "cost_implication": "Changeover cost: est. $2,000-$5,000 per machine reassignment.",
        "cost_estimate": 3500 * len(alternates),
        "assumptions": [
            "Alternate machine tooling compatible with current work orders",
            "Quality validation required after reassignment",
            "Operator skill matches alternate machine requirements",
        ],
        "blockers": [],
        "recommended": len(alternates) >= 1 and days_left <= 10,
    }


def _evaluate_resequence_wos(order_id, order, work_orders, machine_map, all_orders):
    """Evaluate resequencing work orders based on priority and due dates."""
    days_left = _days_until(order.get("due_date", ""))
    order_priority = order.get("priority", "Normal")
    priority_rank = {"High": 3, "Normal": 2, "Low": 1}
    order_pri = priority_rank.get(order_priority, 2)
    penalty = _safe_float(order.get("penalty_per_day"), 0)

    # Find other orders on same machines
    related_machines = {wo.get("machine_id") for wo in work_orders if wo.get("order_id") == order_id}
    competing_wos = []
    for wo in work_orders:
        if wo.get("machine_id") in related_machines and wo.get("order_id") != order_id:
            comp_order = next((o for o in all_orders if o.get("order_id") == wo["order_id"]), None)
            comp_pri = priority_rank.get(comp_order.get("priority", "Normal"), 2) if comp_order else 1
            comp_penalty = _safe_float(comp_order.get("penalty_per_day"), 0) if comp_order else 0
            comp_due = comp_order.get("due_date", "9999-12-31") if comp_order else "9999-12-31"

            # Can we preempt this order?
            can_preempt = order_pri > comp_pri or (order_pri == comp_pri and penalty > comp_penalty)

            competing_wos.append({
                "wo_id": wo["wo_id"],
                "order_id": wo["order_id"],
                "status": wo.get("status", "Unknown"),
                "progress": wo.get("progress_percent", 0),
                "priority": comp_order.get("priority", "Unknown") if comp_order else "Unknown",
                "machine_id": wo["machine_id"],
                "can_preempt": can_preempt,
                "comp_penalty": comp_penalty,
                "comp_due": comp_due,
            })

    preemptible = [w for w in competing_wos if w["can_preempt"]]
    in_progress = [w for w in preemptible if w["status"] == "In Progress"]
    queued = [w for w in preemptible if w["status"] == "Queued"]

    if not preemptible:
        return {
            "name": "resequence",
            "label": "重排工單順序 (Resequence Work Orders)",
            "feasibility": "low",
            "feasibility_reason": (
                f"No lower-priority work orders found on same machines to preempt. "
                f"Order {order_id} priority: {order_priority}."
            ),
            "expected_impact": "N/A — no resequencing targets available.",
            "capacity_effect": "No capacity relief through resequencing.",
            "timing_implication": "N/A",
            "cost_implication": "N/A",
            "cost_estimate": None,
            "assumptions": [],
            "blockers": [f"All competing orders have equal or higher priority than {order_priority}"],
            "recommended": False,
        }

    impact_desc = []
    if queued:
        impact_desc.append(f"Delay {len(queued)} queued WO(s): {', '.join(w['wo_id'] for w in queued)}.")
    if in_progress:
        impact_desc.append(f"Preempt {len(in_progress)} in-progress WO(s) (work-in-progress loss).")

    # Calculate potential time savings
    time_savings = 0
    for w in preemptible:
        if w["status"] == "Queued":
            time_savings += 1  # Assume 1 day per queued WO
        elif w["status"] == "In Progress" and w["progress"] < 50:
            time_savings += 0.5  # Partial WIP loss

    return {
        "name": "resequence",
        "label": "重排工單順序 (Resequence Work Orders)",
        "feasibility": "high" if not in_progress else "medium",
        "feasibility_reason": (
            f"Found {len(preemptible)} preemptible WO(s) on same machines. "
            f"{len(queued)} queued, {len(in_progress)} in progress."
        ),
        "expected_impact": " ".join(impact_desc),
        "capacity_effect": (
            f"Frees capacity on shared machines. "
            f"Estimated {time_savings}d time savings for {order_id}."
        ),
        "timing_implication": (
            f"Potential {time_savings}d schedule gain for {order_id}. "
            f"{'Immediate if queued WOs.' if not in_progress else 'Delayed by WIP recovery if in-progress.'}"
        ),
        "cost_implication": (
            f"Potential penalty savings: ${penalty * time_savings:,.0f}. "
            f"WIP loss for preempted orders: est. ${sum(w['comp_penalty'] for w in in_progress):,.0f}."
        ),
        "cost_estimate": None,
        "assumptions": [
            f"Order {order_id} priority ({order_priority}) justifies preemption",
            "Preempted orders can be rescheduled without cascading delays",
            "WIP recovery cost acceptable for in-progress orders",
        ],
        "blockers": [f"Preempting in-progress WO {w['wo_id']} causes material waste" for w in in_progress if w["progress"] > 30] or [],
        "recommended": bool(preemptible) and days_left <= 7,
    }


def _evaluate_split_load(order_id, order, work_orders, machine_map, all_orders):
    """Evaluate splitting work order load across shifts or machines."""
    related_wos = [wo for wo in work_orders if wo.get("order_id") == order_id]
    days_left = _days_until(order.get("due_date", ""))
    customer_tier = order.get("customer_tier", "Standard")
    penalty = _safe_float(order.get("penalty_per_day"), 0)

    # Check if any machine supports overtime
    ot_machines = []
    for wo in related_wos:
        mid = wo.get("machine_id")
        m = machine_map.get(mid)
        if m and m.get("overtime_available"):
            ot_machines.append(mid)

    # Check multi-machine potential
    multi_machine_capable = len(set(wo.get("machine_id") for wo in related_wos)) > 1

    if not ot_machines and not multi_machine_capable:
        return {
            "name": "split_load",
            "label": "分散負載 (Split Load Across Shifts)",
            "feasibility": "low",
            "feasibility_reason": (
                "No machines support overtime and work orders are on single machine."
            ),
            "expected_impact": "Limited — no overtime capacity to leverage.",
            "capacity_effect": "No additional capacity available through shift splitting.",
            "timing_implication": "N/A",
            "cost_implication": "N/A",
            "cost_estimate": None,
            "assumptions": [],
            "blockers": ["No overtime-capable machines assigned to this order"],
            "recommended": False,
        }

    # Estimate overtime capacity gain
    ot_gain = len(ot_machines) * 4  # Assume 4 extra hours per machine per day
    ot_days = max(1, days_left // 2) if days_left > 0 else 1
    ot_cost = len(ot_machines) * 2500 * ot_days  # $2,500 per machine per day

    # Multi-machine split potential
    if multi_machine_capable:
        split_desc = "Work can be distributed across multiple machines."
        multi_impact = "Parallel processing reduces total completion time."
    else:
        split_desc = "Single machine — can only extend operating hours."
        multi_impact = "Overtime extends daily capacity on current machine(s)."

    return {
        "name": "split_load",
        "label": "分散負載 (Split Load Across Shifts)",
        "feasibility": "high" if ot_machines else "medium",
        "feasibility_reason": (
            f"{len(ot_machines)} overtime-capable machine(s): {', '.join(ot_machines) if ot_machines else 'none'}. "
            f"{split_desc}"
        ),
        "expected_impact": (
            f"Add ~{ot_gain}h/day capacity through overtime. {multi_impact} "
            f"Can compress schedule by est. {ot_days}d."
        ),
        "capacity_effect": (
            f"Overtime capacity: +{ot_gain}h/day on {', '.join(ot_machines) if ot_machines else 'N/A'}. "
            f"{'Multi-machine parallel processing available.' if multi_machine_capable else ''}"
        ),
        "timing_implication": (
            f"Schedule compression: ~{ot_days}d with {ot_days}d overtime. "
            f"Setup: immediate if operators available."
        ),
        "cost_implication": f"Overtime cost: est. ${ot_cost:,.0f} for {ot_days}d.",
        "cost_estimate": ot_cost,
        "assumptions": [
            f"Operators available for {ot_days}d overtime",
            "Material supply sufficient for extended production",
            "Quality inspection capacity available for overtime output",
        ],
        "blockers": [],
        "recommended": ot_machines and days_left <= 5 and penalty > 500,
    }


def _evaluate_defer_order(order_id, order, work_orders, machine_map, all_orders):
    """Evaluate deferring a lower-priority order to free capacity."""
    days_left = _days_until(order.get("due_date", ""))
    order_priority = order.get("priority", "Normal")
    order_penalty = _safe_float(order.get("penalty_per_day"), 0)

    # This skill is called for a specific order. The question is:
    # Can we defer OTHER orders to help THIS one?
    # Or if THIS order is low priority, should it be deferred?

    priority_rank = {"High": 3, "Normal": 2, "Low": 1}
    target_pri = priority_rank.get(order_priority, 2)

    if target_pri >= 3:  # High priority — should not be deferred
        # Check if there are low-priority orders on same machines that could be deferred
        related_machines = {wo.get("machine_id") for wo in work_orders if wo.get("order_id") == order_id}
        low_pri_orders = []
        for o in all_orders:
            if o["order_id"] == order_id:
                continue
            o_pri = priority_rank.get(o.get("priority", "Normal"), 2)
            o_machines = {wo.get("machine_id") for wo in work_orders if wo.get("order_id") == o["order_id"]}
            if o_machines & related_machines and o_pri < target_pri:
                o_days = _days_until(o.get("due_date", ""))
                o_penalty = _safe_float(o.get("penalty_per_day"), 0)
                low_pri_orders.append({
                    "order_id": o["order_id"],
                    "priority": o.get("priority"),
                    "days_left": o_days,
                    "penalty": o_penalty,
                })

        if not low_pri_orders:
            return {
                "name": "defer_order",
                "label": "延後低優先訂單 (Defer Low-Priority Order)",
                "feasibility": "low",
                "feasibility_reason": (
                    f"No lower-priority orders found on same machines. "
                    f"Order {order_id} is {order_priority} priority."
                ),
                "expected_impact": "N/A — no deferrable orders.",
                "capacity_effect": "No capacity relief through deferral.",
                "timing_implication": "N/A",
                "cost_implication": "N/A",
                "cost_estimate": None,
                "assumptions": [],
                "blockers": [f"No orders with priority lower than {order_priority} on shared machines"],
                "recommended": False,
            }

        deferred = low_pri_orders[0]  # Pick the lowest priority
        return {
            "name": "defer_order",
            "label": "延後低優先訂單 (Defer Low-Priority Order)",
            "feasibility": "high",
            "feasibility_reason": (
                f"Can defer {deferred['order_id']} ({deferred['priority']}, "
                f"{deferred['days_left']}d left) to free capacity for {order_id}."
            ),
            "expected_impact": (
                f"Free capacity by delaying {deferred['order_id']}. "
                f"Reduces queue time for {order_id}."
            ),
            "capacity_effect": (
                f"Frees shared machine capacity. "
                f"{deferred['order_id']} penalty exposure: ${deferred['penalty']:,.0f}/day."
            ),
            "timing_implication": (
                f"{order_id} gains est. 1-2d from reduced queue. "
                f"{deferred['order_id']} delayed by est. 2-3d."
            ),
            "cost_implication": (
                f"Penalty trade-off: {order_id} saves ${order_penalty:,.0f}/day, "
                f"{deferred['order_id']} costs ${deferred['penalty']:,.0f}/day."
            ),
            "cost_estimate": None,
            "assumptions": [
                f"{deferred['order_id']} customer accepts delay notification",
                "Deferred order can be rescheduled without cascading impact",
            ],
            "blockers": [],
            "recommended": True,
        }

    # Target order is NOT high priority — consider deferring IT
    return {
        "name": "defer_order",
        "label": "延後低優先訂單 (Defer Low-Priority Order)",
        "feasibility": "medium",
        "feasibility_reason": (
            f"Order {order_id} is {order_priority} priority. "
            f"Consider deferring to free capacity for higher-priority orders."
        ),
        "expected_impact": (
            f"Deferring {order_id} frees capacity for higher-priority work. "
            f"Penalty exposure: ${order_penalty:,.0f}/day if delayed."
        ),
        "capacity_effect": f"Frees capacity on assigned machines for other orders.",
        "timing_implication": f"{order_id} delayed by est. 3-5d. Higher-priority orders gain 1-2d.",
        "cost_implication": f"Penalty cost if delayed: ${order_penalty * 3:,.0f} (3d delay estimate).",
        "cost_estimate": None,
        "assumptions": [
            "Customer accepts delay notification",
            "Deferred order can be rescheduled within acceptable window",
        ],
        "blockers": [f"Order {order_id} penalty (${order_penalty:,.0f}/day) makes deferral costly"] if order_penalty > 2000 else [],
        "recommended": target_pri <= 1 and order_penalty < 500,
    }


def _compute_ranked_recommendation(options):
    """Rank options by feasibility and recommendation score."""
    priority = {"high": 3, "medium": 2, "low": 1}

    def score(opt):
        s = priority.get(opt["feasibility"], 0)
        if opt["recommended"]:
            s += 5
        if opt["cost_estimate"] is not None and opt["cost_estimate"] > 0:
            s += 1
        return s

    return sorted(options, key=score, reverse=True)


def handle_capacity_rebalance(order_ids, data_dir, query=None):
    """
    Generate capacity rebalance options for an order.

    Analyzes machine loads, schedule conflicts, and work order status
    to provide concrete rebalancing recommendations.
    """
    if not order_ids:
        return {"error": "Order ID is required for capacity rebalance."}

    order_id = order_ids[0]

    # Load data via provider layer
    orders = load_data(data_dir, "orders.json")
    work_orders = load_data(data_dir, "work_orders.json")
    machines = load_data(data_dir, "machines.json")
    schedule = load_data(data_dir, "schedule.json")

    order = next((o for o in orders if o.get("order_id") == order_id), None)
    if not order:
        return {"error": f"Order {order_id} not found"}

    # Analyze machine loads
    machine_map = _analyze_machine_loads(machines, work_orders)

    # Identify pressure points
    pressures = _identify_pressure_points(order_id, order, work_orders, machine_map, schedule, orders)

    # Reuse schedule conflict check
    conflict_result = check_schedule_conflict([order_id], data_dir)
    conflicts = conflict_result.get("details", {}).get("conflicts", [])

    # Reuse delivery risk for context
    delivery = analyze_delivery_risk(order_id, data_dir)
    delivery_decision = delivery.get("decision", "unknown") if "error" not in delivery else "unknown"

    if not pressures and not conflicts:
        # No significant capacity issues
        return normalize_skill_response("capacity-rebalance", {
            "order_id": order_id,
            "customer": order.get("customer"),
            "decision": "no_capacity_issue",
            "confidence": "High",
            "blockers": ["No significant capacity pressure points detected for this order."],
            "owner": "Production Planner",
            "eta": order.get("due_date"),
            "next_action": "No capacity rebalancing needed. Monitor machine loads proactively.",
            "escalation": "None",
            "pressures": [],
            "options": [],
            "rebalance_summary": {
                "total_pressures": 0,
                "total_conflicts": 0,
                "total_evaluated": 0,
                "recommended_count": 0,
                "top_recommendation": "None — capacity is adequate",
            },
            "days_left": _days_until(order.get("due_date", "")),
            "trace": [
                f"loaded data via provider layer ({get_provider_name()})",
                "analyzed machine loads and work order assignments",
                "no significant capacity pressure points detected",
                "rebalance plan not required",
            ],
        })

    days_left = _days_until(order.get("due_date", ""))

    # Evaluate 4 rebalance options
    options = [
        _evaluate_reassign_machine(order_id, order, work_orders, machine_map, orders),
        _evaluate_resequence_wos(order_id, order, work_orders, machine_map, orders),
        _evaluate_split_load(order_id, order, work_orders, machine_map, orders),
        _evaluate_defer_order(order_id, order, work_orders, machine_map, orders),
    ]

    ranked = _compute_ranked_recommendation(options)

    recommended = [opt for opt in ranked if opt["recommended"]]
    if recommended:
        summary_text = (
            f"Top recommendation: {recommended[0]['label']} — "
            f"{recommended[0]['expected_impact']}"
        )
    else:
        summary_text = (
            f"No strongly recommended rebalance option for {order_id}. "
            f"Review feasibility details for manual assessment."
        )

    # Pressure summary
    high_severity = [p for p in pressures if p.get("severity") == "high"]
    medium_severity = [p for p in pressures if p.get("severity") == "medium"]

    raw_data = {
        "order_id": order_id,
        "customer": order.get("customer"),
        "decision": "capacity_pressure" if pressures else "schedule_conflict",
        "confidence": delivery.get("confidence", "Medium") if "error" not in delivery else "Medium",
        "blockers": [p["detail"] for p in pressures] or [
            f"Schedule conflict on {c['machine_id']}: {', '.join(c['orders'])}" for c in conflicts
        ],
        "owner": "Production Planner",
        "eta": order.get("due_date"),
        "next_action": summary_text,
        "escalation": delivery.get("escalation", "None") if "error" not in delivery else "None",
        "days_left": days_left,
        "pressures": [
            {
                "type": p["type"],
                "machine_id": p.get("machine_id"),
                "severity": p["severity"],
                "detail": p["detail"],
            }
            for p in pressures
        ],
        "conflicts": [
            {
                "machine_id": c["machine_id"],
                "orders": c["orders"],
                "overlap_start": c.get("overlap_start"),
                "overlap_end": c.get("overlap_end"),
            }
            for c in conflicts
        ],
        "options": ranked,
        "rebalance_summary": {
            "total_pressures": len(pressures),
            "high_severity_count": len(high_severity),
            "medium_severity_count": len(medium_severity),
            "total_conflicts": len(conflicts),
            "total_evaluated": len(options),
            "recommended_count": len(recommended),
            "top_recommendation": recommended[0]["label"] if recommended else "None",
        },
        "machine_utilization": {
            mid: {
                "load_percent": m["load_percent"],
                "max_capacity_percent": m["max_capacity_percent"],
                "available_capacity_percent": m["available_capacity_percent"],
                "status": m["status"],
            }
            for mid, m in machine_map.items()
        },
        "trace": [
            f"loaded data via provider layer ({get_provider_name()})",
            "analyzed machine loads and work order assignments",
            f"identified {len(pressures)} pressure point(s) and {len(conflicts)} conflict(s)",
            "reused schedule-conflict-check and delivery-risk-analysis",
            "evaluated 4 rebalance options (reassign_machine, resequence, split_load, defer_order)",
            "ranked options by feasibility and recommendation score",
        ],
    }

    return normalize_skill_response("capacity-rebalance", raw_data)
