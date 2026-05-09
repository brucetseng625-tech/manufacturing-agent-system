"""Auto-remediation hooks for system state changes.

Config-driven, opt-in automation that triggers safe internal operations
when specific alert conditions are detected. All actions are low-risk and
designed to be reversible.

Design principles:
- Opt-in: disabled by default, zero breaking changes
- Config-driven: hooks defined in config.json
- Cooldown: per-hook cooldown prevents action spam
- Dry-run: each hook supports dry_run mode for safe testing
- Audit: every execution (real or dry-run) logged to audit chain
- Read-only: no high-risk external writes

Supported triggers:
  - circuit_breaker_open
  - system_unhealthy
  - degradation_detected
  - provider_degraded

Supported actions:
  - alerts:reset      — Clear alert cooldown state
  - config:reload     — Reload configuration from disk
  - policy:reload     — Reload policy from config
  - provider:fallback — Suggest fallback (dry-run only, no auto-switch)

Usage:
    from auto_remediation import evaluate_hooks, get_remediation_status

    # Automatic evaluation (called from alert system)
    results = evaluate_hooks(trigger="circuit_breaker_open", context={...})

    # Manual evaluation via API
    results = evaluate_all_hooks()

    # Status inspection
    status = get_remediation_status()
"""

import json
import time
import threading
import urllib.request
import urllib.error

from config import get_config_value
from audit_chain import append_audit_entry
from automation_policy import check_automation_allowed, is_automation_enabled
from execution_receipts import record_receipt

# ─── Constants ───────────────────────────────────────────────────────────────

SUPPORTED_TRIGGERS = {
    "circuit_breaker_open",
    "system_unhealthy",
    "degradation_detected",
    "provider_degraded",
}

SUPPORTED_ACTIONS = {
    "alerts:reset",
    "config:reload",
    "policy:reload",
    "provider:fallback",
}

DEFAULT_COOLDOWN_SECONDS = 120
MAX_EXECUTION_HISTORY = 50

# ─── Module State ────────────────────────────────────────────────────────────

_lock = threading.Lock()
_last_execution = {}  # hook_name -> last_execution_timestamp
_execution_history = []  # list of execution records


# ─── Config Loading ─────────────────────────────────────────────────────────

def _is_enabled():
    """Check if auto-remediation is globally enabled."""
    return get_config_value("auto_remediation.enabled", False, raw=True)


def _get_hooks():
    """Load hook definitions from config.

    Returns dict of {hook_name: hook_config}.
    """
    hooks = get_config_value("auto_remediation.hooks", {}, raw=True)
    if not isinstance(hooks, dict):
        return {}
    return hooks


def _get_hook(hook_name):
    """Get a specific hook definition by name."""
    hooks = _get_hooks()
    return hooks.get(hook_name)


# ─── Cooldown Management ────────────────────────────────────────────────────

def _check_cooldown(hook_name, cooldown_seconds):
    """Check if a hook is still in cooldown.

    Returns True if the hook can execute (cooldown expired or never ran).
    Returns False if still in cooldown.
    """
    now = time.time()
    with _lock:
        last = _last_execution.get(hook_name, 0)
        if now - last < cooldown_seconds:
            return False
        return True


def _record_execution(hook_name):
    """Record that a hook was executed (for cooldown tracking)."""
    with _lock:
        _last_execution[hook_name] = time.time()


# ─── Execution History ──────────────────────────────────────────────────────

def _add_to_history(record):
    """Add an execution record to the history buffer."""
    with _lock:
        _execution_history.append(record)
        if len(_execution_history) > MAX_EXECUTION_HISTORY:
            _execution_history[:] = _execution_history[-MAX_EXECUTION_HISTORY:]


def get_execution_history(limit=20):
    """Return recent execution history.

    Args:
        limit: Max entries to return (default 20).

    Returns:
        list of execution records, newest first.
    """
    with _lock:
        return list(reversed(_execution_history[-limit:]))


# ─── Action Handlers ────────────────────────────────────────────────────────

def _action_alerts_reset(dry_run=False):
    """Reset alert cooldown state and log.

    Args:
        dry_run: If True, only log what would happen.

    Returns:
        dict with success status and details.
    """
    if dry_run:
        return {
            "action": "alerts:reset",
            "dry_run": True,
            "would_execute": True,
            "message": "Would reset alert cooldown state and clear alert log",
        }

    from alert import get_alert_manager
    get_alert_manager().reset()
    return {
        "action": "alerts:reset",
        "dry_run": False,
        "success": True,
        "message": "Alert state cleared",
    }


def _action_config_reload(dry_run=False):
    """Reload configuration from disk.

    Args:
        dry_run: If True, only log what would happen.

    Returns:
        dict with success status and details.
    """
    if dry_run:
        return {
            "action": "config:reload",
            "dry_run": True,
            "would_execute": True,
            "message": "Would reload configuration from config.json",
        }

    from config import reload_config
    result = reload_config()
    return {
        "action": "config:reload",
        "dry_run": False,
        "success": result.get("success", False),
        "source": result.get("source", "unknown"),
        "message": result.get("error", "Config reloaded"),
    }


def _action_policy_reload(dry_run=False):
    """Reload policy from config.

    Args:
        dry_run: If True, only log what would happen.

    Returns:
        dict with success status and details.
    """
    if dry_run:
        return {
            "action": "policy:reload",
            "dry_run": True,
            "would_execute": True,
            "message": "Would reload policy from config",
        }

    from skills.policy import reload_policy
    result = reload_policy()
    return {
        "action": "policy:reload",
        "dry_run": False,
        "success": result.get("success", False),
        "source": result.get("source", "unknown"),
        "message": result.get("error", "Policy reloaded"),
    }


def _action_provider_fallback(dry_run=False):
    """Suggest fallback provider (read-only, never auto-switches).

    Args:
        dry_run: Always treated as dry-run for this action.

    Returns:
        dict with suggestion details.
    """
    from data_source import get_provider_status, get_degradation_status
    provider = get_provider_status()
    degradation = get_degradation_status()

    return {
        "action": "provider:fallback",
        "dry_run": True,
        "success": True,
        "message": "Fallback suggestion only — no provider switch performed",
        "current_provider": provider.get("name", "unknown"),
        "current_readiness": provider.get("readiness", "unknown"),
        "degradation": degradation.get("reason", ""),
        "recommendations": degradation.get("recommendations", []),
    }


# Action dispatch table
_ACTION_HANDLERS = {
    "alerts:reset": _action_alerts_reset,
    "config:reload": _action_config_reload,
    "policy:reload": _action_policy_reload,
    "provider:fallback": _action_provider_fallback,
}


# ─── Hook Evaluation ────────────────────────────────────────────────────────

def _execute_hook(hook_name, hook_config, trigger, context=None):
    """Execute a single remediation hook.

    Args:
        hook_name: Name of the hook (for audit/history).
        hook_config: Hook configuration dict.
        trigger: The trigger event that caused this evaluation.
        context: Optional context dict with system state info.

    Returns:
        dict with execution result.
    """
    action = hook_config.get("action", "")
    dry_run = hook_config.get("dry_run", False)
    cooldown = hook_config.get("cooldown_seconds", DEFAULT_COOLDOWN_SECONDS)

    # Validate action
    if action not in SUPPORTED_ACTIONS:
        record_receipt(
            source="auto-remediation",
            operation=action,
            status="skipped",
            trigger=trigger,
            hook=hook_name,
            details={"reason": "unsupported_action"},
        )
        return {
            "hook": hook_name,
            "trigger": trigger,
            "action": action,
            "status": "skipped",
            "reason": f"Unsupported action: {action}",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    # Check cooldown
    if not _check_cooldown(hook_name, cooldown):
        record_receipt(
            source="auto-remediation",
            operation=action,
            status="cooldown",
            trigger=trigger,
            hook=hook_name,
            details={"reason": "in_cooldown"},
        )
        return {
            "hook": hook_name,
            "trigger": trigger,
            "action": action,
            "status": "cooldown",
            "reason": f"Hook still in cooldown ({cooldown}s)",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    # Check automation policy
    if is_automation_enabled():
        allowed, policy_reason = check_automation_allowed(
            action, source_ip="127.0.0.1",
            context={"hook": hook_name, "trigger": trigger})
        if not allowed:
            record_receipt(
                source="auto-remediation",
                operation=action,
                status="policy_denied",
                trigger=trigger,
                hook=hook_name,
                details={"policy_reason": policy_reason},
            )
            return {
                "hook": hook_name,
                "trigger": trigger,
                "action": action,
                "status": "policy_denied",
                "reason": policy_reason,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

    # Execute the action
    handler = _ACTION_HANDLERS.get(action)
    if handler is None:
        record_receipt(
            source="auto-remediation",
            operation=action,
            status="error",
            trigger=trigger,
            hook=hook_name,
            details={"reason": "no_handler"},
        )
        return {
            "hook": hook_name,
            "trigger": trigger,
            "action": action,
            "status": "error",
            "reason": f"No handler for action: {action}",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    try:
        result = handler(dry_run=dry_run)
        status = "executed" if not dry_run else "dry_run"

        # Record execution for cooldown
        _record_execution(hook_name)

        # Build audit details
        audit_details = {
            "hook": hook_name,
            "trigger": trigger,
            "action": action,
            "dry_run": dry_run,
            "context": context or {},
        }
        if "success" in result:
            audit_details["action_success"] = result["success"]

        # Log to audit chain
        append_audit_entry(
            action="auto_remediation",
            operator="system",
            source_ip="127.0.0.1",
            details=audit_details,
            result=status,
        )

        # Add to execution history
        record = {
            "hook": hook_name,
            "trigger": trigger,
            "action": action,
            "status": status,
            "dry_run": dry_run,
            "action_result": result,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _add_to_history(record)

        # Record execution receipt
        record_receipt(
            source="auto-remediation",
            operation=action,
            status=status,
            trigger=trigger,
            hook=hook_name,
            details={"dry_run": dry_run, "result": result.get("message", "")},
        )

        return {
            "hook": hook_name,
            "trigger": trigger,
            "action": action,
            "status": status,
            "dry_run": dry_run,
            "result": result,
            "timestamp": record["timestamp"],
        }

    except Exception as e:
        error_result = {
            "hook": hook_name,
            "trigger": trigger,
            "action": action,
            "status": "error",
            "reason": str(e),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        # Log error to audit chain
        append_audit_entry(
            action="auto_remediation",
            operator="system",
            source_ip="127.0.0.1",
            details={"hook": hook_name, "trigger": trigger, "action": action, "error": str(e)},
            result="failed",
        )

        # Record error receipt
        record_receipt(
            source="auto-remediation",
            operation=action,
            status="error",
            trigger=trigger,
            hook=hook_name,
            details={"error": str(e)},
        )

        _add_to_history(error_result)
        return error_result


def evaluate_hooks(trigger, context=None):
    """Evaluate all hooks matching a specific trigger.

    This is the primary entry point called from the alert system when
    a state change is detected.

    Args:
        trigger: Alert type string (e.g., "circuit_breaker_open").
        context: Optional dict with system state info for audit logging.

    Returns:
        list of execution results for matching hooks.
    """
    if not _is_enabled():
        return []

    hooks = _get_hooks()
    results = []

    for hook_name, hook_config in hooks.items():
        hook_trigger = hook_config.get("trigger", "")
        if hook_trigger != trigger:
            continue

        # Validate trigger
        if trigger not in SUPPORTED_TRIGGERS:
            continue

        result = _execute_hook(hook_name, hook_config, trigger, context)
        results.append(result)

    return results


def evaluate_all_hooks(context=None):
    """Evaluate all configured hooks regardless of trigger.

    Used for manual testing or API-triggered evaluation.

    Args:
        context: Optional dict with system state info.

    Returns:
        list of execution results for all hooks.
    """
    if not _is_enabled():
        return []

    hooks = _get_hooks()
    results = []

    for hook_name, hook_config in hooks.items():
        trigger = hook_config.get("trigger", "manual")
        if trigger not in SUPPORTED_TRIGGERS:
            # For manual evaluation, allow any trigger
            trigger = "manual"

        result = _execute_hook(hook_name, hook_config, trigger, context)
        results.append(result)

    return results


# ─── Status & Diagnostics ───────────────────────────────────────────────────

def get_remediation_status():
    """Return current auto-remediation configuration and state.

    Returns:
        dict with:
            enabled: bool
            hooks: dict of hook configs
            execution_history: recent execution records
            cooldown_state: current cooldown status per hook
    """
    hooks = _get_hooks()
    now = time.time()

    cooldown_state = {}
    for hook_name, hook_config in hooks.items():
        cooldown = hook_config.get("cooldown_seconds", DEFAULT_COOLDOWN_SECONDS)
        with _lock:
            last = _last_execution.get(hook_name, 0)
        remaining = max(0, cooldown - (now - last)) if last > 0 else 0
        cooldown_state[hook_name] = {
            "cooldown_seconds": cooldown,
            "remaining_seconds": round(remaining, 1),
            "ready": remaining == 0,
        }

    return {
        "enabled": _is_enabled(),
        "hooks": hooks,
        "cooldown_state": cooldown_state,
        "execution_history": get_execution_history(limit=10),
        "supported_triggers": sorted(SUPPORTED_TRIGGERS),
        "supported_actions": sorted(SUPPORTED_ACTIONS),
    }


def reset_remediation_state():
    """Reset all cooldowns and execution history.

    Used for testing or operator-initiated state reset.
    """
    with _lock:
        _last_execution.clear()
        _execution_history.clear()

    append_audit_entry(
        action="auto_remediation",
        operator="api",
        source_ip="127.0.0.1",
        details={"operation": "reset_state"},
        result="success",
    )
