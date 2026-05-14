
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
from data_source import set_data_source, create_provider, get_provider_name, get_provider_status, get_provider_health, get_degradation_status, get_system_status, set_default_provider, get_default_provider_mode
from alert import check_alerts, get_alert_manager
from timeline import build_timeline, timeline_summary
from guardrails import check_guardrail, get_guardrails_status
from data_mapper import get_mapping_diagnostics, reset_mapping_stats
from audit_chain import append_audit_entry, query_audit_log, get_audit_summary, _close_audit_log
from incident_report import generate_incident_report
from auto_remediation import evaluate_hooks, evaluate_all_hooks, get_remediation_status, reset_remediation_state
from approval_queue import create_pending_item, list_pending, get_item, approve_item, reject_item, get_approval_stats, reset_queue, serialize_item_for_api
from automation_policy import check_automation_allowed, get_automation_policy_status
from rollback_eligibility import query_rollback_eligibility, get_rollback_summary
from guardrails import check_guardrail, get_guardrails_status, get_guardrail
from execution_receipts import record_receipt, query_receipts, get_receipts_summary, reset_receipts
from pilot_checklist import get_checklist, get_checklist_summary
from incident_closure import get_closure, query_closures, upsert_closure, reset_closures
from rollout_profile import get_rollout_profile, get_rollout_status, check_rollout, reload_rollout_profile


def _check_guardrail_with_queue(operation, headers, source_ip, details=None,
                                original_request=None):
    """Check guardrail and create a pending approval item if approval is required but token is missing.

    Args:
        operation: Guard label string
        headers: Request headers dict
        source_ip: Client IP for audit
        details: Optional details to attach to pending item
        original_request: Optional dict with the original blocked request for retry

    Returns:
        None if allowed, or dict with error details if denied.
        Also creates a pending approval item when error_type is guardrail_approval_required.
    """
    guard = check_guardrail(operation, headers)
    if guard is None:
        return None  # Allowed

    # If approval was required (not explicitly denied), create a pending item
    if guard.get("error_type") == "guardrail_approval_required":
        guardrail_config = get_guardrail(operation) or {}
        create_pending_item(
            operation=operation,
            source_ip=source_ip,
            details=details or {},
            guardrail_config=guardrail_config,
            original_request=original_request,
        )

    return guard
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


def _close_access_log():
    global _access_log_file
    if _access_log_file is not None:
        try:
            _access_log_file.close()
        except Exception:
            pass
        _access_log_file = None


class ManagedHTTPServer(HTTPServer):
    """HTTP server that cleans up shared log handles when closing."""

    def server_close(self):
        super().server_close()
        _close_access_log()
        _close_audit_log()

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

    def _send_error_response(self, status_code, error_type, message, details=None, explainability=None):
        """Send a consistent error response across all endpoints."""
        body = {
            "status": "error",
            "error_type": error_type,
            "message": message,
        }
        if details is not None:
            body["details"] = details
        if explainability is not None:
            body.update({k: v for k, v in explainability.items() if k not in body})
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
        elif path == "/timeline":
            self._handle_timeline(parsed_path)
        elif path == "/guardrails":
            self._send_json_response(200, get_guardrails_status())
        elif path == "/mapping/diagnostics":
            self._send_json_response(200, get_mapping_diagnostics())
        elif path == "/audit/rollback":
            self._handle_rollback_eligibility(parsed_path)
        elif path == "/audit":
            self._handle_audit_query(parsed_path)
        elif path == "/incident/report":
            self._handle_incident_report(parsed_path)
        elif path == "/incident/closures":
            self._handle_incident_closures(parsed_path)
        elif path.startswith("/incident/closures/"):
            self._handle_incident_closure_detail(path)
        elif path == "/auto-remediation/status":
            self._send_json_response(200, get_remediation_status())
        elif path == "/automation/policy":
            self._send_json_response(200, get_automation_policy_status())
        elif path == "/automation/receipts":
            self._handle_automation_receipts(parsed_path)
        elif path == "/pilot/checklist":
            checklist = get_checklist()
            self._send_json_response(200, {
                "items": checklist,
                "summary": get_checklist_summary(checklist),
            })
        elif path == "/rollout/profile":
            self._send_json_response(200, get_rollout_profile())
        elif path == "/rollout/status":
            self._send_json_response(200, get_rollout_status())
        elif path == "/approvals":
            self._handle_approvals_list(parsed_path)
        elif path.startswith("/approvals/"):
            self._handle_approval_detail(path)
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
        # Guardrail check (creates pending approval item if needed)
        headers = dict(self.headers)
        original_request = {"method": "POST", "path": "/alerts/reset", "body": None}
        guard = _check_guardrail_with_queue("alerts:reset", headers,
                                            self.client_address[0],
                                            details={"endpoint": "/alerts/reset"},
                                            original_request=original_request)
        if guard:
            self._drain_request_body()
            self._send_json_response(403, guard)
            return

        # Drain any request body
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                self.rfile.read(content_length)
        except Exception:
            pass
        get_alert_manager().reset()
        append_audit_entry("alerts:reset", operator="api",
                           source_ip=self.client_address[0],
                           details={}, result="success")
        self._send_json_response(200, {"success": True, "message": "Alert state cleared"})

    def _handle_provider_select(self):
        """Handle POST /provider/select — switch the global default provider mode.

        Expects JSON body: {"mode": "local|live|auto"}
        Guarded by the "provider:select" guardrail (approval-required by default).
        Also gated by rollout profile (provider_selection capability).
        """
        # Read body first for guardrail queue
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = None
            if content_length > 0:
                raw = self.rfile.read(content_length).decode("utf-8")
                body = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            body = None

        # Rollout gating: provider_selection
        rollout = check_rollout("provider_selection", operation="provider:select")
        if not rollout["allowed"]:
            append_audit_entry("provider:select", operator="api",
                               source_ip=self.client_address[0],
                               details={"mode": body.get("mode") if body else "unknown",
                                        "rollout_blocked": True, "rollout_message": rollout["message"]},
                               result="denied")
            self._send_error_response(403, "rollout_gated", rollout["message"],
                                      explainability={"reason": rollout.get("reason", rollout["message"]),
                                                      "next_action": rollout.get("next_action", "Update the rollout profile."),
                                                      "decision_state": rollout.get("decision_state", "rollout_gated"),
                                                      "requires_approval": rollout.get("requires_approval", False)})
            return

        headers = dict(self.headers)
        original_request = {"method": "POST", "path": "/provider/select", "body": body}
        guard = _check_guardrail_with_queue("provider:select", headers,
                                            self.client_address[0],
                                            details={"endpoint": "/provider/select", "body": body},
                                            original_request=original_request)
        if guard:
            append_audit_entry("provider:select", operator="api",
                               source_ip=self.client_address[0],
                               details={"guardrail": True, "mode": body.get("mode") if body else "unknown",
                                        "error_type": guard.get("error_type")},
                               result="denied" if guard.get("error_type") == "guardrail_denied" else "pending_approval")
            self._send_json_response(403, guard)
            return

        # Use already-read body
        if body is None:
            self._send_error_response(400, "missing_body", "Request body is required")
            return

        payload = body
        mode = payload.get("mode")
        if mode not in VALID_DATA_SOURCES:
            append_audit_entry("provider:select", operator="api",
                               source_ip=self.client_address[0],
                               details={"mode": mode, "error": "invalid_mode"}, result="failed")
            self._send_error_response(400, "invalid_mode",
                f"Invalid mode: {mode}. Must be one of: {list(VALID_DATA_SOURCES)}")
            return

        try:
            provider = set_default_provider(mode)
            append_audit_entry("provider:select", operator="api",
                               source_ip=self.client_address[0],
                               details={"mode": mode, "provider_name": provider.name(),
                                        "readiness": provider.readiness()},
                               result="success")
            self._send_json_response(200, {
                "success": True,
                "mode": mode,
                "provider_name": provider.name(),
                "readiness": provider.readiness(),
                "message": f"Default provider switched to {mode}",
            })
        except ValueError as e:
            append_audit_entry("provider:select", operator="api",
                               source_ip=self.client_address[0],
                               details={"mode": mode, "error": str(e)}, result="failed")
            self._send_error_response(400, "provider_error", str(e))
        except Exception as e:
            self._send_error_response(500, "internal_error", f"Failed to switch provider: {e}")

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

    def _handle_timeline(self, parsed_path):
        """Handle GET /timeline — unified incident timeline from all sources."""
        try:
            params = parse_qs(parsed_path.query)
            last_n = 50
            if "last" in params:
                try:
                    last_n = int(params["last"][0])
                except (ValueError, IndexError):
                    pass

            event_type = None
            if "type" in params:
                et = params["type"][0]
                if et in ("run", "alert", "access"):
                    event_type = et

            events = build_timeline(last_n=last_n, event_type=event_type)
            summary = timeline_summary(events)

            self._send_json_response(200, {
                "total": len(events),
                "events": events,
                "summary": summary,
            })
        except Exception as e:
            self._send_error_response(500, "internal_error", "Failed to build timeline", str(e))

    def _handle_audit_query(self, parsed_path):
        """Handle GET /audit — query the operator audit chain.

        Query params:
            action: Filter by action type (e.g., "config:reload")
            result: Filter by result ("success", "denied", "failed")
            last: Max entries to return (default 50)
            offset: Skip first N entries (default 0)
        """
        try:
            params = parse_qs(parsed_path.query)
            action_filter = params.get("action", [None])[0]
            result_filter = params.get("result", [None])[0]
            last = int(params.get("last", ["50"])[0])
            offset = int(params.get("offset", ["0"])[0])

            result = query_audit_log(limit=last, action_filter=action_filter,
                                     result_filter=result_filter, offset=offset)
            summary = get_audit_summary()

            self._send_json_response(200, {
                "entries": result["entries"],
                "total": result["total"],
                "summary": summary,
            })
        except Exception as e:
            self._send_error_response(500, "internal_error", "Failed to query audit log", str(e))

    def _handle_rollback_eligibility(self, parsed_path):
        """Handle GET /audit/rollback — rollback eligibility analysis.

        Query params:
            category: Filter by category (e.g., "guarded_operation")
            eligible: Filter by eligibility (true/false)
            last: Max entries to return (default 50)
            offset: Skip first N entries (default 0)
        """
        try:
            params = parse_qs(parsed_path.query)
            category_filter = params.get("category", [None])[0]
            eligible_raw = params.get("eligible", [None])[0]
            eligible_filter = None
            if eligible_raw == "true":
                eligible_filter = True
            elif eligible_raw == "false":
                eligible_filter = False
            last = int(params.get("last", ["50"])[0])
            offset = int(params.get("offset", ["0"])[0])

            result = query_rollback_eligibility(
                limit=last, category_filter=category_filter,
                eligible_filter=eligible_filter, offset=offset)

            self._send_json_response(200, result)
        except Exception as e:
            self._send_error_response(500, "internal_error", "Failed to analyze rollback eligibility", str(e))

    def _handle_automation_receipts(self, parsed_path):
        """Handle GET /automation/receipts — query execution receipts.

        Query params:
            source: Filter by source ("approval-retry" or "auto-remediation")
            status: Filter by status string
            operation: Filter by operation name
            limit: Max receipts to return (default 20)
            offset: Skip first N receipts (default 0)
        """
        try:
            params = parse_qs(parsed_path.query)
            source = params.get("source", [None])[0]
            status = params.get("status", [None])[0]
            operation = params.get("operation", [None])[0]
            limit = int(params.get("limit", ["20"])[0])
            offset = int(params.get("offset", ["0"])[0])

            result = query_receipts(
                source=source, status=status, operation=operation,
                limit=limit, offset=offset)
            result["summary"] = get_receipts_summary()

            self._send_json_response(200, result)
        except Exception as e:
            self._send_error_response(500, "internal_error", "Failed to query execution receipts", str(e))

    def _handle_incident_report(self, parsed_path):
        """Handle GET /incident/report — generate an incident report.

        Query params:
            window_minutes: Time window for data aggregation (default 60)
        """
        try:
            params = parse_qs(parsed_path.query)
            window = int(params.get("window_minutes", ["60"])[0])

            report = generate_incident_report(window_minutes=window)
            self._send_json_response(200, report)
        except Exception as e:
            self._send_error_response(500, "internal_error", "Failed to generate incident report", str(e))

    def _handle_incident_closures(self, parsed_path):
        """Handle GET /incident/closures — list incident closure records."""
        try:
            params = parse_qs(parsed_path.query)
            status = params.get("status", [None])[0]
            limit = int(params.get("limit", ["20"])[0])
            offset = int(params.get("offset", ["0"])[0])
            self._send_json_response(200, query_closures(status=status, limit=limit, offset=offset))
        except Exception as e:
            self._send_error_response(500, "internal_error", "Failed to query incident closures", str(e))

    def _handle_incident_closure_detail(self, path):
        """Handle GET /incident/closures/{report_id} — return one closure record."""
        report_id = path.split("/incident/closures/")[1].split("/")[0]
        if not report_id or report_id == "reset":
            self._send_error_response(404, "not_found", "Incident closure not found")
            return

        record = get_closure(report_id)
        if record is None:
            self._send_error_response(404, "incident_closure_not_found", "Incident closure not found")
            return

        self._send_json_response(200, record)

    def _handle_incident_closure_upsert(self, report_id):
        """Handle POST /incident/closures/{report_id} — create or update closure state."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            payload = {}
            if content_length > 0:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (json.JSONDecodeError, ValueError) as e:
            self._send_error_response(400, "invalid_json", f"Request body is not valid JSON: {e}")
            return

        result = upsert_closure(
            report_id=report_id,
            status=payload.get("status"),
            updated_by=payload.get("updated_by", "operator"),
            resolution_note=payload.get("resolution_note"),
            linked_alert_ids=payload.get("linked_alert_ids"),
            linked_receipt_ids=payload.get("linked_receipt_ids"),
        )
        if "error" in result:
            if result["error"] in ("invalid_report_id", "invalid_status", "resolution_note_required"):
                self._send_json_response(400, result)
            elif result["error"] == "invalid_transition":
                self._send_json_response(409, result)
            else:
                self._send_json_response(500, result)
            return

        self._send_json_response(200, result)

    def _handle_incident_closures_reset(self):
        """Handle POST /incident/closures/reset — clear closure workflow state."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                self.rfile.read(content_length)
        except Exception:
            pass

        reset_closures()
        self._send_json_response(200, {
            "success": True,
            "message": "Incident closures cleared",
        })

    def _handle_auto_remediation_evaluate(self):
        """Handle POST /auto-remediation/evaluate — trigger auto-remediation.

        Expects optional JSON body: {"trigger": "circuit_breaker_open", "context": {...}}
        If no trigger specified, evaluates all hooks.
        Gated by rollout profile (auto_remediation capability).
        """
        # Drain any request body
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                body = self.rfile.read(content_length).decode("utf-8")
                payload = json.loads(body)
            else:
                payload = {}
        except (json.JSONDecodeError, ValueError):
            payload = {}

        # Rollout gating: auto_remediation
        rollout = check_rollout("auto_remediation", operation="auto_remediation:evaluate")
        if not rollout["allowed"]:
            self._send_error_response(403, "rollout_gated", rollout["message"],
                                      explainability={"reason": rollout.get("reason", rollout["message"]),
                                                      "next_action": rollout.get("next_action", "Update the rollout profile."),
                                                      "decision_state": rollout.get("decision_state", "rollout_gated"),
                                                      "requires_approval": rollout.get("requires_approval", False)})
            return

        trigger = payload.get("trigger")
        context = payload.get("context", {})
        context["source_ip"] = self.client_address[0]

        if trigger:
            results = evaluate_hooks(trigger=trigger, context=context)
        else:
            results = evaluate_all_hooks(context=context)

        self._send_json_response(200, {
            "evaluated": len(results),
            "results": results,
        })

    def _handle_auto_remediation_reset(self):
        """Handle POST /auto-remediation/reset — reset remediation state."""
        # Drain any request body
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                self.rfile.read(content_length)
        except Exception:
            pass

        reset_remediation_state()
        append_audit_entry("auto_remediation", operator="api",
                           source_ip=self.client_address[0],
                           details={"operation": "reset_state"}, result="success")
        self._send_json_response(200, {
            "success": True,
            "message": "Auto-remediation state reset",
        })

    def _handle_rollout_reload(self):
        """Handle POST /rollout/reload — reload rollout profile from file.

        Reloads the rollout profile from rollout_profile.json if present,
        otherwise falls back to default profile.
        """
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                self.rfile.read(content_length)
        except Exception:
            pass

        result = reload_rollout_profile()
        status = 200 if result.get("success") else 400
        append_audit_entry("rollout:reload", operator="api",
                           source_ip=self.client_address[0],
                           details={"success": result.get("success"),
                                    "source": result.get("source")},
                           result="success" if result.get("success") else "failed")
        self._send_json_response(status, result)

    def _handle_automation_receipts_reset(self):
        """Handle POST /automation/receipts/reset — clear execution receipts."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                self.rfile.read(content_length)
        except Exception:
            pass

        reset_receipts()
        self._send_json_response(200, {
            "success": True,
            "message": "Execution receipts cleared",
        })

    def _handle_approvals_list(self, parsed_path):
        """Handle GET /approvals — list approval queue items.

        Query params:
            status: Filter by status (pending, approved, rejected, expired)
            limit: Max items to return (default 50)
        """
        try:
            params = parse_qs(parsed_path.query)
            status_filter = params.get("status", [None])[0]
            limit = int(params.get("limit", ["50"])[0])

            items = list_pending(status_filter=status_filter, limit=limit)
            stats = get_approval_stats()

            self._send_json_response(200, {
                "total": len(items),
                "stats": stats,
                "items": [serialize_item_for_api(item) for item in items],
            })
        except Exception as e:
            self._send_error_response(500, "internal_error", "Failed to list approvals", str(e))

    def _handle_approval_detail(self, path):
        """Handle GET /approvals/{id} — return one approval item with replay preview."""
        approval_id = path.split("/approvals/")[1].split("/")[0]
        if not approval_id or approval_id == "reset":
            self._send_error_response(404, "not_found", "Approval item not found")
            return

        item = get_item(approval_id)
        if item is None:
            self._send_error_response(404, "approval_not_found", "Approval item not found")
            return

        self._send_json_response(200, serialize_item_for_api(item))

    def _handle_approval_approve(self, approval_id):
        """Handle POST /approvals/{id}/approve — approve a pending item."""
        # Drain any request body
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                body = self.rfile.read(content_length).decode("utf-8")
                payload = json.loads(body)
            else:
                payload = {}
        except (json.JSONDecodeError, ValueError):
            payload = {}

        approved_by = payload.get("approved_by", "operator")
        approval_token = payload.get("approval_token")

        result = approve_item(approval_id, approved_by=approved_by, approval_token=approval_token)
        if "error" in result:
            status = 404 if result["error"] == "approval_not_found" else 409
            self._send_json_response(status, result)
            return

        append_audit_entry("approval:approved", operator=approved_by,
                           source_ip=self.client_address[0],
                           details={"approval_id": approval_id, "operation": result.get("operation")},
                           result="success")
        self._send_json_response(200, result)

    def _handle_approval_approve_and_retry(self, approval_id):
        """Handle POST /approvals/{id}/approve-and-retry — approve and re-execute blocked request.

        Approves the pending item, then replays the original blocked operation
        with the approval token injected into headers.
        """
        # Drain any request body
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                body = self.rfile.read(content_length).decode("utf-8")
                payload = json.loads(body)
            else:
                payload = {}
        except (json.JSONDecodeError, ValueError):
            payload = {}

        approved_by = payload.get("approved_by", "operator")
        approval_token = payload.get("approval_token", "approved-via-queue-{}".format(approval_id))

        # Step 1: Approve the item
        result = approve_item(approval_id, approved_by=approved_by, approval_token=approval_token)
        if "error" in result:
            status = 404 if result["error"] == "approval_not_found" else 409
            self._send_json_response(status, result)
            return

        append_audit_entry("approval:approved", operator=approved_by,
                           source_ip=self.client_address[0],
                           details={"approval_id": approval_id, "operation": result.get("operation"),
                                    "retry": True},
                           result="success")

        # Step 2: Check automation policy before retry
        allowed, policy_reason = check_automation_allowed(
            "approval:retry", source_ip=self.client_address[0],
            context={"approval_id": approval_id, "operation": result.get("operation")})
        if not allowed:
            record_receipt(
                source="approval-retry",
                operation=result.get("operation", "unknown"),
                status="policy_denied",
                approval_id=approval_id,
                details={"policy_reason": policy_reason},
            )
            response = {
                "approval": result,
                "retry": {"success": False, "error": "policy_denied", "reason": policy_reason},
            }
            self._send_json_response(200, response)
            return

        # Step 3: Replay the original request if available
        original = result.get("original_request")
        retry_result = None
        receipt_status = "success"
        if original and original.get("method") and original.get("path"):
            try:
                retry_result = self._replay_request(original, approval_token)
                if retry_result.get("status_code", 200) >= 400:
                    receipt_status = "failed"
            except Exception as e:
                retry_result = {"error": "retry_failed", "message": str(e)}
                receipt_status = "error"
        else:
            receipt_status = "skipped"

        # Record execution receipt
        record_receipt(
            source="approval-retry",
            operation=result.get("operation", "unknown"),
            status=receipt_status,
            approval_id=approval_id,
            details={"retry_result": retry_result} if retry_result else None,
        )

        response = {
            "approval": result,
            "retry": retry_result,
        }
        self._send_json_response(200, response)

    def _replay_request(self, original_request, approval_token):
        """Re-execute a blocked request with approval token injected.

        Args:
            original_request: dict with "method", "path", "body"
            approval_token: Token to inject into X-Approval-Token header

        Returns:
            dict with retry result (status_code, body).
        """
        import urllib.request
        import urllib.error

        method = original_request.get("method", "POST")
        path = original_request.get("path", "")
        body = original_request.get("body")

        url = "http://127.0.0.1:{}{}".format(self.server.server_address[1], path)

        headers = {
            "Content-Type": "application/json",
            "X-Approval-Token": approval_token,
        }

        data = json.dumps(body).encode("utf-8") if body else None

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_body = json.loads(resp.read().decode("utf-8"))
                return {
                    "status_code": resp.status,
                    "success": True,
                    "body": resp_body,
                }
        except urllib.error.HTTPError as e:
            resp_body = e.read().decode("utf-8")
            try:
                resp_body = json.loads(resp_body)
            except Exception:
                pass
            return {
                "status_code": e.code,
                "success": False,
                "body": resp_body,
            }

    def _handle_approval_reject(self, approval_id):
        """Handle POST /approvals/{id}/reject — reject a pending item."""
        # Drain any request body
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                body = self.rfile.read(content_length).decode("utf-8")
                payload = json.loads(body)
            else:
                payload = {}
        except (json.JSONDecodeError, ValueError):
            payload = {}

        reason = payload.get("reason", "")
        rejected_by = payload.get("rejected_by", "operator")

        result = reject_item(approval_id, reason=reason, rejected_by=rejected_by)
        if "error" in result:
            status = 404 if result["error"] == "approval_not_found" else 409
            self._send_json_response(status, result)
            return

        self._send_json_response(200, result)

    def _handle_approvals_reset(self):
        """Handle POST /approvals/reset — clear approval queue."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                self.rfile.read(content_length)
        except Exception:
            pass

        reset_queue()
        self._send_json_response(200, {
            "success": True,
            "message": "Approval queue cleared",
        })

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
        elif path == "/rollout/reload":
            self._handle_rollout_reload()
        elif path == "/alerts/reset":
            self._handle_alerts_reset()
        elif path.endswith("/acknowledge") and path.startswith("/alerts/"):
            alert_id = path.split("/alerts/")[1].split("/acknowledge")[0]
            self._handle_alert_acknowledge(alert_id)
        elif path.endswith("/resolve") and path.startswith("/alerts/"):
            alert_id = path.split("/alerts/")[1].split("/resolve")[0]
            self._handle_alert_resolve(alert_id)
        elif path == "/provider/select":
            self._handle_provider_select()
        elif path == "/auto-remediation/evaluate":
            self._handle_auto_remediation_evaluate()
        elif path == "/auto-remediation/reset":
            self._handle_auto_remediation_reset()
        elif path == "/automation/receipts/reset":
            self._handle_automation_receipts_reset()
        elif path == "/incident/closures/reset":
            self._handle_incident_closures_reset()
        elif path.startswith("/incident/closures/"):
            report_id = path.split("/incident/closures/")[1]
            self._handle_incident_closure_upsert(report_id)
        elif path.startswith("/approvals/") and path.endswith("/approve"):
            approval_id = path.split("/approvals/")[1].split("/approve")[0]
            self._handle_approval_approve(approval_id)
        elif path.startswith("/approvals/") and path.endswith("/approve-and-retry"):
            approval_id = path.split("/approvals/")[1].split("/approve-and-retry")[0]
            self._handle_approval_approve_and_retry(approval_id)
        elif path.startswith("/approvals/") and path.endswith("/reject"):
            approval_id = path.split("/approvals/")[1].split("/reject")[0]
            self._handle_approval_reject(approval_id)
        elif path == "/approvals/reset":
            self._handle_approvals_reset()
        else:
            self._drain_request_body()
            self._send_error_response(404, "not_found", "Endpoint not found")
            return

    def _handle_config_reload(self):
        """Handle POST /config/reload — reload centralized config file."""
        # Read body first for guardrail queue
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = None
            if content_length > 0:
                raw = self.rfile.read(content_length).decode("utf-8")
                body = json.loads(raw)
            config_path = body.get("config_path") if body else None
        except (json.JSONDecodeError, ValueError) as e:
            config_path = None
            body = None

        # Guardrail check (creates pending approval item if needed)
        headers = dict(self.headers)
        original_request = {"method": "POST", "path": "/config/reload", "body": body}
        guard = _check_guardrail_with_queue("config:reload", headers,
                                            self.client_address[0],
                                            details={"endpoint": "/config/reload", "config_path": config_path},
                                            original_request=original_request)
        if guard:
            result_label = "denied" if guard.get("error_type") == "guardrail_denied" else "pending_approval"
            append_audit_entry("config:reload", operator="api",
                               source_ip=self.client_address[0],
                               details={"guardrail": True, "error_type": guard.get("error_type")},
                               result=result_label)
            self._send_json_response(403, guard)
            return

        try:
            result = reload_config(resolve_repo_path(config_path) if config_path else None)
            meta = get_config_metadata()
            append_audit_entry("config:reload", operator="api",
                               source_ip=self.client_address[0],
                               details={"config_path": config_path, "source": result.get("source")},
                               result="success" if result.get("success") else "failed")
            self._send_json_response(200, {
                "success": result["success"],
                "source": result["source"],
                "error": result["error"],
                "reloaded_at": result["reloaded_at"],
                "reload_count": meta["reload_count"],
            })
        except (json.JSONDecodeError, ValueError) as e:
            append_audit_entry("config:reload", operator="api",
                               source_ip=self.client_address[0],
                               details={"error": str(e)}, result="failed")
            self._send_error_response(400, "invalid_json", f"Request body is not valid JSON: {e}")
        except Exception as e:
            append_audit_entry("config:reload", operator="api",
                               source_ip=self.client_address[0],
                               details={"error": str(e)}, result="failed")
            self._send_error_response(500, "internal_error", f"Failed to reload config: {e}")

    def _handle_policy_reload(self):
        """Handle POST /policy/reload — hot-reload policy from config file."""
        # Read body first for guardrail queue
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = None
            if content_length > 0:
                raw = self.rfile.read(content_length).decode("utf-8")
                body = json.loads(raw)
            config_path = body.get("config_path") if body else None
        except (json.JSONDecodeError, ValueError):
            config_path = None
            body = None

        # Guardrail check (creates pending approval item if needed)
        headers = dict(self.headers)
        original_request = {"method": "POST", "path": "/policy/reload", "body": body}
        guard = _check_guardrail_with_queue("policy:reload", headers,
                                            self.client_address[0],
                                            details={"endpoint": "/policy/reload", "config_path": config_path},
                                            original_request=original_request)
        if guard:
            result_label = "denied" if guard.get("error_type") == "guardrail_denied" else "pending_approval"
            append_audit_entry("policy:reload", operator="api",
                               source_ip=self.client_address[0],
                               details={"guardrail": True, "error_type": guard.get("error_type")},
                               result=result_label)
            self._send_json_response(403, guard)
            return

        try:
            result = reload_policy(config_path)
            reload_meta = get_reload_metadata()

            append_audit_entry("policy:reload", operator="api",
                               source_ip=self.client_address[0],
                               details={"config_path": config_path, "source": result.get("source")},
                               result="success" if result.get("success") else "failed")

            self._send_json_response(200, {
                "success": result["success"],
                "source": result["source"],
                "error": result["error"],
                "reloaded_at": result["reloaded_at"],
                "reload_count": reload_meta["reload_count"],
            })
        except (json.JSONDecodeError, ValueError) as e:
            append_audit_entry("policy:reload", operator="api",
                               source_ip=self.client_address[0],
                               details={"error": str(e)}, result="failed")
            self._send_error_response(400, "invalid_json", f"Request body is not valid JSON: {e}")
        except Exception as e:
            append_audit_entry("policy:reload", operator="api",
                               source_ip=self.client_address[0],
                               details={"error": str(e)}, result="failed")
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

        # Rollout gating: run_query
        op = "run:dry_run" if dry_run else "run:query"
        rollout = check_rollout("run_query", operation=op)
        if not rollout["allowed"]:
            self._send_error_response(403, "rollout_gated", rollout["message"],
                                      explainability={"reason": rollout.get("reason", rollout["message"]),
                                                      "next_action": rollout.get("next_action", "Update the rollout profile."),
                                                      "decision_state": rollout.get("decision_state", "rollout_gated"),
                                                      "requires_approval": rollout.get("requires_approval", False)})
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

def create_server(port=DEFAULT_PORT, enable_access_log=None, log_dir=None):
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
    return ManagedHTTPServer(server_address, AgentHandler)


def run_server(port=DEFAULT_PORT, enable_access_log=None, log_dir=None):
    httpd = create_server(port=port, enable_access_log=enable_access_log, log_dir=log_dir)
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
