
import json
import os
import sys
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from orchestrator import route_query
from integrations.asana_client import post_comment, format_success_report, format_error_report
from audit_logger import log_run, query_runs
from skills.registry import get_registry
from skills.schema import SCHEMA_METADATA
from skills.policy import get_policy, DEFAULT_POLICY
from skills.observability import log_request, log_asana_post
from data_source import set_data_source, create_provider, get_provider_name

DEFAULT_PORT = 8000
VALID_DATA_SOURCES = ("local", "live", "auto")

class AgentHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default stderr logging to keep test output clean
        pass

    def _send_json_response(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _send_error_response(self, status_code, error_type, message, details=None):
        """Send a consistent error response across all endpoints."""
        body = {
            "status": "error",
            "error_type": error_type,
            "message": message,
        }
        if details is not None:
            body["details"] = details
        self._send_json_response(status_code, body)

    def _drain_request_body(self):
        """Consume any unread POST body bytes before returning an error response."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            content_length = 0
        if content_length > 0:
            self.rfile.read(content_length)

    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        # Dashboard routes
        if path == "/" or path == "/dashboard" or path == "/index.html":
            self._serve_dashboard()
            return
        # Static files
        if path.startswith("/static/"):
            self._serve_static(path)
            return

        # API routes
        if path == "/health":
            self._send_json_response(200, {"status": "ok"})
        elif path == "/history":
            self._handle_history(parsed_path)
        elif path == "/skills":
            self._handle_skills()
        elif path == "/schema":
            self._handle_schema()
        elif path == "/policy":
            self._handle_policy()
        else:
            self._send_error_response(404, "not_found", "Endpoint not found")

    def _serve_dashboard(self):
        """Serve the dashboard HTML."""
        dashboard_path = os.path.join(os.path.dirname(__file__), "static", "dashboard.html")
        try:
            with open(dashboard_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self._send_error_response(500, "internal_error", "Dashboard file not found")

    def _serve_static(self, path):
        """Serve static files (CSS, JS, images)."""
        # Prevent directory traversal
        safe_path = path.replace("..", "")
        file_path = os.path.join(os.path.dirname(__file__), "static", safe_path.lstrip("/"))
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png": "image/png",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
        }

        try:
            if not os.path.isfile(file_path):
                self._send_error_response(404, "not_found", "File not found")
                return

            ext = os.path.splitext(file_path)[1].lower()
            content_type = content_types.get(ext, "application/octet-stream")

            with open(file_path, "rb") as f:
                content = f.read()

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self._send_error_response(500, "internal_error", "Failed to serve static file")

    def _handle_skills(self):
        """Handle GET /skills — return available skills and team workflows."""
        try:
            registry = get_registry()
            items = []

            for skill in registry.skills:
                items.append({
                    "name": skill["name"],
                    "intent": skill["intent"],
                    "type": "skill",
                    "requires_order_id": skill.get("requires_order_id", False),
                    "keywords": skill.get("keywords", []),
                    "exact_keywords": skill.get("exact_keywords", []),
                    "priority": skill.get("priority", 0),
                })

            for team in registry.teams:
                items.append({
                    "name": f"team:{team['name']}",
                    "intent": team["intent"],
                    "type": "team",
                    "requires_order_id": team.get("requires_order_id", False),
                    "keywords": team.get("keywords", []),
                    "exact_keywords": team.get("exact_keywords", []),
                    "priority": team.get("priority", 0),
                    "steps": team.get("steps", []),
                })

            self._send_json_response(200, {
                "total": len(items),
                "items": items,
            })
        except Exception as e:
            self._send_error_response(500, "internal_error", "Failed to list skills", str(e))

    def _handle_schema(self):
        """Handle GET /schema — return unified output schema metadata."""
        try:
            self._send_json_response(200, SCHEMA_METADATA)
        except Exception as e:
            self._send_error_response(500, "internal_error", "Failed to serve schema", str(e))

    def _handle_policy(self):
        """Handle GET /policy — return active policy configuration."""
        try:
            active = get_policy()
            source = active.get("_source", "default")
            self._send_json_response(200, {
                "source": source,
                "policy": {k: v for k, v in active.items() if not k.startswith("_")},
            })
        except Exception as e:
            self._send_error_response(500, "internal_error", "Failed to serve policy", str(e))

    def _handle_history(self, parsed_path):
        """Handle GET /history with optional query parameters for filtering."""
        try:
            params = parse_qs(parsed_path.query)

            # Parameter validation
            last_raw = params.get("last", [10])[0]
            try:
                last_n = int(last_raw)
                if last_n <= 0:
                    self._send_error_response(400, "invalid_parameter", "'last' must be a positive integer")
                    return
            except (ValueError, TypeError):
                self._send_error_response(400, "invalid_parameter", "'last' must be a positive integer")
                return

            status = params.get("status", [None])[0]
            if status is not None and status not in ("success", "error"):
                self._send_error_response(400, "invalid_parameter", "'status' must be 'success' or 'error'")
                return

            channel = params.get("channel", [None])[0]
            if channel is not None and channel not in ("cli", "http"):
                self._send_error_response(400, "invalid_parameter", "'channel' must be 'cli' or 'http'")
                return

            intent = params.get("intent", [None])[0]
            skill = params.get("skill", [None])[0]
            run_id = params.get("run_id", [None])[0]

            runs = query_runs(
                last_n=last_n,
                status=status,
                intent=intent,
                skill=skill,
                channel=channel,
                run_id=run_id,
            )

            self._send_json_response(200, {
                "total": len(runs),
                "filters": {
                    "last": last_n,
                    "status": status,
                    "intent": intent,
                    "skill": skill,
                    "channel": channel,
                },
                "runs": runs,
            })
        except Exception as e:
            self._send_error_response(500, "internal_error", "Failed to query history", str(e))

    def do_POST(self):
        parsed_path = urlparse(self.path)
        if parsed_path.path != "/run":
            self._drain_request_body()
            self._send_error_response(404, "not_found", "Endpoint not found")
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_error_response(400, "invalid_json", f"Request body is not valid JSON: {e}")
            return

        query = payload.get("query", "")
        data_dir = payload.get("data_dir", None)
        asana_task = payload.get("asana_task", None)

        if not query:
            self._send_error_response(400, "missing_query", "Request payload must include 'query'")
            return

        # Resolve data_dir
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(__file__), "mock_data")

        # Configure data source mode
        data_source_mode = payload.get("data_source", "local")
        if data_source_mode not in VALID_DATA_SOURCES:
            self._send_error_response(400, "invalid_data_source",
                f"Invalid data_source: {data_source_mode}. Must be one of: {list(VALID_DATA_SOURCES)}")
            return
        set_data_source(create_provider(data_source_mode))

        # Log request
        log_request(query, "http", data_source=data_source_mode)

        # Route the query
        try:
            result = route_query(query, data_dir)
        except Exception as e:
            # Unexpected internal error
            result = {
                "status": "error",
                "type": "internal_error",
                "details": str(e),
                "query": query,
                "data_dir": data_dir,
                "order_ids": [],
            }

        # Asana Integration
        asana_posted = None
        if asana_task:
            try:
                if result["status"] == "success":
                    comment = format_success_report(result)
                else:
                    comment = format_error_report(result)
                asana_posted = post_comment(asana_task, comment)
                log_asana_post(asana_task, asana_posted, run_id=result.get("run_id"))
            except Exception:
                # Log error but don't fail the agent run
                asana_posted = False
                log_asana_post(asana_task, False, run_id=result.get("run_id"))

        # Return response — consistent shape for both success and error
        response_body = {
            "status": result["status"],
            "run_id": result.get("run_id"),
            "intent": result.get("intent"),
            "order_ids": result.get("order_ids"),
            "asana_task": asana_task,
            "asana_posted": asana_posted,
            "data_source": get_provider_name(),
        }
        
        if result["status"] == "success":
            response_body["data"] = result.get("data")
            status_code = 200
        else:
            error_type = result.get("type", "unknown")
            response_body["error_type"] = error_type
            response_body["error"] = result.get("details")
            # Validation errors are user errors (400), others are 500
            if error_type in ("validation_failed", "missing_order_id", "unknown_intent"):
                status_code = 400
            else:
                status_code = 500

        # Audit Log
        log_run(result, "http", asana_task, asana_posted)

        self._send_json_response(status_code, response_body)

def run_server(port=DEFAULT_PORT):
    server_address = ("", port)
    httpd = HTTPServer(server_address, AgentHandler)
    print(f"Agent Server running on port {port}")
    httpd.serve_forever()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manufacturing Agent HTTP server")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", DEFAULT_PORT)),
        help="Port to listen on",
    )
    args = parser.parse_args()
    run_server(args.port)
