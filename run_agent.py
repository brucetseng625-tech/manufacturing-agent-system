
import json
import os
import re
import sys
from skills.delivery_risk import analyze_delivery_risk
from skills.schedule_conflict_check import check_schedule_conflict


def extract_order_ids(query):
    match = re.findall(r"\bORD-\d+\b", query, re.IGNORECASE)
    return [m.upper() for m in match]


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
            print(f"\n️ CONFLICT on {c['machine_id']}")
            print(f"   Time: {c['overlap_start']} ~ {c['overlap_end']}")
            print(f"   Orders: {', '.join(c['orders'])}")
            print(f"   👑 Winner: {c['winner']} (Priority)")
            print(f"    Loser: {c['loser']}")
            print(f"   📝 Suggestion: {c['suggestion']}")
    else:
        print("No conflicts found for the selected orders.")
    print()
    print("Trace")
    for item in result["trace"]:
        print(f"- {item}")
    print("=" * 44)


def main():
    if len(sys.argv) < 2:
        print('Usage: python3 run_agent.py "Query"')
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    mock_data_dir = os.path.join(os.path.dirname(__file__), "mock_data")

    print(f"Agent received: '{query}'")

    order_ids = extract_order_ids(query)
    if not order_ids:
        order_ids = ["ORD-1001"] # Default

    # Routing
    if "衝突" in query or "conflict" in query.lower() or len(order_ids) > 1:
        print("Routing to: schedule-conflict-check skill")
        result = check_schedule_conflict(order_ids, mock_data_dir)
        print_schedule_report(result)
        print("\nRaw JSON")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif "準時" in query or "出貨" in query or "delivery" in query.lower():
        print("Routing to: delivery-risk-analysis skill")
        result = analyze_delivery_risk(order_ids[0], mock_data_dir)
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
