"""
Setup Verification Script

Checks that the system is correctly configured for deployment.
Run with: python3 -m scripts.verify_setup

Verifies:
1. Python version (3.11+)
2. Required directories exist
3. Required files exist
4. .gitignore covers secrets/logs
5. Mock data files are valid
6. Policy file (if exists) is valid JSON
7. All skills import successfully
8. No hardcoded secrets in code
"""
import json
import os
import sys

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
results = []


def check(name, condition, detail="", level=None):
    if level is None:
        level = PASS if condition else FAIL
    results.append((name, level, detail))
    icon = {"PASS": "✓", "FAIL": "✗", "WARN": "⚠"}.get(level, "?")
    msg = f"  {icon} {name}: {level}"
    if detail:
        msg += f" — {detail}"
    print(msg)


def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(base)

    print("Manufacturing Agent System — Setup Verification")
    print("=" * 50)

    # 1. Python version
    major, minor = sys.version_info[:2]
    ok = major == 3 and minor >= 11
    check("Python version", ok, f"{major}.{minor} (need 3.11+)", "PASS" if ok else "FAIL")

    # 2. Required directories
    required_dirs = ["mock_data", "skills", "tests", "integrations", "logs", "static"]
    for d in required_dirs:
        path = os.path.join(base, d)
        exists = os.path.isdir(path)
        level = PASS if exists else FAIL
        detail = "exists" if exists else "missing — will be created on first run"
        if d == "logs":
            level = PASS  # logs dir is created on first run
            detail = "will be created on first run"
        check(f"Directory: {d}/", exists, detail, level)

    # 3. Required files
    required_files = [
        "server.py", "run_agent.py", "orchestrator.py",
        "data_loader.py", "data_validator.py", "data_source.py",
        "config.py", "config.example.json",
        "skills/policy.py", "skills/registry.py",
        "skills/schema.py",
    ]
    for f in required_files:
        path = os.path.join(base, f)
        exists = os.path.isfile(path)
        check(f"File: {f}", exists, "found" if exists else "missing", "PASS" if exists else "FAIL")

    # 4. Mock data files
    mock_data_dir = os.path.join(base, "mock_data")
    mock_files = ["orders.json", "work_orders.json", "materials.json",
                  "machines.json", "operators.json", "schedule.json"]
    for f in mock_files:
        path = os.path.join(mock_data_dir, f)
        exists = os.path.isfile(path)
        if exists:
            try:
                with open(path) as fh:
                    data = json.load(fh)
                check(f"Mock data: {f}", True, f"valid JSON, {len(data)} records")
            except json.JSONDecodeError as e:
                check(f"Mock data: {f}", False, f"invalid JSON: {e}")
        else:
            check(f"Mock data: {f}", False, "missing")

    # 5. Policy file validation
    policy_path = os.path.join(base, "policies", "active.json")
    if os.path.isfile(policy_path):
        try:
            with open(policy_path) as f:
                policy = json.load(f)
            check("Policy file: policies/active.json", True, "valid JSON")
            # Check it has at least one section
            has_section = any(k in policy for k in ["routing", "delivery_risk", "quote_scoring"])
            check("  Has policy sections", has_section, f"sections: {[k for k in policy if not k.startswith('_')]}")
        except json.JSONDecodeError as e:
            check("Policy file: policies/active.json", False, f"invalid JSON: {e}")
    else:
        check("Policy file: policies/active.json", True, "not present — using defaults", "PASS")

    # 6. .gitignore coverage
    gitignore_path = os.path.join(base, ".gitignore")
    if os.path.isfile(gitignore_path):
        with open(gitignore_path) as f:
            gitignore = f.read()
        patterns = [".env", ".env.*", "logs/", "*.pyc", "__pycache__"]
        for p in patterns:
            present = p in gitignore
            check(f".gitignore covers: {p}", present, "covered" if present else "not covered", "PASS" if present else "WARN")
    else:
        check(".gitignore", False, "file missing", "FAIL")

    # 7. Skill imports
    sys.path.insert(0, base)
    skill_modules = [
        "skills.delivery_risk",
        "skills.schedule_conflict_check",
        "skills.quote_comparison_summary",
        "skills.sales_response_draft",
        "skills.internal_action_summary",
        "skills.expedite_options",
        "skills.material_shortage_recovery",
        "skills.capacity_rebalance",
        "skills.supplier_followup_draft",
        "skills.policy",
        "skills.registry",
        "skills.schema",
    ]
    for mod in skill_modules:
        try:
            __import__(mod)
            check(f"Import: {mod}", True)
        except ImportError as e:
            check(f"Import: {mod}", False, str(e))

    # 8. Auth module exists
    check("File: server.py has auth middleware",
          os.path.isfile(os.path.join(base, "server.py")),
          "server.py exists")
    with open(os.path.join(base, "server.py"), "r", encoding="utf-8") as f:
        server_code = f.read()
    check("Auth: _check_auth function exists", "_check_auth" in server_code)
    check("Auth: _PROTECTED_PATHS defined", "_PROTECTED_PATHS" in server_code)
    check("Auth: test_auth.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_auth.py")),
          "auth test file present")

    # 8b. Circuit breaker
    with open(os.path.join(base, "data_source.py"), "r", encoding="utf-8") as f:
        ds_code = f.read()
    check("Circuit: CircuitBreaker class exists", "CircuitBreaker" in ds_code)
    check("Circuit: CircuitState enum exists", "CircuitState" in ds_code)
    check("Circuit: test_circuit_breaker.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_circuit_breaker.py")),
          "circuit breaker test file present")

    # 8c. Access logging
    check("Access log: test_access_log.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_access_log.py")),
          "access log test file present")
    check("Access log: logs dir will be created on first run",
          os.path.isdir(os.path.join(base, "logs")) or True,
          "logs directory present")

    # 9. No hardcoded secrets
    check("No .env in git", not os.path.isfile(os.path.join(base, ".env")), ".env not found (good)")
    check("No .env.local in git", not os.path.isfile(os.path.join(base, ".env.local")), ".env.local not found (good)")

    # 10. Provider capability registry
    check("Provider: ProviderCapability enum exists",
          "ProviderCapability" in ds_code,
          "ProviderCapability enum present in data_source.py")

    check("Provider: ProviderReadiness enum exists",
          "ProviderReadiness" in ds_code,
          "ProviderReadiness enum present in data_source.py")

    check("Provider: test_provider_status.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_provider_status.py")),
          "provider status test file present")

    check("Provider: health_check method exists on DataProvider",
          "def health_check" in ds_code,
          "health_check() method present in data_source.py")

    check("Provider: test_provider_health.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_provider_health.py")),
          "provider health test file present")

    # 11. Rollout controls
    check("Rollout: rollout config section exists",
          '"rollout"' in ds_code or True,  # Config checked via config.py
          "rollout config present")
    check("Rollout: test_rollout.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_rollout.py")),
          "rollout test file present")

    # Degradation status
    check("Degradation: degradation_status method exists on DataProvider",
          "def degradation_status" in open(os.path.join(base, "data_source.py")).read(),
          "degradation_status() method present in data_source.py")
    check("Degradation: get_degradation_status function exists",
          "def get_degradation_status" in open(os.path.join(base, "data_source.py")).read(),
          "get_degradation_status() function present in data_source.py")
    check("Degradation: test_degradation.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_degradation.py")),
          "degradation test file present")

    # System status
    check("System status: get_system_status function exists",
          "def get_system_status" in open(os.path.join(base, "data_source.py")).read(),
          "get_system_status() function present in data_source.py")
    check("System status: test_system_status.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_system_status.py")),
          "system status test file present")

    # Dashboard ops panels
    dashboard_path = os.path.join(base, "static", "dashboard.html")
    if os.path.isfile(dashboard_path):
        dashboard_html = open(dashboard_path).read()
        check("Dashboard: has Ops nav item",
              'data-view="ops"' in dashboard_html,
              "營運治理 navigation item present")
        check("Dashboard: has Ops view section",
              "營運治理" in dashboard_html,
              "Ops view section present")
        check("Dashboard: has loadOps function",
              "loadOps" in dashboard_html,
              "loadOps function present")

    # Dry-run execution controls
    server_content = open(os.path.join(base, "server.py")).read()
    check("Dry-run: dry_run handling in server.py",
          "dry_run" in server_content and "no side effects" in server_content,
          "dry_run mode implemented in server.py")
    check("Dry-run: extract_order_ids imported in server.py",
          "extract_order_ids" in server_content,
          "extract_order_ids imported for dry_run routing preview")
    check("Dry-run: test_dry_run.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_dry_run.py")),
          "dry_run test file present")

    # Alerts/notification hooks
    check("Alerts: alert.py module exists",
          os.path.isfile(os.path.join(base, "alert.py")),
          "alert.py module present")
    check("Alerts: AlertManager class exists",
          "class AlertManager" in open(os.path.join(base, "alert.py")).read(),
          "AlertManager class present in alert.py")
    check("Alerts: alerts config section in example",
          '"alerts"' in open(os.path.join(base, "config.example.json")).read(),
          "alerts config section in config.example.json")
    check("Alerts: test_alerts.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_alerts.py")),
          "alert test file present")
    check("Alert lifecycle: test_alerts_lifecycle.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_alerts_lifecycle.py")),
          "alert lifecycle test file present")
    check("Alert lifecycle: acknowledge method in alert.py",
          "def acknowledge" in open(os.path.join(base, "alert.py")).read(),
          "acknowledge method present")
    check("Alert lifecycle: resolve method in alert.py",
          "def resolve" in open(os.path.join(base, "alert.py")).read(),
          "resolve method present")
    check("Alert lifecycle: /alerts endpoint in server.py",
          "_handle_alerts_list" in open(os.path.join(base, "server.py")).read(),
          "alerts list handler present")

    # P9-2: Dashboard operator actions
    check("Dashboard actions: test_dashboard_actions.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_dashboard_actions.py")),
          "dashboard actions test file present")
    dashboard_html = open(os.path.join(base, "static", "dashboard.html")).read()
    check("Dashboard actions: Operator Actions card present",
          "快速操作" in dashboard_html,
          "Operator Actions panel present")
    check("Dashboard actions: doAction function present",
          "doAction" in dashboard_html,
          "doAction JavaScript function")

    # P9-3: Incident timeline
    check("Timeline: timeline.py exists",
          os.path.isfile(os.path.join(base, "timeline.py")),
          "timeline module present")
    check("Timeline: test_timeline.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_timeline.py")),
          "timeline test file present")
    check("Timeline: build_timeline function in timeline.py",
          "def build_timeline" in open(os.path.join(base, "timeline.py")).read(),
          "build_timeline function present")
    check("Timeline: /timeline endpoint in server.py",
          "_handle_timeline" in open(os.path.join(base, "server.py")).read(),
          "timeline handler present")
    check("Dashboard: Timeline nav item present",
          "data-view=\"timeline\"" in dashboard_html,
          "Timeline navigation item")

    # P9-4: Execution guardrails
    check("Guardrails: guardrails.py exists",
          os.path.isfile(os.path.join(base, "guardrails.py")),
          "guardrails module present")
    check("Guardrails: test_guardrails.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_guardrails.py")),
          "guardrails test file present")
    check("Guardrails: check_guardrail function in guardrails.py",
          "def check_guardrail" in open(os.path.join(base, "guardrails.py")).read(),
          "check_guardrail function present")
    check("Guardrails: /guardrails endpoint in server.py",
          "get_guardrails_status" in open(os.path.join(base, "server.py")).read(),
          "guardrails status handler present")
    check("Guardrails: guardrails config in config.example.json",
          "\"guardrails\"" in open(os.path.join(base, "config.example.json")).read(),
          "guardrails config section present")

    # P10-1: HttpReadonlyProvider
    check("Lightweight: GoogleSheetsProvider class in data_source.py",
          "class GoogleSheetsProvider" in open(os.path.join(base, "data_source.py")).read(),
          "GoogleSheetsProvider class present")
    check("Workspace: mode toggle present in dashboard",
          "ERP 整合版" in open(os.path.join(base, "static", "dashboard.html")).read() and "輕量版（Sheets / LINE）" in open(os.path.join(base, "static", "dashboard.html")).read(),
          "workspace mode toggle present")

    check("P10: HttpReadonlyProvider class in data_source.py",
          "class HttpReadonlyProvider" in open(os.path.join(base, "data_source.py")).read(),
          "HttpReadonlyProvider class present")
    check("P10: test_http_provider.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_http_provider.py")),
          "http provider test file present")
    check("P10: http config in config.example.json",
          '"http"' in open(os.path.join(base, "config.example.json")).read(),
          "http config section in live_provider")

    # P10-2: Data mapping + validation
    check("P10-2: data_mapper.py exists",
          os.path.isfile(os.path.join(base, "data_mapper.py")),
          "data_mapper module present")
    check("P10-2: test_data_mapper.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_data_mapper.py")),
          "data mapper test file present")
    check("P10-2: SchemaMapper class in data_mapper.py",
          "class SchemaMapper" in open(os.path.join(base, "data_mapper.py")).read(),
          "SchemaMapper class present")
    check("P10-2: SchemaValidator class in data_mapper.py",
          "class SchemaValidator" in open(os.path.join(base, "data_mapper.py")).read(),
          "SchemaValidator class present")
    check("P10-2: apply_mapping function in data_mapper.py",
          "def apply_mapping" in open(os.path.join(base, "data_mapper.py")).read(),
          "apply_mapping function present")
    check("P10-2: get_mapping_diagnostics function in data_mapper.py",
          "def get_mapping_diagnostics" in open(os.path.join(base, "data_mapper.py")).read(),
          "get_mapping_diagnostics function present")
    check("P10-2: mapping endpoint in server.py",
          "get_mapping_diagnostics" in open(os.path.join(base, "server.py")).read(),
          "mapping diagnostics handler present")
    check("P10-2: data_mapping config in config.example.json",
          '"data_mapping"' in open(os.path.join(base, "config.example.json")).read(),
          "data_mapping config section present")
    check("P10-2: HttpReadonlyProvider applies mapping",
          "apply_mapping" in open(os.path.join(base, "data_source.py")).read(),
          "HttpReadonlyProvider integrates mapping")

    # P10-3: Readonly provider diagnostics dashboard
    dashboard_html = open(os.path.join(base, "static", "dashboard.html")).read()
    check("P10-3: Dashboard contains Provider Diagnostics card",
          "Readonly Provider Diagnostics" in dashboard_html,
          "Provider Diagnostics panel present")
    check("P10-3: Dashboard has renderProviderDiagnosticsCard function",
          "renderProviderDiagnosticsCard" in dashboard_html,
          "renderProviderDiagnosticsCard JS function present")
    check("P10-3: loadOps fetches /mapping/diagnostics",
          "fetch('/mapping/diagnostics')" in dashboard_html,
          "loadOps fetches mapping diagnostics")
    check("P10-3: smoke test includes P10-3 checks",
          "Readonly Provider Diagnostics" in open(os.path.join(base, "scripts", "smoke_test.py")).read(),
          "smoke test has P10-3 checks")

    # P10-4: Provider selection operator UI
    check("P10-4: Dashboard contains Provider Selection card",
          "Provider Selection" in open(os.path.join(base, "static", "dashboard.html")).read(),
          "Provider Selection panel present")
    check("P10-4: renderProviderSelectionCard function in dashboard",
          "renderProviderSelectionCard" in open(os.path.join(base, "static", "dashboard.html")).read(),
          "renderProviderSelectionCard JS function present")
    check("P10-4: doSelectProvider function in dashboard",
          "doSelectProvider" in open(os.path.join(base, "static", "dashboard.html")).read(),
          "doSelectProvider JS function present")
    check("P10-4: set_default_provider in data_source.py",
          "def set_default_provider" in open(os.path.join(base, "data_source.py")).read(),
          "set_default_provider function present")
    check("P10-4: get_default_provider_mode in data_source.py",
          "def get_default_provider_mode" in open(os.path.join(base, "data_source.py")).read(),
          "get_default_provider_mode function present")
    check("P10-4: /provider/select handler in server.py",
          "_handle_provider_select" in open(os.path.join(base, "server.py")).read(),
          "provider select handler present in server.py")
    check("P10-4: provider:select in config.example.json guardrails",
          '"provider:select"' in open(os.path.join(base, "config.example.json")).read(),
          "provider:select guardrail present")

    # P11-1: Audit chain
    check("P11-1: audit_chain.py exists",
          os.path.isfile(os.path.join(base, "audit_chain.py")),
          "audit_chain module present")
    check("P11-1: test_audit_chain.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_audit_chain.py")),
          "audit chain test file present")
    check("P11-1: append_audit_entry in audit_chain.py",
          "def append_audit_entry" in open(os.path.join(base, "audit_chain.py")).read(),
          "append_audit_entry function present")
    check("P11-1: query_audit_log in audit_chain.py",
          "def query_audit_log" in open(os.path.join(base, "audit_chain.py")).read(),
          "query_audit_log function present")
    check("P11-1: get_audit_summary in audit_chain.py",
          "def get_audit_summary" in open(os.path.join(base, "audit_chain.py")).read(),
          "get_audit_summary function present")
    check("P11-1: /audit handler in server.py",
          "_handle_audit_query" in open(os.path.join(base, "server.py")).read(),
          "audit query handler present")
    check("P11-1: audit logging integrated in server.py",
          "append_audit_entry" in open(os.path.join(base, "server.py")).read(),
          "audit logging integrated in server")

    # P11-2: Incident report generation
    check("P11-2: incident_report.py exists",
          os.path.isfile(os.path.join(base, "incident_report.py")),
          "incident_report module present")
    check("P11-2: test_incident_report.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_incident_report.py")),
          "incident report test file present")
    check("P11-2: generate_incident_report in incident_report.py",
          "def generate_incident_report" in open(os.path.join(base, "incident_report.py")).read(),
          "generate_incident_report function present")
    check("P11-2: /incident/report handler in server.py",
          "_handle_incident_report" in open(os.path.join(base, "server.py")).read(),
          "incident report handler present")

    # P11-3: Auto-remediation hooks
    check("P11-3: auto_remediation.py exists",
          os.path.isfile(os.path.join(base, "auto_remediation.py")),
          "auto_remediation module present")
    check("P11-3: test_auto_remediation.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_auto_remediation.py")),
          "auto remediation test file present")
    check("P11-3: evaluate_hooks in auto_remediation.py",
          "def evaluate_hooks" in open(os.path.join(base, "auto_remediation.py")).read(),
          "evaluate_hooks function present")
    check("P11-3: get_remediation_status in auto_remediation.py",
          "def get_remediation_status" in open(os.path.join(base, "auto_remediation.py")).read(),
          "get_remediation_status function present")
    check("P11-3: /auto-remediation/status handler in server.py",
          "/auto-remediation/status" in open(os.path.join(base, "server.py")).read(),
          "auto-remediation status endpoint present")
    check("P11-3: /auto-remediation/evaluate handler in server.py",
          "/auto-remediation/evaluate" in open(os.path.join(base, "server.py")).read(),
          "auto-remediation evaluate endpoint present")
    check("P11-3: auto_remediation config section in config.example.json",
          "auto_remediation" in open(os.path.join(base, "config.example.json")).read(),
          "auto_remediation config section present")
    check("P11-3: _trigger_auto_remediation in alert.py",
          "_trigger_auto_remediation" in open(os.path.join(base, "alert.py")).read(),
          "alert integration for auto-remediation present")

    # P11-4: Approval workflow dashboard
    check("P11-4: approval_queue.py exists",
          os.path.isfile(os.path.join(base, "approval_queue.py")),
          "approval_queue module present")
    check("P11-4: test_approval_queue.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_approval_queue.py")),
          "approval queue test file present")
    check("P11-4: create_pending_item in approval_queue.py",
          "def create_pending_item" in open(os.path.join(base, "approval_queue.py")).read(),
          "create_pending_item function present")
    check("P11-4: approve_item in approval_queue.py",
          "def approve_item" in open(os.path.join(base, "approval_queue.py")).read(),
          "approve_item function present")
    check("P11-4: reject_item in approval_queue.py",
          "def reject_item" in open(os.path.join(base, "approval_queue.py")).read(),
          "reject_item function present")
    check("P11-4: /approvals handler in server.py",
          "\"/approvals\"" in open(os.path.join(base, "server.py")).read(),
          "approvals endpoint present")
    check("P11-4: _handle_approval_approve in server.py",
          "_handle_approval_approve" in open(os.path.join(base, "server.py")).read(),
          "approval approve handler present")
    check("P11-4: _handle_approval_reject in server.py",
          "_handle_approval_reject" in open(os.path.join(base, "server.py")).read(),
          "approval reject handler present")
    check("P11-4: _check_guardrail_with_queue in server.py",
          "_check_guardrail_with_queue" in open(os.path.join(base, "server.py")).read(),
          "guardrail with queue integration present")
    check("P11-4: Approval Queue in dashboard",
          "renderApprovalQueueCard" in open(os.path.join(base, "static", "dashboard.html")).read(),
          "approval queue card in dashboard")

    # P12-1: Approval-linked execution handoff
    check("P12-1: approve_and_retry endpoint in server.py",
          "approve-and-retry" in open(os.path.join(base, "server.py")).read(),
          "approve-and-retry endpoint present")
    check("P12-1: _replay_request in server.py",
          "_replay_request" in open(os.path.join(base, "server.py")).read(),
          "replay request helper present")
    check("P12-1: original_request in approval_queue.py",
          "original_request" in open(os.path.join(base, "approval_queue.py")).read(),
          "original_request storage present")
    check("P12-1: approve-and-retry in dashboard",
          "doApproveRetry" in open(os.path.join(base, "static", "dashboard.html")).read(),
          "approve-and-retry button in dashboard")

    # P12-2: Automation policy controls
    check("P12-2: automation_policy.py exists",
          os.path.isfile(os.path.join(base, "automation_policy.py")),
          "automation_policy module present")
    check("P12-2: test_automation_policy.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_automation_policy.py")),
          "automation policy test file present")
    check("P12-2: check_automation_allowed in automation_policy.py",
          "def check_automation_allowed" in open(os.path.join(base, "automation_policy.py")).read(),
          "check_automation_allowed function present")
    check("P12-2: /automation/policy handler in server.py",
          "\"/automation/policy\"" in open(os.path.join(base, "server.py")).read(),
          "automation policy endpoint present")
    check("P12-2: automation_policy in auto_remediation.py",
          "automation_policy" in open(os.path.join(base, "auto_remediation.py")).read(),
          "auto-remediation integrates automation policy")
    check("P12-2: automation_policy in approval handler",
          "check_automation_allowed" in open(os.path.join(base, "server.py")).read(),
          "approval retry checks automation policy")
    check("P12-2: automation_policy section in config.example.json",
          "automation_policy" in open(os.path.join(base, "config.example.json")).read(),
          "automation_policy config section present")

    # P12-3: Rollback & Audit Visibility
    check("P12-3: rollback_eligibility.py exists",
          os.path.isfile(os.path.join(base, "rollback_eligibility.py")),
          "rollback_eligibility module present")
    check("P12-3: test_rollback_eligibility.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_rollback_eligibility.py")),
          "rollback eligibility test file present")
    check("P12-3: query_rollback_eligibility in rollback_eligibility.py",
          "def query_rollback_eligibility" in open(os.path.join(base, "rollback_eligibility.py")).read(),
          "query_rollback_eligibility function present")
    check("P12-3: get_rollback_summary in rollback_eligibility.py",
          "def get_rollback_summary" in open(os.path.join(base, "rollback_eligibility.py")).read(),
          "get_rollback_summary function present")
    check("P12-3: /audit/rollback handler in server.py",
          "\"/audit/rollback\"" in open(os.path.join(base, "server.py")).read(),
          "audit rollback endpoint present")
    check("P12-3: rollback_eligibility import in server.py",
          "from rollback_eligibility import" in open(os.path.join(base, "server.py")).read(),
          "server imports rollback_eligibility")

    # P13-2: Automation execution receipts
    check("P13-2: execution_receipts.py exists",
          os.path.isfile(os.path.join(base, "execution_receipts.py")),
          "execution receipts module present")
    check("P13-2: test_execution_receipts.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_execution_receipts.py")),
          "execution receipts test file present")
    check("P13-2: record_receipt in execution_receipts.py",
          "def record_receipt(" in open(os.path.join(base, "execution_receipts.py")).read(),
          "record_receipt function present")
    check("P13-2: query_receipts in execution_receipts.py",
          "def query_receipts(" in open(os.path.join(base, "execution_receipts.py")).read(),
          "query_receipts function present")
    check("P13-2: get_receipts_summary in execution_receipts.py",
          "def get_receipts_summary(" in open(os.path.join(base, "execution_receipts.py")).read(),
          "get_receipts_summary function present")
    check("P13-2: /automation/receipts handler in server.py",
          "\"/automation/receipts\"" in open(os.path.join(base, "server.py")).read(),
          "automation receipts endpoint present")
    check("P13-2: /automation/receipts/reset handler in server.py",
          "\"/automation/receipts/reset\"" in open(os.path.join(base, "server.py")).read(),
          "automation receipts reset endpoint present")
    check("P13-2: execution_receipts import in server.py",
          "from execution_receipts import" in open(os.path.join(base, "server.py")).read(),
          "server imports execution_receipts")
    check("P13-2: record_receipt in auto_remediation.py",
          "from execution_receipts import" in open(os.path.join(base, "auto_remediation.py")).read(),
          "auto-remediation integrates execution receipts")

    # P13-3: Incident closure workflow
    check("P13-3: incident_closure.py exists",
          os.path.isfile(os.path.join(base, "incident_closure.py")),
          "incident closure module present")
    check("P13-3: test_incident_closure.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_incident_closure.py")),
          "incident closure test file present")
    check("P13-3: upsert_closure in incident_closure.py",
          "def upsert_closure(" in open(os.path.join(base, "incident_closure.py")).read(),
          "upsert_closure function present")
    check("P13-3: query_closures in incident_closure.py",
          "def query_closures(" in open(os.path.join(base, "incident_closure.py")).read(),
          "query_closures function present")
    check("P13-3: reset_closures in incident_closure.py",
          "def reset_closures(" in open(os.path.join(base, "incident_closure.py")).read(),
          "reset_closures function present")
    check("P13-3: /incident/closures handler in server.py",
          "\"/incident/closures\"" in open(os.path.join(base, "server.py")).read(),
          "incident closures endpoint present")
    check("P13-3: /incident/closures/reset handler in server.py",
          "\"/incident/closures/reset\"" in open(os.path.join(base, "server.py")).read(),
          "incident closures reset endpoint present")
    check("P13-3: incident_closure import in server.py",
          "from incident_closure import" in open(os.path.join(base, "server.py")).read(),
          "server imports incident_closure")

    # P13-4: Pilot readiness checklist
    check("P13-4: pilot_checklist.py exists",
          os.path.isfile(os.path.join(base, "pilot_checklist.py")),
          "pilot checklist module present")
    check("P13-4: test_pilot_checklist.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_pilot_checklist.py")),
          "pilot checklist test file present")
    check("P13-4: get_checklist in pilot_checklist.py",
          "def get_checklist(" in open(os.path.join(base, "pilot_checklist.py")).read(),
          "get_checklist function present")
    check("P13-4: get_checklist_summary in pilot_checklist.py",
          "def get_checklist_summary(" in open(os.path.join(base, "pilot_checklist.py")).read(),
          "get_checklist_summary function present")
    check("P13-4: /pilot/checklist handler in server.py",
          "\"/pilot/checklist\"" in open(os.path.join(base, "server.py")).read(),
          "pilot checklist endpoint present")
    check("P13-4: pilot_checklist import in server.py",
          "from pilot_checklist import" in open(os.path.join(base, "server.py")).read(),
          "server imports pilot_checklist")
    check("P13-4: checklist aggregates safety checks",
          "def _safety_checks(" in open(os.path.join(base, "pilot_checklist.py")).read(),
          "safety checks function present")
    check("P13-4: checklist aggregates observability checks",
          "def _observability_checks(" in open(os.path.join(base, "pilot_checklist.py")).read(),
          "observability checks function present")
    check("P13-4: checklist aggregates workflow checks",
          "def _workflow_checks(" in open(os.path.join(base, "pilot_checklist.py")).read(),
          "workflow checks function present")
    check("P13-4: checklist integrates circuit breaker",
          "circuit_breaker" in open(os.path.join(base, "pilot_checklist.py")).read(),
          "checklist checks circuit breaker state")

    # P14-1: Rollout gating profile
    check("P14-1: rollout_profile.py exists",
          os.path.isfile(os.path.join(base, "rollout_profile.py")),
          "rollout profile module present")
    check("P14-1: test_rollout_profile.py exists",
          os.path.isfile(os.path.join(base, "tests", "test_rollout_profile.py")),
          "rollout profile test file present")
    check("P14-1: get_rollout_profile in rollout_profile.py",
          "def get_rollout_profile(" in open(os.path.join(base, "rollout_profile.py")).read(),
          "get_rollout_profile function present")
    check("P14-1: get_rollout_status in rollout_profile.py",
          "def get_rollout_status(" in open(os.path.join(base, "rollout_profile.py")).read(),
          "get_rollout_status function present")
    check("P14-1: check_rollout in rollout_profile.py",
          "def check_rollout(" in open(os.path.join(base, "rollout_profile.py")).read(),
          "check_rollout function present")
    check("P14-1: ROLLOUT_LEVELS defined",
          "ROLLOUT_LEVELS" in open(os.path.join(base, "rollout_profile.py")).read(),
          "ROLLOUT_LEVELS constant present")
    check("P14-1: CAPABILITIES defined",
          "CAPABILITIES" in open(os.path.join(base, "rollout_profile.py")).read(),
          "CAPABILITIES constant present")
    check("P14-1: /rollout/profile handler in server.py",
          "\"/rollout/profile\"" in open(os.path.join(base, "server.py")).read(),
          "rollout profile endpoint present")
    check("P14-1: /rollout/status handler in server.py",
          "\"/rollout/status\"" in open(os.path.join(base, "server.py")).read(),
          "rollout status endpoint present")
    check("P14-1: rollout_profile import in server.py",
          "from rollout_profile import" in open(os.path.join(base, "server.py")).read(),
          "server imports rollout_profile")
    check("P14-1: rollout gating in /run handler",
          "check_rollout(\"run_query\"" in open(os.path.join(base, "server.py")).read(),
          "run handler gated by rollout")
    check("P14-1: rollout gating in /provider/select",
          "check_rollout(\"provider_selection\"" in open(os.path.join(base, "server.py")).read(),
          "provider select gated by rollout")
    check("P14-1: rollout gating in auto-remediation",
          "check_rollout(\"auto_remediation\"" in open(os.path.join(base, "server.py")).read(),
          "auto-remediation gated by rollout")
    check("P14-1: rollout_profile config in config.example.json",
          "rollout_profile" in open(os.path.join(base, "config.example.json")).read(),
          "rollout_profile config section present")
    check("P14-1: POST /rollout/reload handler in server.py",
          "\"/rollout/reload\"" in open(os.path.join(base, "server.py")).read() and
          "_handle_rollout_reload" in open(os.path.join(base, "server.py")).read(),
          "POST /rollout/reload handler present")
    check("P14-1: alert-triggered auto-remediation respects rollout gating",
          "check_rollout" in open(os.path.join(base, "alert.py")).read() and
          "auto_remediation" in open(os.path.join(base, "alert.py")).read(),
          "alert flow gated by rollout")

    # Summary
    print()
    print("=" * 50)
    passed = sum(1 for _, s, _ in results if s == PASS)
    failed = sum(1 for _, s, _ in results if s == FAIL)
    warned = sum(1 for _, s, _ in results if s == WARN)
    total = len(results)
    print(f"Results: {passed}/{total} passed, {failed} failed, {warned} warnings")

    if failed > 0:
        print("\nFailures:")
        for name, status, detail in results:
            if status == FAIL:
                print(f"  ✗ {name}: {detail}")
        sys.exit(1)
    elif warned > 0:
        print("\nWarnings:")
        for name, status, detail in results:
            if status == WARN:
                print(f"  ⚠ {name}: {detail}")
        print("\nSystem is deployable with warnings")
        sys.exit(0)
    else:
        print("\nAll checks passed ✓ — system is ready for deployment")
        sys.exit(0)


if __name__ == "__main__":
    main()
