from skills.delivery_risk import analyze_delivery_risk


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
    customer = delivery_report["customer"]
    product = delivery_report["product"]
    order_id = delivery_report["order_id"]
    due_date = delivery_report["due_date"]
    decision = delivery_report["decision"]

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
        for blocker in delivery_report["blockers"]
        if not str(blocker).startswith("No critical blockers")
    ]

    return {
        "order_id": delivery_report["order_id"],
        "customer": delivery_report["customer"],
        "product": delivery_report["product"],
        "due_date": delivery_report["due_date"],
        "decision": delivery_report["decision"],
        "confidence": delivery_report["confidence"],
        "shipment_status": _status_label(delivery_report["decision"]),
        "key_message": _key_message(
            delivery_report["decision"], delivery_report["due_date"]
        ),
        "internal_guidance": delivery_report["recommendation"],
        "risk_summary": actionable_blockers[:3],
        "customer_reply_draft": _draft_customer_message(delivery_report),
        "trace": delivery_report["trace"] + ["generated sales response draft"],
    }
