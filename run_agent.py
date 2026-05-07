
import json
import os
import re
import sys
from skills.delivery_risk import analyze_delivery_risk


def extract_order_id(query):
    match = re.search(r"\bORD-\d+\b", query, re.IGNORECASE)
    if not match:
        return "ORD-1001"
    return match.group(0).upper()


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


def main():
    if len(sys.argv) < 2:
        print('Usage: python3 run_agent.py "這張急單 ORD-1001 能不能準時出？"')
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    mock_data_dir = os.path.join(os.path.dirname(__file__), "mock_data")

    print(f"Agent received: '{query}'")

    order_id = extract_order_id(query)

    # Routing
    if "準時" in query or "出貨" in query or "delivery" in query.lower():
        print("Routing to: delivery-risk-analysis skill")
        result = analyze_delivery_risk(order_id, mock_data_dir)
        if "error" in result:
            print(result["error"])
            sys.exit(1)
        print_decision_report(result)
        print("\nRaw JSON")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("Unknown intent. MVP only supports delivery risk queries.")

if __name__ == "__main__":
    main()
