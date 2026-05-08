from skills.delivery_risk import analyze_delivery_risk
from skills.schema import normalize_skill_response


def _status_label(decision):
    if decision == "can_ship_on_time":
        return "on_track"
    if decision == "at_risk":
        return "pending_confirmation"
    return "recovery_in_progress"


def _key_message(decision, due_date):
    if decision == "can_ship_on_time":
        return f"We are on track to meet the committed delivery date of {due_date}."
    if decision == "at_risk":
        return (
            f"We are reviewing the latest production status for the {due_date} commitment "
            "and will confirm shortly."
        )
    return (
        f"Current production constraints may affect the committed delivery date of {due_date}. "
        "We are executing recovery actions now."
    )


def _draft_customer_message(delivery_report):
    customer = delivery_report.get("customer", "Customer")
    product = delivery_report.get("details", {}).get("product", delivery_report.get("product", "your product"))
    order_id = delivery_report.get("order_id", "N/A")
    due_date = delivery_report.get("eta", delivery_report.get("due_date", "the committed date"))
    decision = delivery_report.get("decision", "unknown")

    intro = f"Dear {customer},"
    if decision == "can_ship_on_time":
        body_lines = [
            f"Regarding order {order_id} for {product}, production is progressing as planned.",
            f"We remain on schedule for the committed delivery date of {due_date}.",
            "We will continue to monitor execution closely and keep you posted if anything changes.",
        ]
    elif decision == "at_risk":
        body_lines = [
            f"Regarding order {order_id} for {product}, we are reviewing the latest production status.",
            f"The current target delivery date remains {due_date}, and we are validating the recovery plan now.",
            "We will send you a firm update as soon as the production review is complete.",
        ]
    else:
        body_lines = [
            f"Regarding order {order_id} for {product}, we have identified production constraints affecting execution.",
            f"As a result, the committed delivery date of {due_date} may be impacted.",
            "Our team is working on recovery actions now and will provide an updated delivery commitment shortly.",
        ]

    return "\n\n".join([intro, "\n".join(body_lines), "Best regards,\nSales Team"])


def handle_sales_response_draft(order_ids, data_dir, query=None):
    """
    Generate a customer-facing sales reply draft based on delivery risk status.
    """
    if not order_ids:
        return {"error": "Order ID is required for sales response draft."}

    delivery_report = analyze_delivery_risk(order_ids[0], data_dir)
    if "error" in delivery_report:
        return delivery_report

    actionable_blockers = [
        blocker
        for blocker in delivery_report.get("blockers", [])
        if not str(blocker).startswith("No critical blockers")
    ]

    raw_data = {
        "order_id": delivery_report.get("order_id"),
        "customer": delivery_report.get("customer"),
        "product": delivery_report.get("product"),
        "decision": delivery_report.get("decision"),
        "confidence": delivery_report.get("confidence"),
        "shipment_status": _status_label(delivery_report.get("decision")),
        "key_message": _key_message(
            delivery_report.get("decision"), delivery_report.get("due_date")
        ),
        "internal_guidance": delivery_report.get("recommendation"),
        "risk_summary": actionable_blockers[:3],
        "customer_reply_draft": _draft_customer_message(delivery_report),
        "trace": delivery_report.get("trace", []) + ["generated sales response draft"],
        "owner": "Sales Team",
        "eta": delivery_report.get("due_date"),
        "next_action": delivery_report.get("recommendation"),
        "escalation": delivery_report.get("escalation"),
    }
    
    return normalize_skill_response("sales-response-draft", raw_data)
