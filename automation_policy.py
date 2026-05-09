"""Automation policy controls for limited automation actions.

Config-driven, default-safe, opt-in policy layer that gates which
automation operations are permitted. Applies to:
- auto-remediation hook executions
- approval-linked retry executions

Design:
- Opt-in: disabled by default, zero breaking changes
- Config-driven: allowed_actions list defines what's permitted
- Default-safe: if not configured, only safe actions allowed
- Consistent error shape on denial
- All denials logged to audit chain

Configuration (config.json):
{
  "automation_policy": {
    "enabled": true,
    "allowed_actions": [
      "alerts:reset",
      "config:reload",
      "policy:reload",
      "provider:fallback",
      "approval:retry"
    ],
    "denied_actions": [
      "provider:switch"
    ]
  }
}

Usage:
    from automation_policy import check_automation_allowed, is_automation_enabled

    if check_automation_allowed("alerts:reset"):
        # proceed with action
    else:
        # denied — log audit entry, return error
"""

from config import get_config_value
from audit_chain import append_audit_entry


def is_automation_enabled():
    """Check if automation policy is globally enabled."""
    return get_config_value("automation_policy.enabled", False, raw=True)


def get_allowed_actions():
    """Return the list of allowed automation actions.

    Returns:
        list of action strings, or None if not configured.
    """
    return get_config_value("automation_policy.allowed_actions", raw=True)


def get_denied_actions():
    """Return the list of explicitly denied automation actions.

    Returns:
        list of action strings.
    """
    return get_config_value("automation_policy.denied_actions", [], raw=True)


def check_automation_allowed(action, source_ip=None, context=None):
    """Check if an automation action is permitted by policy.

    Args:
        action: Action identifier (e.g., "alerts:reset", "approval:retry")
        source_ip: Client IP for audit logging
        context: Optional dict with action context for audit

    Returns:
        tuple: (allowed: bool, reason: str or None)
    """
    if not is_automation_enabled():
        # Policy disabled — allow all (backward compatible)
        return True, None

    denied = get_denied_actions()
    if action in denied:
        _log_automation_denied(action, source_ip, context,
                               "Explicitly denied in automation_policy.denied_actions")
        return False, "Action '{}' is denied by automation policy".format(action)

    allowed = get_allowed_actions()
    # If policy is enabled and allowed_actions is configured (even if empty list),
    # require action to be in the list. Empty list means deny-all.
    if allowed is not None:
        if action not in allowed:
            _log_automation_denied(action, source_ip, context,
                                   "Not in automation_policy.allowed_actions list")
            return False, "Action '{}' is not in the allowed automation actions list".format(action)

    return True, None


def _log_automation_denied(action, source_ip, context, reason):
    """Log automation policy denial to audit chain."""
    details = {
        "action": action,
        "policy": "automation_policy",
        "reason": reason,
    }
    if context:
        details["context"] = context
    append_audit_entry(
        action="automation:policy_denied",
        operator="system",
        source_ip=source_ip or "unknown",
        details=details,
        result="denied",
    )


def get_automation_policy_status():
    """Return current automation policy configuration.

    Returns:
        dict with enabled flag, allowed actions, denied actions.
    """
    allowed = get_allowed_actions()
    denied = get_denied_actions()
    return {
        "enabled": is_automation_enabled(),
        "allowed_actions": allowed if allowed is not None else [],
        "denied_actions": denied if denied is not None else [],
    }
