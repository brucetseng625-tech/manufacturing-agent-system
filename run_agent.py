
import json
import os
import re
import sys
import argparse
from skills.delivery_risk import analyze_delivery_risk
from skills.schedule_conflict_check import check_schedule_conflict
from data_loader import load_json_or_csv
from data_validator import validate_dataset


def extract_order_ids(query):
    match = re.findall(r"\bORD-[A-Z0-9-]+\b", query, re.IGNORECASE)
    return [m.upper() for m in match]


def validate_data_dir(data_dir):
    """Pre-flight check: validate data consistency."""
    file_names = ["orders.json", "work_orders.json", "materials.json", 
                  "machines.json", "operators.json", "schedule.json"]
    # Also check CSV if JSON not present, but loader handles fallback.
    # We just validate whatever files exist.
    
    # To validate, we need to load them.
    # We can iterate and validate.
    errors = []
    
    # Map file names to schema keys
    schema_map = {
        "orders.json": "orders", "orders.csv": "orders",
        "work_orders.json": "work_orders", "work_orders.csv": "work_orders",
        "materials.json": "materials", "materials.csv": "materials",
        "machines.json": "machines", "machines.csv": "machines",
        "operators.json": "operators", "operators.csv": "operators",
        "schedule.json": "schedule", "schedule.csv": "schedule"
    }
    
    for filename, schema_key in schema_map.items():
        filepath = os.path.join(data_dir, filename)
        if os.path.exists(filepath):
            data = load_json_or_csv(data_dir, filename) # This loads JSON or CSV
            errs = validate_dataset(schema_key, data)
            errors.extend(errs)
            
    return errors


def print_decision_report(result):
    print("\n" + "=" * 44)
    print("DECISION REPORT")
    print("=" * 44)
    print(f"Order: {result['order_id']}")
    print(f"Decision: {result['decision']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Due date: {result['due_date']}")
    print()
    print("Evidence")
    for item in result["evidence"]:
        print(f"- {item}")
    print()
    print("Blockers")
    for item in result["blockers"]:
        print(f"- {item}")
    print()
    print("Recommendation")
    print(result["recommendation"])
    print()
    print("Customer Reply")
    print(result["customer_reply"])
    print()
    print("Trace")
    for item in result["trace"]:
        print(f"- {item}")
    print("=" * 44)


def print_schedule_report(result):
    print("\n" + "=" * 44)
    print("SCHEDULE CONFLICT REPORT")
    print("=" * 44)
    print(f"Status: {result['status'].upper()}")
    if result["conflicts"]:
        for c in result["conflicts"]:
            print(f"\nCONFLICT on {c['machine_id']}")
            print(f"   Time: {c['overlap_start']} ~ {c['overlap_end']}")
            print(f"   Orders: {', '.join(c['orders'])}")
            print(f"   Winner: {c['winner']} (priority/due-date rule)")
            print(f"   Loser: {c['loser']}")
            print(f"   Suggestion: {c['suggestion']}")
    else:
        print("No conflicts found for the selected orders.")
    print()
    print("Trace")
    for item in result["trace"]:
        print(f"- {item}")
    print("=" * 44)


def main():
    parser = argparse.ArgumentParser(description="Manufacturing Agent CLI")
    parser.add_argument("--data-dir", default=None, help="Path to data directory (default: mock_data)")
    parser.add_argument("query", nargs="+", help="Natural language query")
    args = parser.parse_args()

    query = " ".join(args.query)
    
    if args.data_dir:
        data_dir = args.data_dir
    else:
        data_dir = os.path.join(os.path.dirname(__file__), "mock_data")

    print(f"Agent received: '{query}'")
    print(f"Data Source: {data_dir}")
    
    # Data Validation Step
    print("\nData Validation Check...")
    errors = validate_data_dir(data_dir)
    if errors:
        print("\nData Validation Failed:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("Data Validation Passed.")

    order_ids = extract_order_ids(query)
    if not order_ids:
        order_ids = ["ORD-1001"] # Default

    # Routing
    if "衝突" in query or "conflict" in query.lower() or len(order_ids) > 1:
        print("Routing to: schedule-conflict-check skill")
        result = check_schedule_conflict(order_ids, data_dir)
        print_schedule_report(result)
        print("\nRaw JSON")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif "準時" in query or "出貨" in query or "delivery" in query.lower():
        print("Routing to: delivery-risk-analysis skill")
        result = analyze_delivery_risk(order_ids[0], data_dir)
        if "error" in result:
            print(result["error"])
            sys.exit(1)
        print_decision_report(result)
        print("\nRaw JSON")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("Unknown intent. MVP supports delivery risk and schedule conflict queries.")

if __name__ == "__main__":
    main()
