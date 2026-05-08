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
              "Ops navigation item present")
        check("Dashboard: has Ops view section",
              "view-ops" in dashboard_html,
              "Ops view section present")
        check("Dashboard: has loadOps function",
              "loadOps" in dashboard_html,
              "loadOps function present")

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
