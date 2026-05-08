"""
Supplier Follow-up Draft Skill

Generates supplier-facing communication drafts for material shortage,
expedite, alternate supplier, and lead time confirmation scenarios.

Unlike sales-response-draft (customer-facing), this skill targets suppliers
and procurement workflows.

Supported draft types:
1. emergency_reorder — Expedited purchase follow-up for current supplier
2. alternate_supplier_inquiry — RFQ to alternate suppliers
3. lead_time_confirmation — Confirm/accelerate delivery timeline
4. material_availability — Check stock and availability status
"""
from datetime import datetime

from data_source import load_data, get_provider_name
from skills.delivery_risk import analyze_delivery_risk, _safe_int, _safe_float
from skills.material_shortage_recovery import handle_material_shortage_recovery
from skills.schema import normalize_skill_response


def _days_until(due_date_str):
    """Calculate days remaining until due date."""
    try:
        due = datetime.fromisoformat(due_date_str)
        return (due - datetime.now()).days
    except (ValueError, TypeError):
        return 0


def _detect_draft_context(order_id, order, materials, quotes):
    """Determine what draft context is most relevant based on data."""
    order_materials = [m for m in materials if m.get("order_id") == order_id]
    shortages = [m for m in order_materials
                 if _safe_int(m.get("available_qty"), 0) < _safe_int(m.get("required_qty"), 0)]

    context = {
        "has_shortage": bool(shortages),
        "shortage_materials": shortages,
        "has_quotes": bool(quotes),
        "quote_suppliers": set(),
        "quote_materials": set(),
    }

    if quotes:
        for q in quotes:
            context["quote_suppliers"].add(q.get("supplier", "Unknown"))
            context["quote_materials"].add(q.get("material", "Unknown"))

    return context


def _generate_emergency_reorder_draft(order, shortage, order_id, days_left):
    """Generate draft for emergency reorder follow-up with current supplier."""
    material = shortage.get("material", "the material")
    shortage_qty = shortage.get("shortage_qty", 0)
    required_qty = shortage.get("required_qty", 0)
    lead_time = shortage.get("lead_time_days", 0)
    reliability = shortage.get("supplier_reliability", 0)
    unit_cost = shortage.get("unit_cost", 0)
    total_cost = shortage_qty * unit_cost

    subject = f"URGENT: Emergency Reorder Request - {material} ({shortage_qty} units)"

    key_asks = [
        f"Confirm immediate availability of {shortage_qty} units of {material}",
        f"Request expedited shipping to deliver within {days_left} days (due date)",
        f"Confirm unit price and any expedite premium applicable",
        f"Provide estimated ship date and tracking information upon confirmation",
    ]

    body = (
        f"Dear [Supplier Name],\n\n"
        f"We have an urgent production requirement for {material} and need to "
        f"place an emergency order for {shortage_qty} units.\n\n"
        f"Original requirement: {required_qty} units total, currently short {shortage_qty} units.\n"
        f"Required delivery: within {days_left} days (due: {order.get('due_date', 'N/A')}).\n"
        f"Estimated order value: ${total_cost:,.0f} (at ${unit_cost:.0f}/unit).\n\n"
        f"Please confirm the following as soon as possible:\n"
        f"1. Current stock availability for {shortage_qty} units of {material}\n"
        f"2. Earliest possible ship date with expedited shipping\n"
        f"3. Any expedite premium or price adjustment applicable\n"
        f"4. Updated lead time commitment\n\n"
        f"This is a time-critical request. We appreciate your immediate attention "
        f"and look forward to your prompt response.\n\n"
        f"Best regards,\n"
        f"Procurement Team\n"
        f"[Company Name]\n"
        f"[Contact Information]"
    )

    return {
        "draft_type": "emergency_reorder",
        "label": "緊急補貨跟進 (Emergency Reorder Follow-up)",
        "target_supplier": "Current supplier (per purchase record)",
        "subject": subject,
        "key_asks": key_asks,
        "urgency_level": "critical",
        "urgency_reason": f"Shortage of {shortage_qty} units, only {days_left}d until due date.",
        "reply_draft": body,
        "recommended": days_left <= lead_time,
        "context": {
            "material": material,
            "shortage_qty": shortage_qty,
            "required_qty": required_qty,
            "lead_time_days": lead_time,
            "supplier_reliability": reliability,
            "estimated_cost": total_cost,
        },
    }


def _generate_alternate_supplier_draft(order, context, order_id, days_left):
    """Generate RFQ draft for alternate supplier inquiry."""
    quote_suppliers = context.get("quote_suppliers", set())
    quote_materials = context.get("quote_materials", set())

    if not quote_suppliers:
        return None  # Can't generate without supplier data

    # Pick a representative material from shortage context
    shortage_materials = context.get("shortage_materials", [])
    target_material = shortage_materials[0].get("material", "requested material") if shortage_materials else None

    if not target_material:
        return None

    subject = f"RFQ: {target_material} - Urgent Production Requirement"

    key_asks = [
        f"Provide quotation for {target_material} (quantity to be confirmed)",
        f"Confirm standard and expedited lead times",
        f"Share material specifications and quality certifications",
        f"Indicate MOQ and pricing tiers",
        f"Confirm payment terms and delivery options",
    ]

    body = (
        f"Dear [Supplier Name],\n\n"
        f"We are currently evaluating suppliers for {target_material} to support "
        f"an upcoming production requirement.\n\n"
        f"We understand you may be able to supply this material and would like "
        f"to request a quotation with the following details:\n\n"
        f"1. Material specifications and grade confirmation\n"
        f"2. Available quantities and MOQ\n"
        f"3. Standard lead time and expedited options\n"
        f"4. Unit pricing (volume discounts if applicable)\n"
        f"5. Quality certifications and test reports\n"
        f"6. Payment terms and delivery options\n\n"
        f"This is an active sourcing initiative. We will review all submissions "
        f"promptly and contact qualified suppliers for samples or further discussion.\n\n"
        f"Please submit your quotation by [date]. We look forward to the "
        f"possibility of establishing a business relationship.\n\n"
        f"Best regards,\n"
        f"Procurement Team\n"
        f"[Company Name]\n"
        f"[Contact Information]"
    )

    return {
        "draft_type": "alternate_supplier_inquiry",
        "label": "替代供應商詢價 (Alternate Supplier RFQ)",
        "target_supplier": f"Alternate suppliers from vendor list ({', '.join(list(quote_suppliers)[:2])}{'...' if len(quote_suppliers) > 2 else ''})",
        "subject": subject,
        "key_asks": key_asks,
        "urgency_level": "high",
        "urgency_reason": f"Active sourcing for {target_material}. {len(quote_suppliers)} potential supplier(s) identified.",
        "reply_draft": body,
        "recommended": True,
        "context": {
            "material": target_material,
            "potential_suppliers": list(quote_suppliers),
            "materials_in_quotes": list(quote_materials),
        },
    }


def _generate_lead_time_confirmation_draft(order, shortage, order_id, days_left):
    """Generate draft to confirm or accelerate delivery timeline."""
    material = shortage.get("material", "the material")
    lead_time = shortage.get("lead_time_days", 0)
    effective_lead = shortage.get("effective_lead_days", lead_time)
    reliability = shortage.get("supplier_reliability", 0)

    subject = f"Lead Time Confirmation Request - {material} Order"

    key_asks = [
        f"Confirm current lead time for {material} (stated: {lead_time} days)",
        f"Verify if expedited delivery within {days_left} days is possible",
        f"Confirm reliability-adjusted delivery timeline",
        f"Provide production schedule and committed ship date",
    ]

    body = (
        f"Dear [Supplier Name],\n\n"
        f"We are writing to confirm the delivery timeline for our pending "
        f"order of {material}.\n\n"
        f"Current stated lead time: {lead_time} days\n"
        f"Effective lead time (reliability-adjusted): ~{effective_lead} days\n"
        f"Our required delivery: within {days_left} days\n\n"
        f"Please confirm:\n"
        f"1. Current production status and estimated completion date\n"
        f"2. Earliest possible ship date\n"
        f"3. Whether expedited shipping can meet our {days_left}-day requirement\n"
        f"4. Any factors that may affect the current timeline\n\n"
        f"Timely confirmation is critical for our production planning. "
        f"We appreciate your prompt response.\n\n"
        f"Best regards,\n"
        f"Procurement Team\n"
        f"[Company Name]\n"
        f"[Contact Information]"
    )

    return {
        "draft_type": "lead_time_confirmation",
        "label": "交期確認 (Lead Time Confirmation)",
        "target_supplier": "Current supplier (per purchase order)",
        "subject": subject,
        "key_asks": key_asks,
        "urgency_level": "high" if days_left < effective_lead else "medium",
        "urgency_reason": (
            f"Effective lead time ({effective_lead}d) {'exceeds' if days_left < effective_lead else 'within'} "
            f"remaining time ({days_left}d)."
        ),
        "reply_draft": body,
        "recommended": days_left < effective_lead,
        "context": {
            "material": material,
            "stated_lead_time": lead_time,
            "effective_lead_time": effective_lead,
            "supplier_reliability": reliability,
        },
    }


def _generate_material_availability_draft(order, shortage, order_id, days_left):
    """Generate draft to check material availability status."""
    material = shortage.get("material", "the material")
    available = shortage.get("available_qty", 0)
    required = shortage.get("required_qty", 0)
    safety_stock = shortage.get("safety_stock", 0)
    below_safety = shortage.get("below_safety_stock", False)

    subject = f"Material Availability Check - {material}"

    key_asks = [
        f"Confirm current stock level for {material}",
        f"Verify if {required - available} additional units can be sourced",
        f"Check if safety stock ({safety_stock} units) can be temporarily allocated",
        f"Provide next available replenishment date",
    ]

    body = (
        f"Dear [Supplier Name] / [Warehouse Team],\n\n"
        f"We are checking the availability status of {material} for "
        f"order {order_id}.\n\n"
        f"Current status:\n"
        f"  Required: {required} units\n"
        f"  Available: {available} units\n"
        f"  Shortage: {required - available} units\n"
        f"{'  WARNING: Below safety stock level (' + str(safety_stock) + ' units)' if below_safety else ''}\n\n"
        f"Please confirm:\n"
        f"1. Current on-hand quantity of {material}\n"
        f"2. Any incoming shipments and expected arrival dates\n"
        f"3. Possibility of allocating safety stock for this order\n"
        f"4. Next available replenishment timeline\n\n"
        f"Your prompt response will help us finalize our production schedule.\n\n"
        f"Best regards,\n"
        f"Procurement Team\n"
        f"[Company Name]\n"
        f"[Contact Information]"
    )

    return {
        "draft_type": "material_availability",
        "label": "物料庫存確認 (Material Availability Check)",
        "target_supplier": "Internal warehouse / Current supplier",
        "subject": subject,
        "key_asks": key_asks,
        "urgency_level": "medium" if available > 0 else "high",
        "urgency_reason": f"{available}/{required} units available. {'Below safety stock.' if below_safety else ''}",
        "reply_draft": body,
        "recommended": True,
        "context": {
            "material": material,
            "available_qty": available,
            "required_qty": required,
            "safety_stock": safety_stock,
            "below_safety_stock": below_safety,
        },
    }


def handle_supplier_followup_draft(order_ids, data_dir, query=None):
    """
    Generate supplier follow-up drafts based on shortage/quote context.

    Produces multiple draft types and ranks them by relevance and urgency.
    """
    if not order_ids:
        return {"error": "Order ID is required for supplier follow-up draft."}

    order_id = order_ids[0]

    # Load data via provider layer
    orders = load_data(data_dir, "orders.json")
    materials = load_data(data_dir, "materials.json")

    order = next((o for o in orders if o.get("order_id") == order_id), None)
    if not order:
        return {"error": f"Order {order_id} not found"}

    # Load quotes for alternate supplier context (safe fallback)
    try:
        quotes = load_data(data_dir, "quotes.json")
    except Exception:
        quotes = None

    days_left = _days_until(order.get("due_date", ""))

    # Detect context
    context = _detect_draft_context(order_id, order, materials, quotes)

    # Identify primary shortage material
    shortage = None
    if context["shortage_materials"]:
        s = context["shortage_materials"][0]
        shortage = {
            "material": s.get("material", "Unknown"),
            "shortage_qty": _safe_int(s.get("required_qty"), 0) - _safe_int(s.get("available_qty"), 0),
            "available_qty": _safe_int(s.get("available_qty"), 0),
            "required_qty": _safe_int(s.get("required_qty"), 0),
            "lead_time_days": _safe_int(s.get("supplier_lead_time_days"), 0),
            "effective_lead_days": int(
                _safe_int(s.get("supplier_lead_time_days"), 0) /
                max(_safe_float(s.get("supplier_reliability"), 0.5), 0.1)
            ),
            "supplier_reliability": _safe_float(s.get("supplier_reliability"), 0.5),
            "unit_cost": _safe_float(s.get("unit_cost"), 0),
            "safety_stock": _safe_int(s.get("safety_stock"), 0),
            "below_safety_stock": _safe_int(s.get("available_qty"), 0) <= _safe_int(s.get("safety_stock"), 0),
        }

    # Generate drafts based on context
    drafts = []

    if shortage:
        drafts.append(_generate_emergency_reorder_draft(order, shortage, order_id, days_left))
        drafts.append(_generate_lead_time_confirmation_draft(order, shortage, order_id, days_left))
        drafts.append(_generate_material_availability_draft(order, shortage, order_id, days_left))

    # Alternate supplier RFQ (requires quotes data)
    if context["has_quotes"] and shortage:
        alt_draft = _generate_alternate_supplier_draft(order, context, order_id, days_left)
        if alt_draft:
            drafts.append(alt_draft)

    # Filter out None drafts
    drafts = [d for d in drafts if d is not None]

    # Rank by urgency and recommendation
    urgency_priority = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    drafts.sort(key=lambda d: (
        urgency_priority.get(d["urgency_level"], 0) * -1,
        -1 if d["recommended"] else 0,
    ))

    if not drafts:
        # No shortage context — safe fallback
        return normalize_skill_response("supplier-followup-draft", {
            "order_id": order_id,
            "customer": order.get("customer"),
            "decision": "no_followup_needed",
            "confidence": "High",
            "blockers": ["No material shortage or supplier follow-up context detected."],
            "owner": "Procurement Team",
            "eta": order.get("due_date"),
            "next_action": "No supplier follow-up required at this time. Monitor inventory levels proactively.",
            "escalation": "None",
            "drafts": [],
            "draft_summary": {
                "total_drafts": 0,
                "recommended_count": 0,
                "top_recommendation": "None — no shortage context",
                "target_suppliers": [],
            },
            "trace": [
                f"loaded data via provider layer ({get_provider_name()})",
                "analyzed shortage and supplier context",
                "no follow-up drafts generated — materials sufficient",
            ],
        })

    recommended = [d for d in drafts if d.get("recommended")]
    top = recommended[0] if recommended else drafts[0]

    summary_text = (
        f"Top recommendation: {top['label']} — "
        f"Target: {top['target_supplier']}. "
        f"Urgency: {top['urgency_level']}. {top['urgency_reason']}"
    )

    blocker_lines = []
    for s in context["shortage_materials"]:
        available_qty = _safe_int(s.get("available_qty"), 0)
        required_qty = _safe_int(s.get("required_qty"), 0)
        shortage_qty = required_qty - available_qty
        blocker_lines.append(
            f"{s.get('material', 'Unknown')}: {available_qty}/{required_qty} available "
            f"(shortage: {shortage_qty} units)"
        )

    raw_data = {
        "order_id": order_id,
        "customer": order.get("customer"),
        "decision": "followup_generated",
        "confidence": "High" if context["has_shortage"] else "Medium",
        "blockers": blocker_lines if blocker_lines else ["No critical blockers."],
        "owner": "Procurement Manager",
        "eta": order.get("due_date"),
        "next_action": summary_text,
        "escalation": "None",
        "days_left": days_left,
        "drafts": [
            {
                "draft_type": d["draft_type"],
                "label": d["label"],
                "target_supplier": d["target_supplier"],
                "subject": d["subject"],
                "key_asks": d["key_asks"],
                "urgency_level": d["urgency_level"],
                "urgency_reason": d["urgency_reason"],
                "recommended": d["recommended"],
                "context": d.get("context", {}),
            }
            for d in drafts
        ],
        "reply_draft": top["reply_draft"],
        "draft_summary": {
            "total_drafts": len(drafts),
            "recommended_count": len(recommended),
            "top_recommendation": top["label"],
            "top_urgency": top["urgency_level"],
            "target_suppliers": list(set(d["target_supplier"] for d in drafts)),
        },
        "trace": [
            f"loaded data via provider layer ({get_provider_name()})",
            f"analyzed shortage context ({len(context['shortage_materials'])} shortage material(s))",
            f"generated {len(drafts)} follow-up draft(s)",
            "ranked drafts by urgency and recommendation",
        ],
    }

    return normalize_skill_response("supplier-followup-draft", raw_data)
