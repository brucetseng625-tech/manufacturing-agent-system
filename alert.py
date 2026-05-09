"""Alert/notification hooks for system state changes.

Sends webhook notifications when the system enters degraded, unhealthy,
or critical states. Includes cooldown logic to prevent alert spam.
"""

import json
import time
import threading
from config import get_config_value


class AlertManager:
    """Manages alert cooldown and dispatch for system state changes."""

    def __init__(self):
        self._lock = threading.Lock()
        self._last_alert = {}  # alert_type -> last_sent_timestamp
        self._alert_log = []  # recent alerts for verification

    def check_and_notify(self, system_status, degradation, health, provider_status):
        """Evaluate system state and send alert if threshold crossed.

        Args:
            system_status: Overall system status string (ok/degraded/unhealthy)
            degradation: Degradation status dict from get_degradation_status()
            health: Health check dict from get_provider_health()
            provider_status: Provider status dict

        Returns:
            dict with alert details if sent, None if no alert triggered
        """
        if not get_config_value("alerts.enabled", False):
            return None

        webhook_url = get_config_value("alerts.webhook_url", "")
        if not webhook_url:
            return None

        cooldown = get_config_value("alerts.cooldown_seconds", 300)
        alert_info = self._evaluate(system_status, degradation, health, provider_status)
        if alert_info is None:
            return None

        # Check cooldown
        alert_type = alert_info["type"]
        now = time.time()
        with self._lock:
            last = self._last_alert.get(alert_type, 0)
            if now - last < cooldown:
                return None  # Still in cooldown
            self._last_alert[alert_type] = now

        # Send webhook
        payload = self._build_payload(alert_info, degradation, health, provider_status)
        success = self._send_webhook(webhook_url, payload)

        # Log alert
        with self._lock:
            self._alert_log.append({
                "type": alert_type,
                "severity": alert_info["severity"],
                "sent": success,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
            # Keep last 100 entries
            if len(self._alert_log) > 100:
                self._alert_log = self._alert_log[-100:]

        return {"sent": success, "alert": payload}

    def _evaluate(self, system_status, degradation, health, provider_status):
        """Determine if an alert should be triggered."""
        health_status = health.get("status", "unknown")
        is_degraded = degradation.get("is_degraded", False)
        readiness = provider_status.get("readiness", "unknown")

        # Critical: system unhealthy or provider disabled
        if system_status == "unhealthy" or readiness == "disabled":
            return {
                "type": "system_unhealthy",
                "severity": "critical",
                "reason": f"System status: {system_status}, provider readiness: {readiness}",
            }

        # Warning: system degraded or circuit breaker open
        if is_degraded:
            cb = degradation.get("circuit_breaker")
            if cb and cb.get("state") == "open":
                return {
                    "type": "circuit_breaker_open",
                    "severity": "warning",
                    "reason": degradation.get("reason", "Circuit breaker tripped"),
                }

            if health_status in ("degraded", "not_configured"):
                return {
                    "type": "degradation_detected",
                    "severity": "warning",
                    "reason": degradation.get("reason", "System operating in degraded mode"),
                }

        return None

    def _build_payload(self, alert_info, degradation, health, provider_status):
        """Build the webhook alert payload."""
        return {
            "event": "system_alert",
            "alert_type": alert_info["type"],
            "severity": alert_info["severity"],
            "reason": alert_info["reason"],
            "system": {
                "provider": provider_status.get("name"),
                "readiness": provider_status.get("readiness"),
                "health_status": health.get("status"),
                "degraded": degradation.get("is_degraded"),
                "active_path": degradation.get("active_path"),
            },
            "recommendations": degradation.get("recommendations", []),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def _send_webhook(self, url, payload):
        """Send alert payload to webhook URL.

        Uses stdlib urllib to avoid external dependencies.
        Returns True if HTTP 2xx, False otherwise.
        """
        import urllib.request
        import urllib.error
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return 200 <= resp.status < 300
        except Exception:
            return False

    def get_alert_log(self, last_n=10):
        """Return recent alert log entries."""
        with self._lock:
            return list(self._alert_log[-last_n:])

    def reset(self):
        """Clear cooldown state and alert log."""
        with self._lock:
            self._last_alert.clear()
            self._alert_log.clear()


# Module-level singleton
_alert_manager = AlertManager()


def get_alert_manager():
    """Get the global alert manager singleton."""
    return _alert_manager


def check_alerts(system_status, degradation, health, provider_status):
    """Convenience function: evaluate system state and trigger alert if needed.

    This is the primary entry point called from server.py during
    /system/status requests or periodic health checks.

    Returns alert info dict if sent, None otherwise.
    """
    return _alert_manager.check_and_notify(
        system_status, degradation, health, provider_status
    )
