
import json
import os
import re
from data_loader import load_json_or_csv
from data_validator import validate_dataset
from skills.delivery_risk import analyze_delivery_risk
from skills.schedule_conflict_check import check_schedule_conflict

SCHEMA_MAP = {
    "orders.json": "orders", "orders.csv": "orders",
    "work_orders.json": "work_orders", "work_orders.csv": "work_orders",
    "materials.json": "materials", "materials.csv": "materials",
    "machines.json": "machines", "machines.csv": "machines",
    "operators.json": "operators", "operators.csv": "operators",
    "schedule.json": "schedule", "schedule.csv": "schedule"
}

def extract_order_ids(query):
    match = re.findall(r"\bORD-[A-Z0-9-]+\b", query, re.IGNORECASE)
    return [m.upper() for m in match]

def validate_data_dir(data_dir):
    """Pre-flight check: validate data consistency."""
    errors = []
    for filename, schema_key in SCHEMA_MAP.items():
        filepath = os.path.join(data_dir, filename)
        if os.path.exists(filepath):
            data = load_json_or_csv(data_dir, filename)
            errs = validate_dataset(schema_key, data)
            errors.extend(errs)
    return errors

def route_query(query, data_dir):
    """
    Main orchestrator logic.
    1. Validates data.
    2. Extracts order IDs.
    3. Classifies intent.
    4. Dispatches to skill.
    5. Returns result or error.
    """
    order_ids = extract_order_ids(query)
    if not order_ids:
        order_ids = ["ORD-1001"]

    response_base = {
        "query": query,
        "data_dir": data_dir,
        "order_ids": order_ids,
    }

    # 1. Validation
    validation_errors = validate_data_dir(data_dir)
    if validation_errors:
        return {
            **response_base,
            "status": "error",
            "type": "validation_failed",
            "details": validation_errors
        }

    # 3. Routing
    if "衝突" in query or "conflict" in query.lower() or len(order_ids) > 1:
        skill_name = "schedule-conflict-check"
        result_data = check_schedule_conflict(order_ids, data_dir)
        return {
            **response_base,
            "status": "success",
            "intent": "schedule_conflict_check",
            "skill": skill_name,
            "data": result_data
        }
    elif "準時" in query or "出貨" in query or "delivery" in query.lower():
        skill_name = "delivery-risk-analysis"
        result_data = analyze_delivery_risk(order_ids[0], data_dir)
        if "error" in result_data:
            return {
                **response_base,
                "status": "error",
                "type": "skill_error",
                "details": result_data["error"]
            }
        return {
            **response_base,
            "status": "success",
            "intent": "delivery_risk_analysis",
            "skill": skill_name,
            "data": result_data
        }
    else:
        return {
            **response_base,
            "status": "error",
            "type": "unknown_intent",
            "details": "MVP only supports delivery risk and schedule conflict queries."
        }
