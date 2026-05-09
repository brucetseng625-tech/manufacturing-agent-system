"""Execution guardrails for mutation-capable operator actions.

Config-driven protection layer that gates write operations behind
allow/deny rules and optional approval requirements.

Guardrails are additive: by default (no config), all operations are allowed.
This preserves backward compatibility with existing deployments.

Guard labels:
  - "alerts:reset"   — POST /alerts/reset
  - "config:reload"  — POST /config/reload
  - "policy:reload"  — POST /policy/reload
"""

from config import get_config_value


# Default: no guardrails, all operations allowed (backward compatible)
_DEFAULT_GUARDRAILS = {
    "enabled": False,
    "operations": {},
}


def get_guardrail(operation):
    """Get the guardrail config for a specific operation.

    Args:
        operation: Guard label string (e.g. "alerts:reset").

    Returns:
        dict with guard settings, or empty dict if no guard configured.
    """
    enabled = get_config_value("guardrails.enabled", False)
    if not enabled:
        return None  # Guardrails disabled globally

    ops = get_config_value("guardrails.operations", {})
    if not ops or operation not in ops:
        return None  # No specific guard for this operation

    return ops[operation]


def check_guardrail(operation, headers=None):
    """Check if an operation is allowed under current guardrail config.

    Args:
        operation: Guard label string (e.g. "alerts:reset").
        headers: Request headers dict (for approval token extraction).

    Returns:
        None if allowed, or dict with error details if denied.
        Keys: "error", "error_type", "operation", "reason"
    """
    guard = get_guardrail(operation)
    if guard is None:
        return None  # No guardrail applies — allowed

    # Check if operation is explicitly denied
    if guard.get("denied", False):
        return {
            "error": f"Operation '{operation}' is denied by guardrail",
            "error_type": "guardrail_denied",
            "operation": operation,
            "reason": "Operation is explicitly denied in guardrails config",
        }

    # Check if approval is required
    if guard.get("require_approval", False):
        # Look for approval token in headers
        approval_token = None
        if headers:
            approval_token = headers.get("X-Approval-Token") or headers.get("x-approval-token")

        # Check config for expected approval token
        expected = get_config_value("guardrails.approval_token", "")
        if expected and approval_token != expected:
            return {
                "error": f"Operation '{operation}' requires approval token",
                "error_type": "guardrail_approval_required",
                "operation": operation,
                "reason": "X-Approval-Token header is missing or invalid",
            }

    return None  # Allowed


def get_guardrails_status():
    """Return current guardrails configuration summary.

    Returns:
        dict with enabled status and per-operation guard settings.
    """
    enabled = get_config_value("guardrails.enabled", False)
    ops = get_config_value("guardrails.operations", {})

    status = {"enabled": enabled, "operations": {}}
    for op_name, op_config in (ops or {}).items():
        status["operations"][op_name] = {
            "denied": op_config.get("denied", False),
            "require_approval": op_config.get("require_approval", False),
        }

    return status
