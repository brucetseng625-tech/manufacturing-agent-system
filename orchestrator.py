import json
import os
import re
from data_loader import load_json_or_csv
from data_validator import validate_dataset
from skills.registry import get_registry

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

def validate_data_dir(data_dir, data_files=None):
    """Pre-flight check: validate data consistency."""
    errors = []
    schema_items = SCHEMA_MAP.items()
    if data_files is not None:
        scoped_files = {}
        for filename in data_files:
            base_name = os.path.splitext(filename)[0]
            scoped_files[f"{base_name}.json"] = base_name
            scoped_files[f"{base_name}.csv"] = base_name
        schema_items = scoped_files.items()

    for filename, schema_key in schema_items:
        filepath = os.path.join(data_dir, filename)
        if os.path.exists(filepath):
            data = load_json_or_csv(data_dir, filename)
            errs = validate_dataset(schema_key, data)
            errors.extend(errs)
    return errors

def route_query(query, data_dir):
    """
    Main orchestrator logic using Skill Registry.
    1. Validates data.
    2. Extracts order IDs.
    3. Matches skill via registry.
    4. Dispatches to skill.
    5. Returns result or error.
    """
    order_ids = extract_order_ids(query)
    
    response_base = {
        "query": query,
        "data_dir": data_dir,
        "order_ids": order_ids,
    }
    
    # 1. Skill/Team Matching via Registry
    matched_team = get_registry().match_team(query, order_ids)
    
    # If team matched, execute team workflow
    if matched_team:
        if matched_team.get("requires_order_id") and not order_ids:
            return {
                **response_base,
                "status": "error",
                "type": "missing_order_id",
                "details": f"Order ID is required for {matched_team['name']} team workflow."
            }
        try:
            team_result = get_registry().execute_team(matched_team, order_ids, data_dir, query)
            return {
                **response_base,
                "status": "success",
                "intent": matched_team["intent"],
                "skill": f"team:{matched_team['name']}",
                "data": team_result,
                "is_team": True
            }
        except Exception as e:
            return {
                **response_base,
                "status": "error",
                "type": "team_error",
                "details": str(e)
            }
    
    matched_skill = get_registry().match_skill(query, order_ids)
    
    if matched_skill is None:
        return {
            **response_base,
            "status": "error",
            "type": "unknown_intent",
            "details": "No skill matched your query. Try keywords like '準時', '出貨', '衝突', or provide multiple order IDs."
        }
    
    # Check if skill requires order ID but none provided
    if matched_skill.get("requires_order_id") and not order_ids:
        return {
            **response_base,
            "status": "error",
            "type": "missing_order_id",
            "details": f"Order ID is required for {matched_skill['name']} skill."
        }

    # 2. Validation scoped to the matched skill.
    validation_errors = validate_data_dir(data_dir, matched_skill.get("data_files"))
    if validation_errors:
        return {
            **response_base,
            "status": "error",
            "type": "validation_failed",
            "details": validation_errors
        }
    
    # 3. Execute Skill
    try:
        result_data = get_registry().execute(matched_skill, order_ids, data_dir, query)
    except Exception as e:
        return {
            **response_base,
            "status": "error",
            "type": "skill_error",
            "details": str(e)
        }
    
    # 5. Return Success
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
        "intent": matched_skill["intent"],
        "skill": matched_skill["name"],
        "data": result_data
    }
