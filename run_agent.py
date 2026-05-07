
import json
import os
import sys
import argparse
from orchestrator import route_query
from integrations.asana_client import post_comment, format_success_report, format_error_report

def print_decision_report(result):
    """View: Print delivery risk report."""
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
    """View: Print schedule conflict report."""
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
    parser.add_argument("--asana-task", default=None, help="Asana Task GID to post result comment")
    parser.add_argument("query", nargs="+", help="Natural language query")
    args = parser.parse_args()

    query = " ".join(args.query)
    data_dir = args.data_dir or os.path.join(os.path.dirname(__file__), "mock_data")

    print(f"Agent received: '{query}'")
    print(f"Data Source: {data_dir}")

    # Orchestrate
    print("\nData Validation Check...")
    response = route_query(query, data_dir)

    if response["status"] == "error":
        print(f"\nOperation Failed ({response['type']}):")
        if isinstance(response['details'], list):
            for err in response['details']:
                print(f"  - {err}")
        else:
            print(f"  {response['details']}")
        
        # Post error to Asana if requested
        if args.asana_task:
            print(f"\n📤 Posting error to Asana Task {args.asana_task}...")
            comment = format_error_report(response)
            post_comment(args.asana_task, comment)
            
        sys.exit(1)
    print("Data Validation Passed.")

    # Render
    skill = response["skill"]
    data = response["data"]

    if skill == "delivery-risk-analysis":
        print("Routing to: delivery-risk-analysis skill")
        print_decision_report(data)
        print("\nRaw JSON")
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif skill == "schedule-conflict-check":
        print("Routing to: schedule-conflict-check skill")
        print_schedule_report(data)
        print("\nRaw JSON")
        print(json.dumps(data, indent=2, ensure_ascii=False))

    # Post to Asana if requested
    if args.asana_task:
        print(f"\n Posting result to Asana Task {args.asana_task}...")
        comment = format_success_report(response)
        success = post_comment(args.asana_task, comment)
        if success:
            print("✅ Asana comment posted.")
        else:
            print("⚠️  Failed to post Asana comment (check token/network).")

if __name__ == "__main__":
    main()
