
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
    print(f"Order: {result.get('order_id')}")
    print(f"Customer: {result.get('customer')}")
    print(f"Decision: {result.get('decision')}")
    print(f"Confidence: {result.get('confidence')}")
    print(f"Due date: {result.get('eta')}")
    print()
    print("Evidence")
    for item in result.get("details", {}).get("evidence", []):
        print(f"- {item}")
    print()
    print("Blockers")
    for item in result.get("blockers", []):
        print(f"- {item}")
    print()
    print("Recommendation")
    print(result.get("next_action"))
    print()
    print("Customer Reply")
    print(result.get("reply_draft"))
    print()
    print("Trace")
    for item in result.get("trace", []):
        print(f"- {item}")
    print("=" * 44)

def print_schedule_report(result):
    """View: Print schedule conflict report."""
    print("\n" + "=" * 44)
    print("SCHEDULE CONFLICT REPORT")
    print("=" * 44)
    print(f"Status: {result.get('decision', 'unknown').upper()}")
    conflicts = result.get("details", {}).get("conflicts", [])
    if conflicts:
        for c in conflicts:
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
    for item in result.get("trace", []):
        print(f"- {item}")
    print("=" * 44)

def print_quote_report(result):
    """View: Print quote comparison report."""
    print("\n" + "=" * 44)
    print("QUOTE COMPARISON REPORT")
    print("=" * 44)
    materials = result.get("details", {}).get("materials", [result])
    if materials and isinstance(materials, list):
        for m in materials:
            print(f"\nMaterial: {m.get('material')}")
            print(f"Recommended: {m.get('recommended_supplier')}")
            print(f"Decision: {m.get('decision')}")
            print(f"Confidence: {m.get('confidence')}")
            print(f"Price Spread: ${m.get('price_spread')}")
            lt = m.get('lead_time_summary', {})
            print(f"Lead Time: Avg {lt.get('avg_days')}d (Min: {lt.get('min_days')}d, Max: {lt.get('max_days')}d)")
            print("Risks:")
            risks = m.get('risks', {})
            print(f"  High Risk Suppliers: {risks.get('high_risk_suppliers', 0)}")
            print("Evidence:")
            for e in m.get("evidence", []):
                print(f"- {e}")
            print(f"Recommendation: {m.get('recommendation')}")
    else:
        print(f"Material: {result.get('material')}")
        print(f"Recommended: {result.get('recommended_supplier')}")
        print(f"Decision: {result.get('decision')}")
        print(f"Confidence: {result.get('confidence')}")
        print(f"Price Spread: ${result.get('price_spread')}")
        lt = result.get('lead_time_summary', {})
        print(f"Lead Time: Avg {lt.get('avg_days')}d (Min: {lt.get('min_days')}d, Max: {lt.get('max_days')}d)")
        print("Risks:")
        risks = result.get('risks', {})
        print(f"  High Risk Suppliers: {risks.get('high_risk_suppliers', 0)}")
        print("Evidence:")
        for e in result.get("evidence", []):
            print(f"- {e}")
        print(f"Recommendation: {result.get('recommendation')}")
        print()
        print("Supplier Reply Draft")
        print(result.get("reply_draft"))
    print()
    print("Trace")
    for item in result.get("trace", []):
        print(f"- {item}")
    print("=" * 44)

def print_sales_response_report(result):
    """View: Print sales response draft report."""
    print("\n" + "=" * 44)
    print("SALES RESPONSE DRAFT")
    print("=" * 44)
    print(f"Order: {result.get('order_id')}")
    print(f"Customer: {result.get('customer')}")
    print(f"Decision: {result.get('decision')}")
    print(f"Confidence: {result.get('confidence')}")
    print(f"Shipment Status: {result.get('details', {}).get('shipment_status')}")
    print(f"Key Message: {result.get('details', {}).get('key_message')}")
    print()
    print("Risk Summary")
    for item in result.get("blockers", []) or ["No critical risks highlighted."]:
        print(f"- {item}")
    print()
    print("Internal Guidance")
    print(result.get("next_action"))
    print()
    print("Customer Reply Draft")
    print(result.get("reply_draft"))
    print()
    print("Trace")
    for item in result.get("trace", []):
        print(f"- {item}")
    print("=" * 44)

def print_internal_action_report(result):
    """View: Print internal action summary."""
    print("\n" + "=" * 44)
    print("INTERNAL ACTION SUMMARY")
    print("=" * 44)
    print(f"Order: {result.get('order_id')}")
    print(f"Customer: {result.get('customer')}")
    print(f"Decision: {result.get('decision')}")
    print(f"Confidence: {result.get('confidence')}")
    print()
    print("Top Blockers")
    for b in result.get("blockers", []):
        print(f"- {b}")
    print()
    print("Immediate Actions")
    next_action = result.get("next_action", [])
    if isinstance(next_action, list):
        for a in next_action:
            print(f"- {a}")
    else:
        print(f"- {next_action}")
    print()
    print(f"Owner: {result.get('owner')}")
    print(f"Escalation: {result.get('escalation')}")
    print()
    print("Asana Note (Copy/Paste)")
    print(result.get("details", {}).get("asana_note", ""))
    print()
    print("Trace")
    for item in result.get("trace", []):
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
