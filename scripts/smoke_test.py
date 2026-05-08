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

        # 19. CLI — query execution
        rc, out, err = run_cli(["ORD-1001", "交期風險"])
        check("CLI query execution", rc == 0 and "DECISION REPORT" in out, f"rc={rc}")

        # 20. CLI — data-source flag
        rc, out, err = run_cli(["--data-source", "local", "ORD-1001", "出貨"])
        check("CLI --data-source local", rc == 0 and "mode: local" in out, f"rc={rc}")

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
