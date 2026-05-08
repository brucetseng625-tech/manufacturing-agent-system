
import datetime

SCHEMAS = {
    "orders": {
        "required": ["order_id", "customer", "product", "quantity", "due_date", "priority"],
        "types": {"quantity": int, "penalty_per_day": float, "expedite_cost": float}
    },
    "work_orders": {
        "required": ["wo_id", "order_id", "status", "machine_id", "progress_percent", "estimated_completion"],
        "types": {"progress_percent": int}
    },
    "materials": {
        "required": ["order_id", "material", "required_qty", "available_qty", "status"],
        "types": {"required_qty": int, "available_qty": int, "safety_stock": int, "supplier_lead_time_days": int, "unit_cost": float}
    },
    "machines": {
        "required": ["machine_id", "status", "load_percent", "next_maintenance"],
        "types": {"load_percent": int, "max_capacity_percent": int}
    },
    "operators": {
        "required": ["operator_id", "skill", "shift", "status"],
        "types": {}
    },
    "schedule": {
        "required": ["order_id", "machine_id", "start", "end"],
        "types": {}
    },
    "quotes": {
        "required": ["quote_id", "material", "supplier", "unit_price", "currency", "lead_time_days", "moq", "quality_rating", "risk_level", "valid_until"],
        "types": {"unit_price": float, "lead_time_days": int, "moq": int, "quality_rating": float}
    }
}

def validate_dataset(name, data):
    """
    Validate a list of dicts against the schema.
    Returns a list of error messages. Empty list means valid.
    """
    errors = []
    if name not in SCHEMAS:
        return [f"Unknown dataset type: {name}"]
    
    schema = SCHEMAS[name]
    
    if not isinstance(data, list):
        return [f"Dataset '{name}' must be a list of records."]
        
    if len(data) == 0:
        errors.append(f"Dataset '{name}' is empty. This might be intentional but verify if data is expected.")
        
    for i, record in enumerate(data):
        if not isinstance(record, dict):
            errors.append(f"{name}[{i}]: Record is not a dictionary.")
            continue
            
        # Check required fields
        for field in schema["required"]:
            if field not in record:
                errors.append(f"{name}[{i}]: Missing required field '{field}'.")
            elif record[field] is None or (isinstance(record[field], str) and record[field].strip() == ""):
                errors.append(f"{name}[{i}]: Field '{field}' is empty/null.")
                
        # Check types
        for field, expected_type in schema["types"].items():
            if field in record and record[field] is not None:
                if not isinstance(record[field], expected_type):
                    errors.append(f"{name}[{i}]: Field '{field}' expected {expected_type.__name__}, got {type(record[field]).__name__}.")
                    
        # Check Date/Datetime formats (String validation)
        date_fields = []
        if name == "orders": date_fields = ["due_date"]
        elif name == "work_orders": date_fields = ["estimated_completion"]
        elif name == "machines": date_fields = ["next_maintenance"]
        elif name == "schedule": date_fields = ["start", "end"]
        elif name == "quotes": date_fields = ["valid_until"]
        
        for field in date_fields:
            if field in record and isinstance(record[field], str):
                try:
                    # Try parsing ISO format
                    datetime.datetime.fromisoformat(record[field])
                except ValueError:
                    errors.append(f"{name}[{i}]: Field '{field}' invalid date format ('{record[field]}').")
                    
    return errors

def validate_all_datasets(data_dict):
    """
    Validate all datasets in a dictionary {name: data_list}.
    Returns (is_valid, list_of_all_errors).
    """
    all_errors = []
    for name, data in data_dict.items():
        # Map file names to schema names (e.g. "orders.json" -> "orders")
        clean_name = name.replace(".json", "").replace(".csv", "")
        if clean_name in SCHEMAS:
            errs = validate_dataset(clean_name, data)
            all_errors.extend(errs)
            
    if all_errors:
        return False, all_errors
    return True, []
