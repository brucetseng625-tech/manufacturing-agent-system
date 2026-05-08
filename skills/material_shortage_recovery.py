
"""
Material Shortage Recovery Skill

For orders with material shortages, provides concrete recovery options
instead of just listing shortages as blockers.

Recovery options evaluated:
1. Emergency reorder — expedited purchase from current supplier
2. Alternate supplier — find another supplier with shorter lead time
3. Substitute material — use equivalent material with lower specs
4. Partial production / resequencing — produce what's possible now

Each option includes feasibility, impact, lead time, cost, and recommendation.
"""
from datetime import datetime, timedelta

from data_source import load_data, get_provider_name
from skills.delivery_risk import analyze_delivery_risk, _safe_int, _safe_float
from skills.schema import normalize_skill_response


def _days_until(due_date_str):
    """Calculate days remaining until due date."""
    try:
        due = datetime.fromisoformat(due_date_str)
        return (due - datetime.now()).days
    except (ValueError, TypeError):
        return 0


def _identify_shortage_materials(order_id, materials):
    """Find materials that are in shortage for this order."""
    order_materials = [m for m in materials if m.get("order_id") == order_id]
    shortages = []
    for m in order_materials:
        available = _safe_int(m.get("available_qty"), 0)
        required = _safe_int(m.get("required_qty"), 0)
        if available < required:
            shortage_qty = required - available
            safety_stock = _safe_int(m.get("safety_stock"), 0)
            lead_time = _safe_int(m.get("supplier_lead_time_days"), 0)
            reliability = _safe_float(m.get("supplier_reliability"), 0.5)
            unit_cost = _safe_float(m.get("unit_cost"), 0)
            effective_lead = int(lead_time / max(reliability, 0.1)) if reliability > 0 else lead_time * 2
            shortages.append({
                "material": m.get("material", "Unknown"),
                "shortage_qty": shortage_qty,
                "available_qty": available,
                "required_qty": required,
                "safety_stock": safety_stock,
                "lead_time_days": lead_time,
                "effective_lead_days": effective_lead,
                "supplier_reliability": reliability,
                "unit_cost": unit_cost,
                "below_safety_stock": available <= safety_stock,
                "status": m.get("status", "Unknown"),
            })
    return shortages


def _evaluate_emergency_reorder(shortage, order, days_left):
    """Evaluate emergency reorder from current supplier with expedited shipping."""
    effective_lead = shortage["effective_lead_days"]
    material = shortage["material"]
    shortage_qty = shortage["shortage_qty"]
    unit_cost = shortage["unit_cost"]
    reliability = shortage["supplier_reliability"]

    # Emergency reorder assumes expedited shipping cuts lead time by ~40%
    emergency_lead = int(effective_lead * 0.6)
    material_cost = shortage_qty * unit_cost
    expedite_premium = material_cost * 0.3  # 30% premium for emergency shipping
    total_cost = material_cost + expedite_premium

    can_arrive = emergency_lead <= days_left

    # High reliability suppliers more likely to deliver on time
    if reliability >= 0.85:
        feasibility = "high" if can_arrive else "medium"
    elif reliability >= 0.6:
        feasibility = "medium" if can_arrive else "low"
    else:
        feasibility = "low"

    return {
        "name": "emergency_reorder",
        "label": "緊急補貨 (Emergency Reorder)",
        "feasibility": feasibility,
        "feasibility_reason": (
            f"Current supplier reliability: {reliability:.0%}. "
            f"Emergency lead time: ~{emergency_lead}d (original: {shortage['lead_time_days']}d). "
            f"{'Can arrive before due date.' if can_arrive else 'Likely late even with expedited shipping.'}"
        ),
        "expected_impact": (
            f"Acquire {shortage_qty} units of {material} in ~{emergency_lead}d. "
            f"{'Full production recovery possible.' if can_arrive else 'Partial recovery; may need backup plan.'}"
        ),
        "lead_time_implication": f"{emergency_lead}d expedited lead time vs {shortage['lead_time_days']}d standard.",
        "cost_implication": f"${total_cost:,.0f} total (${material_cost:,.0f} material + ${expedite_premium:,.0f} expedite premium).",
        "cost_estimate": total_cost,
        "assumptions": [
            f"Supplier can prioritize emergency order",
            f"Expedited shipping available for {material}",
            f"Quality inspection can be completed within 1d",
        ],
        "blockers": [] if can_arrive else [f"Even expedited ({emergency_lead}d) exceeds {days_left}d remaining"],
        "recommended": can_arrive and reliability >= 0.7,
    }


def _evaluate_alternate_supplier(shortage, order, days_left, quotes=None):
    """Evaluate finding an alternate supplier for the shortage material."""
    material = shortage["material"]
    shortage_qty = shortage["shortage_qty"]
    unit_cost = shortage["unit_cost"]
    current_lead = shortage["lead_time_days"]
    current_reliability = shortage["supplier_reliability"]

    # Check if quotes data has alternate suppliers for this material
    alt_suppliers = []
    if quotes:
        for q in quotes:
            if q.get("material", "").lower() == material.lower():
                lt = _safe_int(q.get("lead_time_days"), current_lead)
                price = _safe_float(q.get("unit_price"), unit_cost)
                rel = _safe_float(q.get("supplier_reliability"), None)
                risk = q.get("risk_level", "medium")
                alt_suppliers.append({
                    "supplier": q.get("supplier", "Unknown"),
                    "lead_time": lt,
                    "price": price,
                    "reliability": rel if rel is not None else (0.9 if risk == "low" else 0.5),
                })

    if not alt_suppliers:
        # No quotes data — estimate based on industry average
        estimated_alt_lead = max(3, int(current_lead * 0.8))
        estimated_alt_cost = shortage_qty * unit_cost * 1.15  # 15% premium
        can_arrive = estimated_alt_lead <= days_left

        return {
            "name": "alternate_supplier",
            "label": "替代供應商 (Alternate Supplier)",
            "feasibility": "medium",
            "feasibility_reason": (
                f"No supplier comparison data available. "
                f"Estimated alternate lead time: ~{estimated_alt_lead}d. "
                f"Current supplier reliability: {current_reliability:.0%}."
            ),
            "expected_impact": (
                f"May find supplier with shorter lead time for {material}. "
                f"{'Likely feasible within timeline.' if can_arrive else 'Tight timeline for supplier qualification.'}"
            ),
            "lead_time_implication": f"Estimated {estimated_alt_lead}d vs current {current_lead}d.",
            "cost_implication": f"Est. ${estimated_alt_cost:,.0f} (potential 15% premium for new supplier).",
            "cost_estimate": estimated_alt_cost,
            "assumptions": [
                "Alternate supplier exists in vendor list",
                "Supplier qualification can be fast-tracked",
                "Material specs match current requirements",
            ],
            "blockers": [] if can_arrive else [f"New supplier qualification may exceed {days_left}d timeline"],
            "recommended": can_arrive and current_reliability < 0.8,
        }

    # Filter to suppliers faster than current lead time
    faster_suppliers = [s for s in alt_suppliers if s["lead_time"] < current_lead]
    if not faster_suppliers:
        faster_suppliers = alt_suppliers  # Use all if none are faster

    best = min(faster_suppliers, key=lambda s: s["lead_time"])
    can_arrive = best["lead_time"] <= days_left
    alt_cost = shortage_qty * best["price"]
    price_diff = best["price"] - unit_cost
    price_note = f"${price_diff:+,.0f}/unit vs current" if price_diff != 0 else "price comparable"

    return {
        "name": "alternate_supplier",
        "label": "替代供應商 (Alternate Supplier)",
        "feasibility": "high" if can_arrive and best["reliability"] >= 0.8 else ("medium" if can_arrive else "low"),
        "feasibility_reason": (
            f"Best alternate: {best['supplier']} — lead {best['lead_time']}d, "
            f"reliability {best['reliability']:.0%}. {price_note}."
        ),
        "expected_impact": (
            f"Source {shortage_qty} units of {material} from {best['supplier']} "
            f"in {best['lead_time']}d. {'On schedule.' if can_arrive else 'May miss deadline.'}"
        ),
        "lead_time_implication": f"{best['lead_time']}d vs current {current_lead}d ({current_lead - best['lead_time']:+d}d difference).",
        "cost_implication": f"${alt_cost:,.0f} total ({price_note}).",
        "cost_estimate": alt_cost,
        "assumptions": [
            f"{best['supplier']} can fulfill {shortage_qty} units",
            "Material quality equivalent to current spec",
            "PO can be issued immediately",
        ],
        "blockers": [] if can_arrive else [f"Alternate supplier lead time ({best['lead_time']}d) exceeds {days_left}d remaining"],
        "recommended": can_arrive and best["reliability"] >= current_reliability,
    }


def _evaluate_substitute_material(shortage, order, days_left):
    """Evaluate using a substitute/equivalent material."""
    material = shortage["material"]
    shortage_qty = shortage["shortage_qty"]
    unit_cost = shortage["unit_cost"]

    # Estimate: substitute material is typically 10-20% cheaper but may have
    # slightly different specs
    sub_cost = shortage_qty * unit_cost * 0.85  # 15% cheaper
    # Assume substitute is available locally or has very short lead time
    sub_lead = 2  # days

    can_use = sub_lead <= days_left

    return {
        "name": "substitute_material",
        "label": "替代物料 (Substitute Material)",
        "feasibility": "medium" if can_use else "low",
        "feasibility_reason": (
            f"Substitute material for {material} estimated available in ~{sub_lead}d. "
            f"Requires engineering approval for spec compatibility."
        ),
        "expected_impact": (
            f"Replace {material} with equivalent grade material. "
            f"{'Can be sourced immediately if approved.' if can_use else 'Approval timeline may be tight.'}"
        ),
        "lead_time_implication": f"~{sub_lead}d sourcing time vs {shortage['lead_time_days']}d for original material.",
        "cost_implication": f"Est. ${sub_cost:,.0f} (potential 15% savings vs ${unit_cost:.0f}/unit original).",
        "cost_estimate": sub_cost,
        "assumptions": [
            "Engineering approves substitute spec",
            "Customer accepts material change (if applicable)",
            "Quality testing can be completed within 1d",
            f"Substitute has equivalent mechanical properties for {order.get('product', 'product')}",
        ],
        "blockers": [
            "Engineering approval required",
            "Customer notification may be needed for material change",
        ] if order.get("customer_tier") == "VIP" else ["Engineering approval required"],
        "recommended": can_use and shortage["lead_time_days"] > days_left * 2,
    }


def _evaluate_partial_production(shortage, order, days_left, work_orders=None):
    """Evaluate partial production using available material."""
    material = shortage["material"]
    available = shortage["available_qty"]
    required = shortage["required_qty"]
    total_qty = _safe_int(order.get("quantity"), 0)

    if required <= 0 or total_qty <= 0:
        return {
            "name": "partial_production",
            "label": "部分生產 (Partial Production)",
            "feasibility": "low",
            "feasibility_reason": "Cannot calculate production ratio from available data.",
            "expected_impact": "N/A",
            "lead_time_implication": "N/A",
            "cost_implication": "N/A",
            "cost_estimate": None,
            "assumptions": [],
            "blockers": ["Insufficient data to assess partial production ratio"],
            "recommended": False,
        }

    # Material availability ratio
    material_ratio = available / required
    partial_units = int(total_qty * material_ratio)

    # Check WO structure for resequencing potential
    resequencing_possible = False
    if work_orders:
        order_wos = [wo for wo in work_orders if wo.get("order_id") == order.get("order_id")]
        # If there are multiple WOs, some may be prioritized
        resequencing_possible = len(order_wos) > 1

    penalty = _safe_float(order.get("penalty_per_day"), 0)
    penalty_savings = penalty * days_left if partial_units > 0 else 0

    return {
        "name": "partial_production",
        "label": "部分生產 (Partial Production)",
        "feasibility": "high" if material_ratio >= 0.5 else "medium",
        "feasibility_reason": (
            f"Material available for ~{material_ratio:.0%} ({partial_units}/{total_qty} units) "
            f"of order quantity. "
            f"{'Enough for meaningful partial shipment.' if material_ratio >= 0.5 else 'Limited production volume.'}"
        ),
        "expected_impact": (
            f"Produce {partial_units} units now with available {material}. "
            f"Remaining {total_qty - partial_units} units delayed. "
            f"Reduces penalty exposure by est. ${penalty_savings:,.0f}."
        ),
        "lead_time_implication": (
            f"Partial units can ship on schedule. "
            f"Remaining {total_qty - partial_units} units delayed by ~{shortage['effective_lead_days']}d "
            f"(material reorder lead time)."
        ),
        "cost_implication": (
            f"Penalty savings: est. ${penalty_savings:,.0f}. "
            f"Additional logistics cost for second shipment: ~$1,000-$2,000."
        ),
        "cost_estimate": 1500,
        "assumptions": [
            f"Customer accepts {partial_units} unit initial delivery",
            f"Remaining units delivered after material arrives (~{shortage['effective_lead_days']}d)",
            "Quality validation per batch required",
        ] + (["Resequencing WOs to prioritize partial batch"] if resequencing_possible else []),
        "blockers": [],
        "recommended": material_ratio >= 0.3 and penalty > 1000,
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


def handle_material_shortage_recovery(order_ids, data_dir, query=None):
    """
    Generate material shortage recovery options for an order.

    Reuses delivery-risk-analysis for context, then evaluates 4 recovery
    strategies specifically targeting material shortages.
    """
    if not order_ids:
        return {"error": "Order ID is required for material shortage recovery."}

    order_id = order_ids[0]

    # Reuse delivery risk analysis
    delivery_report = analyze_delivery_risk(order_id, data_dir)
    if "error" in delivery_report:
        return delivery_report

    # Load data via provider layer
    orders = load_data(data_dir, "orders.json")
    materials = load_data(data_dir, "materials.json")
    work_orders = load_data(data_dir, "work_orders.json")

    order = next((o for o in orders if o.get("order_id") == order_id), None)
    if not order:
        return {"error": f"Order {order_id} not found"}

    # Identify shortage materials
    shortages = _identify_shortage_materials(order_id, materials)

    if not shortages:
        return normalize_skill_response("material-shortage-recovery", {
            "order_id": order_id,
            "customer": order.get("customer"),
            "decision": "no_shortage",
            "confidence": "High",
            "blockers": ["No material shortages detected for this order."],
            "owner": "Procurement Team",
            "eta": order.get("due_date"),
            "next_action": "No material shortage recovery needed. Monitor inventory levels proactively.",
            "escalation": "None",
            "shortages": [],
            "options": [],
            "recovery_summary": {
                "total_shortages": 0,
                "total_evaluated": 0,
                "recommended_count": 0,
                "top_recommendation": "None — all materials sufficient",
            },
            "trace": [
                "loaded order and materials via provider layer",
                "no material shortages detected",
                "recovery plan not required",
            ],
        })

    # Try to load quotes for alternate supplier evaluation
    try:
        quotes = load_data(data_dir, "quotes.json")
    except Exception:
        quotes = None

    days_left = _days_until(order.get("due_date", ""))

    # For each shortage material, evaluate options (focus on primary shortage)
    primary = shortages[0]
    options = [
        _evaluate_emergency_reorder(primary, order, days_left),
        _evaluate_alternate_supplier(primary, order, days_left, quotes),
        _evaluate_substitute_material(primary, order, days_left),
        _evaluate_partial_production(primary, order, days_left, work_orders),
    ]

    ranked = _compute_ranked_recommendation(options)

    recommended = [opt for opt in ranked if opt["recommended"]]
    if recommended:
        summary_text = (
            f"Top recommendation for {primary['material']} shortage: "
            f"{recommended[0]['label']} — {recommended[0]['expected_impact']}"
        )
    else:
        summary_text = (
            f"No strongly recommended recovery option for {primary['material']}. "
            f"Review feasibility details for manual assessment. "
            f"Consider escalation if {days_left}d remaining is critical."
        )

    # Calculate total shortage cost
    total_shortage_cost = sum(s["shortage_qty"] * s["unit_cost"] for s in shortages)
    total_shortage_units = sum(s["shortage_qty"] for s in shortages)

    raw_data = {
        "order_id": order_id,
        "customer": order.get("customer"),
        "decision": "shortage_detected",
        "confidence": delivery_report.get("confidence", "High"),
        "blockers": [
            f"{s['material']}: {s['available_qty']}/{s['required_qty']} available "
            f"(shortage: {s['shortage_qty']} units, lead time: {s['lead_time_days']}d)"
            for s in shortages
        ],
        "owner": "Procurement Manager",
        "eta": order.get("due_date"),
        "next_action": summary_text,
        "escalation": delivery_report.get("escalation", "None"),
        "days_left": days_left,
        "shortages": [
            {
                "material": s["material"],
                "shortage_qty": s["shortage_qty"],
                "available_qty": s["available_qty"],
                "required_qty": s["required_qty"],
                "lead_time_days": s["lead_time_days"],
                "effective_lead_days": s["effective_lead_days"],
                "supplier_reliability": s["supplier_reliability"],
                "unit_cost": s["unit_cost"],
                "below_safety_stock": s["below_safety_stock"],
            }
            for s in shortages
        ],
        "options": ranked,
        "recovery_summary": {
            "total_shortages": len(shortages),
            "total_shortage_units": total_shortage_units,
            "total_shortage_cost": total_shortage_cost,
            "total_evaluated": len(options),
            "recommended_count": len(recommended),
            "top_recommendation": recommended[0]["label"] if recommended else "None",
            "top_cost_estimate": recommended[0]["cost_estimate"] if recommended else None,
        },
        "trace": [
            f"loaded data via provider layer ({get_provider_name()})",
            f"identified {len(shortages)} shortage material(s)",
            "evaluated 4 recovery options (emergency_reorder, alternate_supplier, substitute_material, partial_production)",
            "ranked options by feasibility and recommendation score",
        ],
    }

    return normalize_skill_response("material-shortage-recovery", raw_data)
