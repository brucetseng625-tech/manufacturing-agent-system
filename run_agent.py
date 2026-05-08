
import json
import os
import sys
import argparse
from orchestrator import route_query
from integrations.asana_client import post_comment, format_success_report, format_error_report
from audit_logger import log_run

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

def print_quote_report(result):
    """View: Print quote comparison report."""
    print("\n" + "=" * 44)
    print("QUOTE COMPARISON REPORT")
    print("=" * 44)
    if "materials" in result:
        for m in result["materials"]:
            print(f"\nMaterial: {m['material']}")
            print(f"Recommended: {m['recommended_supplier']}")
            print(f"Decision: {m['decision']}")
            print(f"Confidence: {m['confidence']}")
            print(f"Price Spread: ${m['price_spread']}")
            lt = m['lead_time_summary']
            print(f"Lead Time: Avg {lt['avg_days']}d (Min: {lt['min_days']}d, Max: {lt['max_days']}d)")
            print("Risks:")
            print(f"  High Risk Suppliers: {m['risks']['high_risk_suppliers']}")
            print("Evidence:")
            for e in m["evidence"]:
                print(f"- {e}")
            print(f"Recommendation: {m['recommendation']}")
    else:
        print(f"Material: {result['material']}")
        print(f"Recommended: {result['recommended_supplier']}")
        print(f"Decision: {result['decision']}")
        print(f"Confidence: {result['confidence']}")
        print(f"Price Spread: ${result['price_spread']}")
        lt = result['lead_time_summary']
        print(f"Lead Time: Avg {lt['avg_days']}d (Min: {lt['min_days']}d, Max: {lt['max_days']}d)")
        print("Risks:")
        print(f"  High Risk Suppliers: {result['risks']['high_risk_suppliers']}")
        print("Evidence:")
        for e in result["evidence"]:
            print(f"- {e}")
        print(f"Recommendation: {result['recommendation']}")
        print()
        print("Supplier Reply Draft")
        print(result["supplier_reply_draft"])
    print()
    print("Trace")
    for item in result["trace"]:
        print(f"- {item}")
    print("=" * 44)

def print_sales_response_report(result):
    """View: Print sales response draft report."""
    print("\n" + "=" * 44)
    print("SALES RESPONSE DRAFT")
    print("=" * 44)
    print(f"Order: {result['order_id']}")
    print(f"Customer: {result['customer']}")
    print(f"Decision: {result['decision']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Shipment Status: {result['shipment_status']}")
    print(f"Key Message: {result['key_message']}")
    print()
    print("Risk Summary")
    for item in result["risk_summary"] or ["No critical risks highlighted."]:
        print(f"- {item}")
    print()
    print("Internal Guidance")
    print(result["internal_guidance"])
    print()
    print("Customer Reply Draft")
    print(result["customer_reply_draft"])
    print()
    print("Trace")
    for item in result["trace"]:
        print(f"- {item}")
    print("=" * 44)

def print_internal_action_report(result):
    """View: Print internal action summary."""
    print("\n" + "=" * 44)
    print("INTERNAL ACTION SUMMARY")
    print("=" * 44)
    print(f"Order: {result['order_id']}")
    print(f"Customer: {result['customer']}")
    print(f"Decision: {result['current_decision']}")
    print(f"Confidence: {result['confidence']}")
    print()
    print("Top Blockers")
    for b in result.get("top_blockers", []):
        print(f"- {b}")
    print()
    print("Immediate Actions")
    for a in result.get("immediate_actions", []):
        print(f"- {a}")
    print()
    print(f"Owner: {result['owner_suggestion']}")
    print(f"Escalation: {result['escalation_suggestion']}")
    print()
    print("Asana Note (Copy/Paste)")
    print(result['asana_note'])
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

    exit_code = 0
    asana_posted = None

    if response["status"] == "error":
        print(f"\nOperation Failed ({response['type']}):")
        if isinstance(response['details'], list):
            for err in response['details']:
                print(f"  - {err}")
        else:
            print(f"  {response['details']}")
        
        # Post error to Asana if requested
        if args.asana_task:
            print(f"\nPosting error to Asana Task {args.asana_task}...")
            comment = format_error_report(response)
            asana_posted = post_comment(args.asana_task, comment)
            
        exit_code = 1
    else:
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
        elif skill == "quote-comparison-summary":
            print("Routing to: quote-comparison-summary skill")
            print_quote_report(data)
            print("\nRaw JSON")
            print(json.dumps(data, indent=2, ensure_ascii=False))
        elif skill == "internal-action-summary":
            print("Routing to: internal-action-summary skill")
            print_internal_action_report(data)
            print("\nRaw JSON")
            print(json.dumps(data, indent=2, ensure_ascii=False))
        elif skill == "sales-response-draft":
            print("Routing to: sales-response-draft skill")
            print_sales_response_report(data)
            print("\nRaw JSON")
            print(json.dumps(data, indent=2, ensure_ascii=False))

        # Post to Asana if requested
        if args.asana_task:
            print(f"\nPosting result to Asana Task {args.asana_task}...")
            comment = format_success_report(response)
            asana_posted = post_comment(args.asana_task, comment)
            if asana_posted:
                print("Asana comment posted.")
            else:
                print("Failed to post Asana comment (check token/network).")

    # Audit Log
    log_run(response, "cli", args.asana_task, asana_posted)
    
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
