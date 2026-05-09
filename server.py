
import json
import os
import sys
import time
import argparse
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from orchestrator import route_query, batch_queries, extract_order_ids
from integrations.asana_client import post_comment, format_success_report, format_error_report
from audit_logger import log_run, query_runs
from skills.registry import get_registry
from skills.schema import SCHEMA_METADATA
from skills.policy import get_policy, DEFAULT_POLICY, reload_policy, get_reload_metadata
from skills.observability import log_request, log_asana_post
from metrics import compute_metrics
from data_dir_monitor import scan_data_dir, get_data_dir_metadata
from data_source import set_data_source, create_provider, get_provider_name, get_provider_status, get_provider_health, get_degradation_status, get_system_status
from alert import check_alerts, get_alert_manager
from config import (
    get_config,
    get_config_value,
    get_config_metadata,
    reload_config,
    resolve_repo_path,
)

# ─── Access Logger ───────────────────────────────────────────────────────────
_access_log_lock = threading.Lock()
_access_log_file = None
_access_log_enabled = False


def _ensure_access_log(log_dir):
    global _access_log_file, _access_log_enabled
    if _access_log_enabled and _access_log_file is None:
        os.makedirs(log_dir, exist_ok=True)
        _access_log_file = open(os.path.join(log_dir, "access.log"), "a", encoding="utf-8")
        _access_log_enabled = True


def _write_access_log(entry):
    if not _access_log_enabled or _access_log_file is None:
        return
    with _access_log_lock:
        try:
            _access_log_file.write(json.dumps(entry) + "\n")
            _access_log_file.flush()
        except Exception:
            pass

DEFAULT_PORT = 8000
VALID_DATA_SOURCES = ("local", "live", "auto")

# Endpoints that require authentication when a token is configured
_PROTECTED_PATHS = {"/run", "/batch", "/config/reload", "/policy/reload"}


def _check_auth(handler, path):
    """Check if request is authorized.

    Returns True if the request should proceed, False if 401 was sent.
    Only protects mutation endpoints. When no token is configured,
    all requests are allowed (development mode).
    """
    if path not in _PROTECTED_PATHS:
        return True

    token = get_config_value("security.api_token", raw=True)
    if not token:
        return True  # No token configured → dev mode, allow all

    # Check Authorization: Bearer <token>
    auth_header = handler.headers.get("Authorization", "")
    if auth_header.startswith("Bearer ") and auth_header[7:] == token:
        return True

    # Check X-API-Token header
    api_token = handler.headers.get("X-API-Token", "")
    if api_token == token:
        return True

    handler._send_error_response(401, "unauthorized", "Invalid or missing API token")
    return False

class AgentHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default stderr logging to keep test output clean
        pass

    def _send_json_response(self, status_code, data):
        self._status_code = status_code
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

    def _log_access(self, start_time, path, method):
        """Record structured access log entry."""
        if not _access_log_enabled:
            return
        duration_ms = round((time.monotonic() - start_time) * 1000, 1)
        client = self.client_address[0] if self.client_address else "unknown"
        # Try to get run_id from thread-local context if available
        run_id = getattr(self, "_run_id", None)
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "method": method,
            "path": path,
            "status_code": getattr(self, "_status_code", 0),
            "duration_ms": duration_ms,
            "client": client,
        }
        if run_id:
            entry["run_id"] = run_id
        _write_access_log(entry)

    def do_GET(self):
        start = time.monotonic()
        try:
            self._dispatch_get()
        finally:
            self._log_access(start, self.path, "GET")

    def _dispatch_get(self):
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
        elif path == "/config":
            self._handle_config(parsed_path)
        elif path == "/metrics":
            self._handle_metrics()
        elif path == "/data/status":
            self._handle_data_status(parsed_path)
        elif path == "/provider/status":
            self._handle_provider_status(parsed_path)
        elif path == "/provider/health":
            self._handle_provider_health(parsed_path)
        elif path == "/system/degradation-status":
            self._handle_degradation_status(parsed_path)
        elif path == "/system/status":
            self._handle_system_status(parsed_path)
        elif path == "/alerts/log":
            self._handle_alerts_log(parsed_path)
        elif path == "/alerts/reset":
            self._handle_alerts_reset()
        elif path == "/alerts":
            self._handle_alerts_list(parsed_path)
        elif path.startswith("/alerts/"):
            self._handle_alert_detail(path, parsed_path)
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

    def _handle_config(self, parsed_path):
        """Handle GET /config — return active application configuration."""
        try:
            params = parse_qs(parsed_path.query)
            raw = params.get("raw", ["false"])[0].lower() == "true"
            config = get_config(raw=raw)
            self._send_json_response(200, {
                "source": config.get("_source", "default"),
                "config": config,
                "metadata": get_config_metadata(),
            })
        except Exception as e:
            self._send_error_response(500, "internal_error", "Failed to serve config", str(e))

    def _handle_metrics(self):
        """Handle GET /metrics — return computed system statistics."""
        try:
            params = parse_qs(self.path.split("?")[-1] if "?" in self.path else "")
            window = 24
            if "window" in params:
                try:
                    window = int(params["window"][0])
                    if window <= 0:
                        window = 24
                except (ValueError, IndexError):
                    window = 24

            result = compute_metrics(window_hours=window)
            self._send_json_response(200, result)
        except Exception as e:
            self._send_error_response(500, "internal_error", "Failed to compute metrics", str(e))

    def _handle_data_status(self, parsed_path):
        """Handle GET /data/status — return data directory metadata."""
        try:
            params = parse_qs(parsed_path.query)
            data_dir = params.get("data_dir", [None])[0]
            if data_dir is None:
                data_dir = os.path.join(os.path.dirname(__file__), "mock_data")

            metadata = get_data_dir_metadata(data_dir)
            self._send_json_response(200, metadata)
        except Exception as e:
            self._send_error_response(500, "internal_error", "Failed to scan data directory", str(e))

    def _handle_provider_status(self, parsed_path):
        """Handle GET /provider/status — return active provider status."""
        try:
            params = parse_qs(parsed_path.query)
            data_dir = params.get("data_dir", [None])[0]
            if data_dir is None:
                data_dir = os.path.join(os.path.dirname(__file__), "mock_data")

            status = get_provider_status(data_dir)
            self._send_json_response(200, status)
        except Exception as e:
            self._send_error_response(500, "internal_error", "Failed to get provider status", str(e))

    def _handle_provider_health(self, parsed_path):
        """Handle GET /provider/health — return provider health diagnostics."""
        try:
            params = parse_qs(parsed_path.query)
            data_dir = params.get("data_dir", [None])[0]
            if data_dir is None:
                data_dir = os.path.join(os.path.dirname(__file__), "mock_data")

            health = get_provider_health(data_dir)
            self._send_json_response(200, health)
        except Exception as e:
            self._send_error_response(500, "internal_error", "Failed to get provider health", str(e))

    def _handle_degradation_status(self, parsed_path):
        """Handle GET /system/degradation-status — return degraded-mode visibility."""
        try:
            params = parse_qs(parsed_path.query)
            data_dir = params.get("data_dir", [None])[0]
            if data_dir is None:
                data_dir = os.path.join(os.path.dirname(__file__), "mock_data")

            status = get_degradation_status(data_dir)
            self._send_json_response(200, status)
        except Exception as e:
            self._send_error_response(500, "internal_error", "Failed to get degradation status", str(e))

    def _handle_system_status(self, parsed_path):
        """Handle GET /system/status — return aggregated operator-facing system status."""
        try:
            params = parse_qs(parsed_path.query)
            data_dir = params.get("data_dir", [None])[0]
            status = get_system_status(data_dir)

            # Check if we should trigger an alert based on current state
            alert_result = check_alerts(
                system_status=status["system"],
                degradation=status["degradation"],
                health=status["health"],
                provider_status=status["provider"],
            )
            if alert_result:
                status["alert_triggered"] = alert_result

            self._send_json_response(200, status)
        except Exception as e:
            self._send_error_response(500, "internal_error", "Failed to get system status", str(e))

    def _handle_alerts_log(self, parsed_path):
        """Handle GET /alerts/log — return recent alert log entries."""
        try:
            params = parse_qs(parsed_path.query)
            last_n = 10
            if "last" in params:
                try:
                    last_n = int(params["last"][0])
                    if last_n <= 0:
                        last_n = 10
                except (ValueError, IndexError):
                    last_n = 10
            log = get_alert_manager().get_alert_log(last_n)
            self._send_json_response(200, {"total": len(log), "alerts": log})
        except Exception as e:
            self._send_error_response(500, "internal_error", "Failed to get alert log", str(e))

    def _handle_alerts_reset(self):
        """Handle POST /alerts/reset — clear alert cooldown state and log."""
        # Drain any request body
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                self.rfile.read(content_length)
        except Exception:
            pass
        get_alert_manager().reset()
        self._send_json_response(200, {"success": True, "message": "Alert state cleared"})

    def _handle_alerts_list(self, parsed_path):
        """Handle GET /alerts — list all alerts with lifecycle status."""
        try:
            params = parse_qs(parsed_path.query)
            status_filter = params.get("status", [None])[0]

            all_alerts = get_alert_manager().get_all_alerts()
            if status_filter:
                all_alerts = [a for a in all_alerts if a.get("status") == status_filter]

            total = len(all_alerts)
            by_status = {}
            for a in all_alerts:
                s = a.get("status", "unknown")
                by_status[s] = by_status.get(s, 0) + 1

            self._send_json_response(200, {
                "total": total,
                "by_status": by_status,
                "alerts": all_alerts,
            })
        except Exception as e:
            self._send_error_response(500, "internal_error", "Failed to list alerts", str(e))

    def _handle_alert_detail(self, path, parsed_path):
        """Handle GET /alerts/{id} — get a specific alert by ID."""
        try:
            parts = path.strip("/").split("/")
            if len(parts) != 2 or not parts[1].startswith("alert-"):
                self._send_error_response(404, "not_found", "Alert endpoint not found")
                return
            alert_id = parts[1]
            alert = get_alert_manager().find_alert(alert_id)
            if alert is None:
                self._send_error_response(404, "not_found", "Alert not found", {"alert_id": alert_id})
                return
            self._send_json_response(200, alert)
        except Exception as e:
            self._send_error_response(500, "internal_error", "Failed to get alert", str(e))

    def _handle_alert_acknowledge(self, alert_id):
        """Handle POST /alerts/{id}/acknowledge — mark alert as acknowledged."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                self.rfile.read(content_length)
        except Exception:
            pass

        if not alert_id or not alert_id.startswith("alert-"):
            self._send_error_response(400, "invalid_id", "Invalid alert ID format")
            return

        result = get_alert_manager().acknowledge(alert_id)
        if "error" in result:
            status = 404 if result["error"] == "alert_not_found" else 409
            self._send_json_response(status, result)
            return
        self._send_json_response(200, result)

    def _handle_alert_resolve(self, alert_id):
        """Handle POST /alerts/{id}/resolve — mark alert as resolved."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                self.rfile.read(content_length)
        except Exception:
            pass

        if not alert_id or not alert_id.startswith("alert-"):
            self._send_error_response(400, "invalid_id", "Invalid alert ID format")
            return

        result = get_alert_manager().resolve(alert_id)
        if "error" in result:
            status = 404 if result["error"] == "alert_not_found" else 409
            self._send_json_response(status, result)
            return
        self._send_json_response(200, result)

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
        start = time.monotonic()
        try:
            self._dispatch_post()
        finally:
            self._log_access(start, self.path, "POST")

    def _dispatch_post(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        if not _check_auth(self, path):
            self._drain_request_body()
            return

        if path == "/run":
            self._handle_run()
        elif path == "/batch":
            self._handle_batch()
        elif path == "/config/reload":
            self._handle_config_reload()
        elif path == "/policy/reload":
            self._handle_policy_reload()
        elif path == "/alerts/reset":
            self._handle_alerts_reset()
        elif path.endswith("/acknowledge") and path.startswith("/alerts/"):
            alert_id = path.split("/alerts/")[1].split("/acknowledge")[0]
            self._handle_alert_acknowledge(alert_id)
        elif path.endswith("/resolve") and path.startswith("/alerts/"):
            alert_id = path.split("/alerts/")[1].split("/resolve")[0]
            self._handle_alert_resolve(alert_id)
        else:
            self._drain_request_body()
            self._send_error_response(404, "not_found", "Endpoint not found")
            return

    def _handle_config_reload(self):
        """Handle POST /config/reload — reload centralized config file."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            config_path = None
            if content_length > 0:
                body = self.rfile.read(content_length).decode("utf-8")
                payload = json.loads(body)
                config_path = payload.get("config_path")

            result = reload_config(resolve_repo_path(config_path) if config_path else None)
            meta = get_config_metadata()
            self._send_json_response(200, {
                "success": result["success"],
                "source": result["source"],
                "error": result["error"],
                "reloaded_at": result["reloaded_at"],
                "reload_count": meta["reload_count"],
            })
        except (json.JSONDecodeError, ValueError) as e:
            self._send_error_response(400, "invalid_json", f"Request body is not valid JSON: {e}")
        except Exception as e:
            self._send_error_response(500, "internal_error", f"Failed to reload config: {e}")

    def _handle_policy_reload(self):
        """Handle POST /policy/reload — hot-reload policy from config file."""
        try:
            # Read optional body for custom config_path
            content_length = int(self.headers.get("Content-Length", 0))
            config_path = None
            if content_length > 0:
                body = self.rfile.read(content_length).decode("utf-8")
                payload = json.loads(body)
                config_path = payload.get("config_path")

            result = reload_policy(config_path)
            reload_meta = get_reload_metadata()

            self._send_json_response(200, {
                "success": result["success"],
                "source": result["source"],
                "error": result["error"],
                "reloaded_at": result["reloaded_at"],
                "reload_count": reload_meta["reload_count"],
            })
        except (json.JSONDecodeError, ValueError) as e:
            self._send_error_response(400, "invalid_json", f"Request body is not valid JSON: {e}")
        except Exception as e:
            self._send_error_response(500, "internal_error", f"Failed to reload policy: {e}")

    def _handle_run(self):
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
        dry_run = payload.get("dry_run", False)

        if not query:
            self._send_error_response(400, "missing_query", "Request payload must include 'query'")
            return

        self._process_run(query, data_dir, asana_task, payload, dry_run)

    def _handle_batch(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_error_response(400, "invalid_json", f"Request body is not valid JSON: {e}")
            return

        queries = payload.get("queries", [])
        if not queries or not isinstance(queries, list):
            self._send_error_response(400, "missing_queries", "Request payload must include 'queries' list")
            return

        data_dir = payload.get("data_dir", None)
        if data_dir is None:
            data_dir = resolve_repo_path(get_config_value("runtime.default_data_dir", "mock_data"))

        data_source_mode = payload.get("data_source", get_config_value("runtime.default_data_source", "local"))
        if data_source_mode not in VALID_DATA_SOURCES:
            self._send_error_response(400, "invalid_data_source",
                f"Invalid data_source: {data_source_mode}. Must be one of: {list(VALID_DATA_SOURCES)}")
            return
        set_data_source(create_provider(
            data_source_mode,
            cb_threshold=get_config_value("live_provider.circuit_breaker.failure_threshold", 0, raw=True),
            cb_recovery=get_config_value("live_provider.circuit_breaker.recovery_seconds", 60, raw=True),
        ))

        log_request(f"batch:{len(queries)}", "http", data_source=data_source_mode)

        # Dry-run mode: preview routing for each query without executing
        dry_run = payload.get("dry_run", False)
        if dry_run:
            dry_run_results = []
            for q in queries:
                query_text = q if isinstance(q, str) else q.get("query", "")
                order_ids = extract_order_ids(query_text)
                run_id = "dry-run-" + str(time.monotonic_ns())

                matched_team = get_registry().match_team(query_text, order_ids)
                if matched_team:
                    intent = matched_team["intent"]
                    matched = f"team:{matched_team['name']}"
                    steps = [s["skill"] for s in matched_team.get("steps", [])]
                else:
                    matched_skill = get_registry().match_skill(query_text, order_ids)
                    if matched_skill:
                        intent = matched_skill["intent"]
                        matched = matched_skill["name"]
                        steps = [matched_skill["name"]]
                    else:
                        intent = None
                        matched = None
                        steps = []

                dry_run_results.append({
                    "query": query_text,
                    "order_ids": order_ids,
                    "intent": intent,
                    "matched": matched,
                    "steps": steps,
                    "run_id": run_id,
                })

            self._send_json_response(200, {
                "status": "dry_run",
                "dry_run": True,
                "total": len(dry_run_results),
                "results": dry_run_results,
                "data_source": get_provider_name(),
                "message": "Dry run completed — no side effects were committed",
            })
            return

        batch_result = batch_queries(queries, data_dir)

        # Log each batch item
        for item in batch_result["results"]:
            res = item["result"]
            log_run({
                "status": res["status"],
                "query": item["query"],
                "data_dir": data_dir,
                "order_ids": res.get("order_ids", []),
                "intent": res.get("intent"),
                "skill": res.get("skill"),
                "run_id": res.get("run_id"),
                "type": res.get("error_type"),
                "data": {} if res["status"] == "success" else None,
            }, "http")

        self._send_json_response(200, batch_result)

    def _process_run(self, query, data_dir, asana_task, payload, dry_run=False):
        # Resolve data_dir
        if data_dir is None:
            data_dir = resolve_repo_path(get_config_value("runtime.default_data_dir", "mock_data"))

        # Configure data source mode
        data_source_mode = payload.get("data_source", get_config_value("runtime.default_data_source", "local"))
        if data_source_mode not in VALID_DATA_SOURCES:
            self._send_error_response(400, "invalid_data_source",
                f"Invalid data_source: {data_source_mode}. Must be one of: {list(VALID_DATA_SOURCES)}")
            return
        set_data_source(create_provider(
            data_source_mode,
            cb_threshold=get_config_value("live_provider.circuit_breaker.failure_threshold", 0, raw=True),
            cb_recovery=get_config_value("live_provider.circuit_breaker.recovery_seconds", 60, raw=True),
        ))

        # Log request
        log_request(query, "http", data_source=data_source_mode)

        # Dry-run mode: validate and preview routing, but don't execute
        if dry_run:
            order_ids = extract_order_ids(query)
            run_id = "dry-run-" + str(time.monotonic_ns())

            # Skill/Team matching preview
            matched_team = get_registry().match_team(query, order_ids)
            if matched_team:
                intent = matched_team["intent"]
                matched = f"team:{matched_team['name']}"
                steps = [s["skill"] for s in matched_team.get("steps", [])]
            else:
                matched_skill = get_registry().match_skill(query, order_ids)
                if matched_skill:
                    intent = matched_skill["intent"]
                    matched = matched_skill["name"]
                    steps = [matched_skill["name"]]
                else:
                    intent = None
                    matched = None
                    steps = []

            self._send_json_response(200, {
                "status": "dry_run",
                "dry_run": True,
                "run_id": run_id,
                "query": query,
                "order_ids": order_ids,
                "intent": intent,
                "matched": matched,
                "steps": steps,
                "data_source": get_provider_name(),
                "message": "Dry run completed — no side effects were committed",
            })
            return

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

def run_server(port=DEFAULT_PORT, enable_access_log=None, log_dir=None):
    global _access_log_enabled, _access_log_file
    if enable_access_log is None:
        enable_access_log = get_config_value("logging.access_log", False, raw=True)
    if log_dir is None:
        log_dir = resolve_repo_path(get_config_value("paths.log_dir", "logs"))
    
    _access_log_enabled = bool(enable_access_log)
    if _access_log_enabled:
        _ensure_access_log(log_dir)
    
    # Track server uptime for system status endpoint
    get_system_status._uptime_start = time.monotonic()
    
    server_address = ("", port)
    httpd = HTTPServer(server_address, AgentHandler)
    print(f"Agent Server running on port {port}")
    httpd.serve_forever()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manufacturing Agent HTTP server")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", get_config_value("server.port", DEFAULT_PORT))),
        help="Port to listen on",
    )
    args = parser.parse_args()
    run_server(args.port)
