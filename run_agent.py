
import json
import os
import sys
import argparse
from orchestrator import route_query, batch_queries
from data_dir_monitor import scan_data_dir, get_data_dir_metadata
from data_source import set_data_source, create_provider, get_provider_name
from skills.policy import get_policy, load_policy, DEFAULT_POLICY, reload_policy, get_reload_metadata
from skills.observability import log_request, log_asana_post, generate_run_id, set_run_id
from integrations.asana_client import post_comment, format_success_report, format_error_report
from audit_logger import log_run, query_runs, format_run_summary

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
    details = result.get("details", {})
    materials = details.get("materials")
    if not materials:
        materials = [{**details, "decision": result.get("decision"), "confidence": result.get("confidence")}]
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

def print_team_report(result):
    """View: Print team execution report."""
    team_name = result.get("team_name", "Unknown Team")
    print(f"\n{'=' * 44}")
    print(f"TEAM WORKFLOW: {team_name.upper()}")
    print(f"{'=' * 44}")

    summary = result.get("summary", {})
    if summary:
        total = summary.get("total_steps", 0)
        success = summary.get("success_count", 0)
        failed = summary.get("failed_count", 0)
        status = "PARTIAL" if summary.get("partial_success") else ("ALL FAILED" if failed == total else "ALL OK")
        print(f"Status: {status} ({success}/{total} steps succeeded)")

    steps = result.get("results", {})
    if not isinstance(steps, dict):
        print("ERROR: Invalid team results structure")
        return

    for alias, step_result in steps.items():
        print(f"\n{'-' * 30}")
        print(f"STEP: {alias.upper()}")
        print(f"{'-' * 30}")

        if not isinstance(step_result, dict):
            print(f"ERROR: Unexpected result type for step '{alias}'")
            continue

        if "error" in step_result:
            print(f"ERROR: {step_result['error']}")
            continue

        skill = step_result.get("skill", alias)
        try:
            if skill == "delivery-risk-analysis":
                print_decision_report(step_result)
            elif skill == "sales-response-draft":
                print_sales_response_report(step_result)
            elif skill == "internal-action-summary":
                print_internal_action_report(step_result)
            elif skill == "schedule-conflict-check":
                print_schedule_report(step_result)
            elif skill == "quote-comparison-summary":
                print_quote_report(step_result)
            elif skill == "expedite-options":
                print_expedite_report(step_result)
            elif skill == "material-shortage-recovery":
                print_material_shortage_report(step_result)
            elif skill == "capacity-rebalance":
                print_capacity_rebalance_report(step_result)
            elif skill == "supplier-followup-draft":
                print_supplier_followup_report(step_result)
            else:
                print(json.dumps(step_result, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"ERROR rendering step '{alias}': {e}")
            print(json.dumps(step_result, indent=2, ensure_ascii=False))

    print(f"\n{'=' * 44}")
    print("TEAM TRACE")
    for item in result.get("trace", []):
        print(f"- {item}")
    print(f"{'=' * 44}")

def print_expedite_report(result):
    """View: Print expedite options report."""
    print("\n" + "=" * 44)
    print("EXPEDITE OPTIONS")
    print("=" * 44)
    print(f"Order: {result.get('order_id')}")
    print(f"Customer: {result.get('customer')}")
    print(f"Decision: {result.get('decision')}")
    print(f"Days left: {result.get('details', {}).get('days_left', result.get('days_left', 'N/A'))}")
    print()

    opt_summary = result.get("details", {}).get("option_summary", {})
    total = opt_summary.get("total_evaluated", 0)
    recommended = opt_summary.get("recommended_count", 0)
    top = opt_summary.get("top_recommendation", "None")
    print(f"Options evaluated: {total}")
    print(f"Recommended: {recommended} (Top: {top})")
    print()

    options = result.get("details", {}).get("options", [])
    if not options:
        print("No options available.")
    else:
        for i, opt in enumerate(options, 1):
            rec_marker = " [RECOMMENDED]" if opt.get("recommended") else ""
            print(f"--- Option {i}: {opt.get('label')}{rec_marker} ---")
            print(f"  Feasibility: {opt.get('feasibility')} — {opt.get('feasibility_reason')}")
            print(f"  Impact: {opt.get('expected_impact')}")
            print(f"  Cost: {opt.get('cost_implication')}")
            if opt.get("blockers"):
                print(f"  Blockers: {'; '.join(opt['blockers'])}")
            if opt.get("key_assumptions"):
                print(f"  Assumptions: {'; '.join(opt['key_assumptions'][:2])}")
            print()

    print("Top Blockers")
    for b in result.get("blockers", []) or ["No critical blockers."]:
        print(f"- {b}")
    print()
    print("Recommendation")
    print(result.get("next_action"))
    print()
    print("Trace")
    for item in result.get("trace", []):
        print(f"- {item}")
    print("=" * 44)


def print_material_shortage_report(result):
    """View: Print material shortage recovery report."""
    print("\n" + "=" * 44)
    print("MATERIAL SHORTAGE RECOVERY")
    print("=" * 44)
    print(f"Order: {result.get('order_id')}")
    print(f"Customer: {result.get('customer')}")
    print(f"Decision: {result.get('decision')}")
    print(f"Days left: {result.get('details', {}).get('days_left', 'N/A')}")
    print()

    rec_summary = result.get("details", {}).get("recovery_summary", {})
    total_shortages = rec_summary.get("total_shortages", 0)
    total_evaluated = rec_summary.get("total_evaluated", 0)
    recommended = rec_summary.get("recommended_count", 0)
    top = rec_summary.get("top_recommendation", "None")
    print(f"Shortages detected: {total_shortages}")
    print(f"Options evaluated: {total_evaluated}")
    print(f"Recommended: {recommended} (Top: {top})")
    print()

    shortages = result.get("details", {}).get("shortages", [])
    if shortages:
        print("Shortage Materials")
        for s in shortages:
            print(f"  - {s.get('material')}: {s.get('available_qty')}/{s.get('required_qty')} "
                  f"(shortage: {s.get('shortage_qty')}, lead time: {s.get('lead_time_days')}d, "
                  f"reliability: {s.get('supplier_reliability', 0):.0%})")
        print()

    options = result.get("details", {}).get("options", [])
    if options:
        for i, opt in enumerate(options, 1):
            rec_marker = " [RECOMMENDED]" if opt.get("recommended") else ""
            print(f"--- Option {i}: {opt.get('label')}{rec_marker} ---")
            print(f"  Feasibility: {opt.get('feasibility')} - {opt.get('feasibility_reason')}")
            print(f"  Impact: {opt.get('expected_impact')}")
            print(f"  Lead time: {opt.get('lead_time_implication')}")
            print(f"  Cost: {opt.get('cost_implication')}")
            if opt.get("blockers"):
                print(f"  Blockers: {'; '.join(opt['blockers'])}")
            if opt.get("assumptions"):
                print(f"  Assumptions: {'; '.join(opt['assumptions'][:2])}")
            print()

    print("Top Blockers")
    for b in result.get("blockers", []) or ["No critical blockers."]:
        print(f"- {b}")
    print()
    print("Recommendation")
    print(result.get("next_action"))
    print()
    print("Trace")
    for item in result.get("trace", []):
        print(f"- {item}")
    print("=" * 44)


def print_capacity_rebalance_report(result):
    """View: Print capacity rebalance report."""
    print("\n" + "=" * 44)
    print("CAPACITY REBALANCE")
    print("=" * 44)
    print(f"Order: {result.get('order_id')}")
    print(f"Customer: {result.get('customer')}")
    print(f"Decision: {result.get('decision')}")
    print(f"Days left: {result.get('details', {}).get('days_left', 'N/A')}")
    print()

    rebal = result.get("details", {}).get("rebalance_summary", {})
    pressures = rebal.get("total_pressures", 0)
    conflicts = rebal.get("total_conflicts", 0)
    total_eval = rebal.get("total_evaluated", 0)
    recommended = rebal.get("recommended_count", 0)
    top = rebal.get("top_recommendation", "None")
    print(f"Pressure points: {pressures}")
    print(f"Schedule conflicts: {conflicts}")
    print(f"Options evaluated: {total_eval}")
    print(f"Recommended: {recommended} (Top: {top})")
    print()

    # Machine utilization
    util = result.get("details", {}).get("machine_utilization", {})
    if util:
        print("Machine Utilization")
        for mid, u in util.items():
            status_marker = "" if u.get("status") == "Running" else f" [{u.get('status')}]"
            print(f"  {mid}: {u.get('load_percent')}% / {u.get('max_capacity_percent')}% max "
                  f"(available: {u.get('available_capacity_percent')}%){status_marker}")
        print()

    # Pressures
    pressure_list = result.get("details", {}).get("pressures", [])
    if pressure_list:
        print("Pressure Points")
        for p in pressure_list:
            sev = p.get("severity", "unknown").upper()
            print(f"  [{sev}] {p.get('detail')}")
        print()

    # Options
    options = result.get("details", {}).get("options", [])
    if options:
        for i, opt in enumerate(options, 1):
            rec_marker = " [RECOMMENDED]" if opt.get("recommended") else ""
            print(f"--- Option {i}: {opt.get('label')}{rec_marker} ---")
            print(f"  Feasibility: {opt.get('feasibility')} - {opt.get('feasibility_reason')}")
            print(f"  Impact: {opt.get('expected_impact')}")
            print(f"  Capacity: {opt.get('capacity_effect')}")
            print(f"  Timing: {opt.get('timing_implication')}")
            print(f"  Cost: {opt.get('cost_implication')}")
            if opt.get("blockers"):
                print(f"  Blockers: {'; '.join(opt['blockers'])}")
            if opt.get("assumptions"):
                print(f"  Assumptions: {'; '.join(opt['assumptions'][:2])}")
            print()

    print("Top Blockers")
    for b in result.get("blockers", []) or ["No critical blockers."]:
        print(f"- {b}")
    print()
    print("Recommendation")
    print(result.get("next_action"))
    print()
    print("Trace")
    for item in result.get("trace", []):
        print(f"- {item}")
    print("=" * 44)


def print_supplier_followup_report(result):
    """View: Print supplier follow-up draft report."""
    print("\n" + "=" * 44)
    print("SUPPLIER FOLLOW-UP DRAFT")
    print("=" * 44)
    print(f"Order: {result.get('order_id')}")
    print(f"Customer: {result.get('customer')}")
    print(f"Decision: {result.get('decision')}")
    print(f"Days left: {result.get('details', {}).get('days_left', 'N/A')}")
    print()

    ds = result.get("details", {}).get("draft_summary", {})
    total = ds.get("total_drafts", 0)
    recommended = ds.get("recommended_count", 0)
    top = ds.get("top_recommendation", "None")
    urgency = ds.get("top_urgency", "N/A")
    print(f"Drafts generated: {total}")
    print(f"Recommended: {recommended} (Top: {top}, Urgency: {urgency})")
    print()

    drafts = result.get("details", {}).get("drafts", [])
    if drafts:
        for i, d in enumerate(drafts, 1):
            rec_marker = " [RECOMMENDED]" if d.get("recommended") else ""
            print(f"--- Draft {i}: {d.get('label')}{rec_marker} ---")
            print(f"  Type: {d.get('draft_type')}")
            print(f"  Target: {d.get('target_supplier')}")
            print(f"  Subject: {d.get('subject')}")
            print(f"  Urgency: {d.get('urgency_level')} - {d.get('urgency_reason')}")
            print(f"  Key Asks:")
            for ask in d.get("key_asks", [])[:3]:
                print(f"    - {ask}")
            print()

    # Show the full draft text
    reply = result.get("reply_draft")
    if reply:
        print("Full Draft (Copy/Paste Ready)")
        print("-" * 40)
        print(reply)
        print("-" * 40)
        print()

    print("Top Blockers")
    for b in result.get("blockers", []) or ["No critical blockers."]:
        print(f"- {b}")
    print()
    print("Recommendation")
    print(result.get("next_action"))
    print()
    print("Trace")
    for item in result.get("trace", []):
        print(f"- {item}")
    print("=" * 44)


def main():
    parser = argparse.ArgumentParser(description="Manufacturing Agent CLI")
    parser.add_argument("--data-dir", default=None, help="Path to data directory (default: mock_data)")
    parser.add_argument("--data-source", default="local", choices=["local", "live", "auto"],
                        help="Data source mode: local (files), live (MCP/ERP), auto (live with fallback)")
    parser.add_argument("--asana-task", default=None, help="Asana Task GID to post result comment")
    parser.add_argument("--history", action="store_true", help="Query run history instead of executing a new query")
    parser.add_argument("--last", type=int, default=10, help="Number of recent runs to show (default: 10, used with --history)")
    parser.add_argument("--status", default=None, help="Filter by status: success or error (used with --history)")
    parser.add_argument("--skill", default=None, help="Filter by skill name (used with --history)")
    parser.add_argument("--channel", default=None, help="Filter by channel: cli or http (used with --history)")
    parser.add_argument("--run-id", default=None, help="Filter by specific run ID (used with --history)")
    parser.add_argument("--policy", action="store_true", help="Show active policy configuration and exit")
    parser.add_argument("--reload-policy", action="store_true", help="Reload policy from config file and exit")
    parser.add_argument("--data-dir-status", action="store_true", help="Show data directory status and exit")
    parser.add_argument("--batch-file", default=None, help="Path to file containing one query per line (batch mode)")
    parser.add_argument("query", nargs="*", help="Natural language query (omit when using --history or --batch-file)")
    args = parser.parse_args()

    # Policy inspection mode
    if args.policy:
        policy = load_policy()
        print(f"Policy source: {policy.get('_source', 'default')}")
        print(json.dumps({k: v for k, v in policy.items() if not k.startswith("_")}, indent=2))
        return

    # Policy hot-reload mode
    if args.reload_policy:
        result = reload_policy()
        meta = get_reload_metadata()
        print(f"Reload success: {result['success']}")
        print(f"Source: {result['source']}")
        if result['error']:
            print(f"Error: {result['error']}")
        print(f"Reload count: {meta['reload_count']}")
        print(f"Last reload: {meta['last_reload_at'] or 'never'}")
        return

    # Data directory status mode
    if args.data_dir_status:
        data_dir = args.data_dir or os.path.join(os.path.dirname(__file__), "mock_data")
        meta = get_data_dir_metadata(data_dir)
        print(f"Data directory: {meta['data_dir']}")
        print(f"Files: {meta['file_count']}")
        if meta['last_modified']:
            print(f"Last modified: {meta['last_modified']}")
        if meta['error']:
            print(f"Error: {meta['error']}")
        print(f"Scanned at: {meta['scanned_at']}")
        if meta['files']:
            print("\nFiles:")
            for f in meta['files']:
                print(f"  {f['name']} (mtime: {f['mtime']})")
        return

    # History query mode
    if args.history:
        if args.last is not None and args.last <= 0:
            print("Error: --last must be a positive integer.")
            sys.exit(1)
        runs = query_runs(
            last_n=args.last,
            status=args.status,
            skill=args.skill,
            channel=args.channel,
            run_id=args.run_id,
        )
        print(format_run_summary(runs, compact=False))
        return

    # Execution mode
    data_dir = args.data_dir or os.path.join(os.path.dirname(__file__), "mock_data")
    set_data_source(create_provider(args.data_source))
    print(f"Data Source: {data_dir} (mode: {get_provider_name()})")

    if args.batch_file:
        # Batch mode
        with open(args.batch_file, "r", encoding="utf-8") as f:
            queries = [line.strip() for line in f if line.strip()]
        if not queries:
            print("Error: Batch file is empty or contains no valid queries.")
            sys.exit(1)

        log_request(f"batch:{len(queries)}", "cli", data_source=args.data_source)
        print(f"\nBatch mode: {len(queries)} queries loaded from {args.batch_file}")
        
        batch_result = batch_queries(queries, data_dir)
        
        print(f"\n{'='*44}")
        print(f"BATCH SUMMARY: {batch_result['success_count']}/{batch_result['total']} succeeded")
        print(f"{'='*44}")
        
        for item in batch_result["results"]:
            res = item["result"]
            status_icon = "OK" if res["status"] == "success" else "FAIL"
            print(f"\n[{status_icon}] #{item['index']+1}: {item['query']}")
            if res["status"] == "success":
                print(f"  Skill: {res.get('skill', 'N/A')} | Run ID: {res.get('run_id', '-')}")
            else:
                print(f"  Error: {res.get('error', 'Unknown')}")
        
        # Log batch results
        for item in batch_result["results"]:
            res = item["result"]
            log_run({
                "status": res["status"], "query": item["query"], "data_dir": data_dir,
                "order_ids": res.get("order_ids", []), "intent": res.get("intent"),
                "skill": res.get("skill"), "run_id": res.get("run_id"),
                "type": res.get("error_type"), "data": {} if res["status"] == "success" else None,
            }, "cli")
        
        sys.exit(0 if batch_result["error_count"] == 0 else 1)

    # Single query mode
    if not args.query:
        parser.print_help()
        sys.exit(1)

    query = " ".join(args.query)

    # Orchestrate
    print("\nData Validation Check...")
    try:
        response = route_query(query, data_dir)
    except Exception as e:
        response = {
            "status": "error",
            "type": "internal_error",
            "details": str(e),
            "query": query,
            "data_dir": data_dir,
            "order_ids": [],
        }

    exit_code = 0
    asana_posted = None

    if response["status"] == "error":
        run_id = response.get("run_id", "-")
        print(f"\nRun ID: {run_id}")
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
            log_asana_post(args.asana_task, asana_posted, run_id=response.get("run_id"))
            
        exit_code = 1
    else:
        print("Data Validation Passed.")

        # Display run_id
        run_id = response.get("run_id", "-")
        print(f"Run ID: {run_id}")

        # Render
        skill = response["skill"]
        data = response["data"]

        if response.get("is_team"):
            print(f"Routing to: team workflow ({skill})")
            print_team_report(data)
            print("\nRaw JSON")
            print(json.dumps(data, indent=2, ensure_ascii=False))
        elif skill == "delivery-risk-analysis":
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
        elif skill == "expedite-options":
            print("Routing to: expedite-options skill")
            print_expedite_report(data)
            print("\nRaw JSON")
            print(json.dumps(data, indent=2, ensure_ascii=False))
        elif skill == "material-shortage-recovery":
            print("Routing to: material-shortage-recovery skill")
            print_material_shortage_report(data)
            print("\nRaw JSON")
            print(json.dumps(data, indent=2, ensure_ascii=False))
        elif skill == "capacity-rebalance":
            print("Routing to: capacity-rebalance skill")
            print_capacity_rebalance_report(data)
            print("\nRaw JSON")
            print(json.dumps(data, indent=2, ensure_ascii=False))
        elif skill == "supplier-followup-draft":
            print("Routing to: supplier-followup-draft skill")
            print_supplier_followup_report(data)
            print("\nRaw JSON")
            print(json.dumps(data, indent=2, ensure_ascii=False))

        # Post to Asana if requested
        if args.asana_task:
            print(f"\nPosting result to Asana Task {args.asana_task}...")
            comment = format_success_report(response)
            asana_posted = post_comment(args.asana_task, comment)
            log_asana_post(args.asana_task, asana_posted, run_id=response.get("run_id"))
            if asana_posted:
                print("Asana comment posted.")
            else:
                print("Failed to post Asana comment (check token/network).")

    # Audit Log
    log_run(response, "cli", args.asana_task, asana_posted)
    
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
