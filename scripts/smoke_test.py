"""
Smoke Test Script

Verifies all critical workflows are functional after deployment.
Run with: python3 -m scripts.smoke_test

Tests:
1. All API endpoints respond correctly
2. CLI executes queries without error
3. Dashboard serves HTML
4. Policy endpoint returns config
5. Skills list is complete
6. Team workflows produce results
7. Error handling works for invalid inputs
"""
import json
import os
import sys
import subprocess
import threading
import time
import urllib.request
import urllib.error

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from http.server import HTTPServer
from server import AgentHandler

PASS = "PASS"
FAIL = "FAIL"
results = []


def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((name, status, detail))
    icon = "✓" if condition else "✗"
    msg = f"  {icon} {name}: {status}"
    if detail:
        msg += f" — {detail}"
    print(msg)


def start_server():
    """Start test server on random port."""
    server = HTTPServer(("127.0.0.1", 0), AgentHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    time.sleep(0.1)
    return server, port


def get(path, port):
    """GET request."""
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())


def post(path, port, payload):
    """POST request."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())


def run_cli(args):
    """Run CLI command, return (returncode, stdout, stderr)."""
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "run_agent.py")
    result = subprocess.run(
        [sys.executable, script] + args,
        capture_output=True, text=True,
        timeout=30
    )
    return result.returncode, result.stdout, result.stderr


def main():
    print("Manufacturing Agent System — Smoke Tests")
    print("=" * 50)

    server, port = start_server()

    try:
        # 1. Health endpoint
        data = get("/health", port)
        check("GET /health", data.get("status") == "ok", f"response: {data}")

        # 2. Skills endpoint
        data = get("/skills", port)
        check("GET /skills", data.get("total", 0) >= 9, f"total skills: {data.get('total')}")
        skill_names = [s["name"] for s in data.get("items", [])]
        expected_skills = [
            "schedule-conflict-check", "delivery-risk-analysis",
            "quote-comparison-summary", "sales-response-draft",
            "internal-action-summary", "expedite-options",
            "material-shortage-recovery", "capacity-rebalance",
            "supplier-followup-draft",
        ]
        for s in expected_skills:
            check(f"  Skill: {s}", s in skill_names)

        # 3. Team workflows listed
        teams = [s["name"] for s in data.get("items", []) if s.get("type") == "team"]
        check("Team workflows listed", len(teams) >= 3, f"teams: {teams}")
        check("  Team: team:recovery-planning", "team:recovery-planning" in teams)

        # 4. Schema endpoint
        data = get("/schema", port)
        check("GET /schema", "top_level_shared_fields" in data)

        # 5. Policy endpoint
        data = get("/policy", port)
        check("GET /policy", "policy" in data and "source" in data, f"source: {data.get('source')}")

        # 5b. Config endpoint
        data = get("/config", port)
        check("GET /config", "config" in data and "metadata" in data, f"source: {data.get('source', data.get('config', {}).get('_source'))}")

        # 6. Dashboard endpoint
        req = urllib.request.Request(f"http://127.0.0.1:{port}/")
        req.add_header("Accept", "text/html")
        resp = urllib.request.urlopen(req)
        html = resp.read().decode()
        check("GET / (dashboard)", "<html" in html.lower() or "<!doctype" in html.lower(), f"length: {len(html)} chars")

        # 7. POST /run — single skill
        data = post("/run", port, {"query": "ORD-1001 能不能準時出？"})
        check("POST /run (delivery-risk)", data.get("status") == "success", f"skill: {data.get('skill')}")

        # 8. POST /run — team workflow
        data = post("/run", port, {"query": "ORD-1001 全面分析"})
        check("POST /run (team workflow)", data.get("status") == "success", f"skill: {data.get('skill')}")
        if data.get("status") == "success":
            results_data = data.get("data", {}).get("results", {})
            check("  Team results present", len(results_data) >= 2, f"steps: {list(results_data.keys())}")

        # 8b. POST /run — recovery planning team workflow
        data = post("/run", port, {"query": "ORD-1001 recovery planning"})
        check("POST /run (recovery-planning team)", data.get("status") == "success", f"skill: {data.get('skill')}")
        if data.get("status") == "success":
            results_data = data.get("data", {}).get("results", {})
            expected_steps = {"shortage", "expedite", "capacity", "supplier"}
            check("  Recovery planning steps present", expected_steps.issubset(results_data.keys()), f"steps: {list(results_data.keys())}")

        # 9. POST /run — quote comparison
        data = post("/run", port, {"query": "報價比較"})
        check("POST /run (quote comparison)", data.get("status") == "success", f"skill: {data.get('skill')}")

        # 10. POST /run — expedite options
        data = post("/run", port, {"query": "ORD-1001 加急方案"})
        check("POST /run (expedite-options)", data.get("status") == "success", f"skill: {data.get('skill')}")

        # 11. POST /run — material shortage recovery
        data = post("/run", port, {"query": "ORD-1001 缺料恢復"})
        check("POST /run (material-shortage-recovery)", data.get("status") == "success", f"skill: {data.get('skill')}")

        # 12. POST /run — capacity rebalance
        data = post("/run", port, {"query": "ORD-1001 產能重分配"})
        check("POST /run (capacity-rebalance)", data.get("status") == "success", f"skill: {data.get('skill')}")

        # 13. POST /run — supplier follow-up
        data = post("/run", port, {"query": "ORD-1001 供應商跟進"})
        check("POST /run (supplier-followup-draft)", data.get("status") == "success", f"skill: {data.get('skill')}")

        # 14. POST /run — error handling (missing order)
        try:
            data = post("/run", port, {"query": "準時出貨"})
            check("POST /run (missing order ID)", data.get("status") == "error", f"type: {data.get('error_type')}")
        except urllib.error.HTTPError as e:
            body = json.loads(e.read())
            check("POST /run (missing order ID)", e.code == 400, f"status: {e.code}")

        # 15. POST /run — error handling (unknown intent)
        try:
            data = post("/run", port, {"query": "今天天氣如何？"})
            check("POST /run (unknown intent)", data.get("status") == "error", f"type: {data.get('error_type')}")
        except urllib.error.HTTPError as e:
            body = json.loads(e.read())
            check("POST /run (unknown intent)", e.code == 400, f"status: {e.code}")

        # 16. POST /run — error handling (invalid JSON)
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/run",
                data=b"not json",
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req)
            check("POST /run (invalid JSON)", False, "should have returned 400")
        except urllib.error.HTTPError as e:
            check("POST /run (invalid JSON)", e.code == 400, f"status: {e.code}")

        # 17. History endpoint
        data = get("/history?last=5", port)
        check("GET /history", "runs" in data, f"total: {data.get('total')}")

        # 18. CLI — policy inspection
        rc, out, err = run_cli(["--policy"])
        check("CLI --policy", rc == 0 and "routing" in out, f"rc={rc}")

        # 18b. CLI — config inspection
        rc, out, err = run_cli(["--show-config"])
        check("CLI --show-config", rc == 0 and "Config source:" in out, f"rc={rc}")

        # 18c. Auth — smoke verifies dev mode (no token = no 401 on mutation endpoints)
        url = f"http://127.0.0.1:{port}/run"
        payload = json.dumps({"query": "ORD-1001 出貨"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
                check("Auth dev mode (POST /run no token)", resp.status == 200, f"status={resp.status}")
        except urllib.error.HTTPError as e:
            check("Auth dev mode (POST /run no token)", e.code != 401, f"got {e.code}")

        # 18d. Circuit breaker — verify provider creation with CB params
        from data_source import create_provider, AutoFailoverProvider, CircuitBreaker
        provider = create_provider("auto", cb_threshold=3, cb_recovery=60)
        check("Circuit: create_provider with CB",
              isinstance(provider, AutoFailoverProvider) and provider._circuit is not None,
              f"circuit breaker present: {provider._circuit._failure_threshold=}")
        provider2 = create_provider("auto", cb_threshold=0)
        check("Circuit: create_provider without CB",
              isinstance(provider2, AutoFailoverProvider) and provider2._circuit is None,
              "simple failover mode")

        # 19. CLI — query execution
        rc, out, err = run_cli(["ORD-1001", "交期風險"])
        check("CLI query execution", rc == 0 and "DECISION REPORT" in out, f"rc={rc}")

        # 20. CLI — data-source flag
        rc, out, err = run_cli(["--data-source", "local", "ORD-1001", "出貨"])
        check("CLI --data-source local", rc == 0 and "mode: local" in out, f"rc={rc}")

        # 21. Provider status endpoint
        status_body = get("/provider/status", port)
        check("Provider status endpoint",
              "name" in status_body and "capabilities" in status_body and "readiness" in status_body,
              f"name={status_body.get('name')}, readiness={status_body.get('readiness')}")

        # 22. Provider readiness is valid enum value
        valid_readiness = {"ready", "not_configured", "degraded", "disabled", "circuit_open"}
        check("Provider readiness valid",
              status_body.get("readiness") in valid_readiness,
              f"readiness={status_body.get('readiness')}")

        # 23. Provider health endpoint
        health_body = get("/provider/health", port)
        check("Provider health endpoint",
              "supported" in health_body and "status" in health_body and "details" in health_body,
              f"status={health_body.get('status')}, supported={health_body.get('supported')}")

        # 24. Rollout: local provider enabled
        check("Rollout: local provider enabled",
              status_body.get("readiness") in ("ready", "degraded"),
              f"local readiness={status_body.get('readiness')}")

        # 25. Degradation status endpoint
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/system/degradation-status") as resp:
            deg_body = json.loads(resp.read())
        check("Degradation status endpoint: responds 200",
              resp.status == 200,
              f"status={resp.status}")
        check("Degradation status: has is_degraded field",
              "is_degraded" in deg_body,
              f"keys={list(deg_body.keys())}")
        check("Degradation status: has active_path field",
              "active_path" in deg_body,
              f"active_path={deg_body.get('active_path')}")
        check("Degradation status: has recommendations field",
              "recommendations" in deg_body,
              f"recommendations={deg_body.get('recommendations')}")

        # 26. System status endpoint
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/system/status") as resp:
            sys_body = json.loads(resp.read())
        check("System status endpoint: responds 200",
              resp.status == 200,
              f"status={resp.status}")
        check("System status: has system field",
              sys_body.get("system") in ("ok", "degraded", "unhealthy"),
              f"system={sys_body.get('system')}")
        check("System status: has provider field",
              "provider" in sys_body,
              f"provider present")
        check("System status: has health field",
              "health" in sys_body,
              f"health present")
        check("System status: has degradation field",
              "degradation" in sys_body,
              f"degradation present")
        check("System status: has config field",
              "config" in sys_body,
              f"config present")
        check("System status: has data_dir field",
              "data_dir" in sys_body,
              f"data_dir present")
        check("System status: has timestamp field",
              "timestamp" in sys_body,
              f"timestamp present")

        # 27. Dashboard ops panel
        try:
            dashboard_url = f"http://127.0.0.1:{port}/"
            req = urllib.request.Request(dashboard_url)
            with urllib.request.urlopen(req) as resp:
                html = resp.read().decode()
            check("Dashboard: has Ops nav item",
                  "data-view=\"ops\"" in html,
                  "Ops navigation item present")
            check("Dashboard: has Ops view section",
                  "view-ops" in html,
                  "Ops view section present")
            check("Dashboard: calls loadOps",
                  "loadOps" in html,
                  "loadOps function present")
            check("Dashboard: fetches /system/status",
                  "/system/status" in html,
                  "/system/status fetch present")
        except Exception as e:
            check("Dashboard ops panel", False, str(e))

        # 28. Dry-run: single query
        dry_run_data = json.dumps({
            "query": "ORD-1001 能不能準時出？",
            "dry_run": True,
        }).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/run",
            data=dry_run_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            dr = json.loads(resp.read())
        check("Dry-run: /run returns dry_run status",
              dr.get("status") == "dry_run",
              f"status={dr.get('status')}")
        check("Dry-run: /run extracts order IDs",
              "ORD-1001" in dr.get("order_ids", []),
              f"order_ids={dr.get('order_ids')}")
        check("Dry-run: /run shows routing",
              dr.get("matched") is not None,
              f"matched={dr.get('matched')}")
        check("Dry-run: /run indicates no side effects",
              "no side effects" in dr.get("message", "").lower(),
              f"message={dr.get('message')}")

        # 29. Dry-run: batch
        batch_data = json.dumps({
            "queries": ["ORD-1001 能不能準時出？"],
            "dry_run": True,
        }).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/batch",
            data=batch_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            dr_batch = json.loads(resp.read())
        check("Dry-run: /batch returns dry_run status",
              dr_batch.get("status") == "dry_run",
              f"status={dr_batch.get('status')}")
        check("Dry-run: /batch returns results per query",
              dr_batch.get("total", 0) >= 1,
              f"total={dr_batch.get('total')}")

        # 30. Alerts: log endpoint
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/alerts/log"
        )
        with urllib.request.urlopen(req) as resp:
            alert_log = json.loads(resp.read())
        check("Alerts: /alerts/log responds 200",
              resp.status == 200,
              f"status={resp.status}")
        check("Alerts: /alerts/log has total field",
              "total" in alert_log,
              f"keys={list(alert_log.keys())}")
        check("Alerts: /alerts/log has alerts list",
              isinstance(alert_log.get("alerts"), list),
              f"alerts type={type(alert_log.get('alerts')).__name__}")

        # P9-1: Alert lifecycle endpoints
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/alerts"
        )
        with urllib.request.urlopen(req) as resp:
            alert_list = json.loads(resp.read())
        check("Alert lifecycle: /alerts responds 200",
              resp.status == 200,
              f"status={resp.status}")
        check("Alert lifecycle: /alerts has by_status",
              "by_status" in alert_list,
              f"keys={list(alert_list.keys())}")

        # P9-2: Dashboard operator actions
        dashboard_html = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "dashboard.html")).read()
        check("Dashboard: contains Operator Actions card",
              "Operator Actions" in dashboard_html,
              "Operator Actions panel present")

        # P9-3: Incident timeline
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/timeline"
        )
        with urllib.request.urlopen(req) as resp:
            tl = json.loads(resp.read())
        check("Timeline: /timeline responds 200",
              resp.status == 200,
              f"status={resp.status}")
        check("Timeline: /timeline has events list",
              "events" in tl and isinstance(tl["events"], list),
              f"total={tl.get('total', 0)}")
        check("Timeline: /timeline has summary",
              "summary" in tl,
              "summary text present")
        check("Dashboard: contains Timeline nav item",
              "data-view=\"timeline\"" in dashboard_html,
              "Timeline navigation item present")

        # P9-4: Execution guardrails
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/guardrails"
        )
        with urllib.request.urlopen(req) as resp:
            gr = json.loads(resp.read())
        check("Guardrails: /guardrails responds 200",
              resp.status == 200,
              f"status={resp.status}")
        check("Guardrails: /guardrails has enabled field",
              "enabled" in gr,
              f"keys={list(gr.keys())}")

        # P10-1: HttpReadonlyProvider
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/provider/status"
        )
        with urllib.request.urlopen(req) as resp:
            ps = json.loads(resp.read())
        check("P10: /provider/status responds 200",
              resp.status == 200,
              f"name={ps.get('name', 'unknown')}")

        # P10-2: /mapping/diagnostics responds 200
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/mapping/diagnostics"
        )
        with urllib.request.urlopen(req) as resp:
            mp = json.loads(resp.read())
        check("P10-2: /mapping/diagnostics responds 200",
              resp.status == 200,
              f"enabled={mp.get('enabled')}")
        check("P10-2: diagnostics has datasets field",
              "datasets" in mp,
              f"keys={list(mp.keys())}")
        check("P10-2: diagnostics has runtime_stats field",
              "runtime_stats" in mp,
              f"stats keys={list(mp.get('runtime_stats', {}).keys())}")

        # P10-3: Readonly provider diagnostics dashboard
        dashboard_html = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "dashboard.html")).read()
        check("P10-3: Dashboard contains Provider Diagnostics card",
              "Readonly Provider Diagnostics" in dashboard_html,
              "Provider Diagnostics panel present")
        check("P10-3: Dashboard has renderProviderDiagnosticsCard function",
              "renderProviderDiagnosticsCard" in dashboard_html,
              "renderProviderDiagnosticsCard JS function present")
        check("P10-3: Dashboard fetches /mapping/diagnostics in loadOps",
              "fetch('/mapping/diagnostics')" in dashboard_html,
              "loadOps fetches mapping diagnostics")

        # P10-4: Provider selection operator UI
        check("P10-4: Dashboard contains Provider Selection card",
              "Provider Selection" in dashboard_html,
              "Provider Selection panel present")
        check("P10-4: Dashboard has renderProviderSelectionCard function",
              "renderProviderSelectionCard" in dashboard_html,
              "renderProviderSelectionCard JS function present")
        check("P10-4: Dashboard has doSelectProvider function",
              "doSelectProvider" in dashboard_html,
              "doSelectProvider JS function present")
        check("P10-4: POST /provider/select endpoint available",
              "_handle_provider_select" in open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server.py")).read(),
              "provider select handler present in server.py")

        # P11-1: Audit chain
        audit_res = get("/audit", port)
        check("P11-1: /audit responds 200",
              "entries" in audit_res and "summary" in audit_res,
              f"keys={list(audit_res.keys())}")

    finally:
        server.shutdown()

    # Summary
    print()
    print("=" * 50)
    passed = sum(1 for _, s, _ in results if s == PASS)
    total = len(results)
    failed = total - passed
    print(f"Results: {passed}/{total} passed, {failed} failed")

    if failed > 0:
        print("\nFailures:")
        for name, status, detail in results:
            if status == FAIL:
                print(f"  ✗ {name}: {detail}")
        sys.exit(1)
    else:
        print("\nAll smoke tests passed ✓")
        sys.exit(0)


if __name__ == "__main__":
    main()
