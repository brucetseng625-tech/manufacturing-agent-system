"""P14-1 Rollout Gating Profile — centralized rollout policy surface.

Defines per-capability rollout levels and enforces gating across:
- /run queries
- Team workflows
- Provider selection
- Approval-linked execution
- Auto-remediation actions

Design:
- Single rollout profile with per-capability levels
- Levels: disabled, internal_only, pilot_readonly, pilot_with_approval, limited_automation
- Read-only query surface + gating enforcement functions
- Integrates with existing guardrails, automation_policy, approval_queue
- No new state — uses in-memory defaults with optional config file override

Usage:
    from rollout_profile import check_rollout, get_rollout_profile, get_rollout_status
"""

import json
import os
import time

# ─── Constants ───────────────────────────────────────────────────────────────

ROLLOUT_LEVELS = [
    "disabled",
    "internal_only",
    "pilot_readonly",
    "pilot_with_approval",
    "limited_automation",
]

CAPABILITIES = [
    "run_query",
    "team_workflows",
    "provider_selection",
    "approval_linked_execution",
    "auto_remediation",
]

DEFAULT_LEVEL = "internal_only"


# ─── Default Rollout Profile ────────────────────────────────────────────────

DEFAULT_ROLLOUT_PROFILE = {
    "version": "1.0",
    "global_level": "internal_only",
    "capabilities": {
        "run_query": "limited_automation",
        "team_workflows": "limited_automation",
        "provider_selection": "internal_only",
        "approval_linked_execution": "pilot_with_approval",
        "auto_remediation": "pilot_readonly",
    },
    "description": "Default rollout profile — safe for internal pilot testing.",
}


# ─── State ───────────────────────────────────────────────────────────────────

_active_profile = dict(DEFAULT_ROLLOUT_PROFILE)
_profile_source = "default"


def _load_profile_from_file(config_path=None):
    """Load rollout profile from config file if it exists."""
    if config_path is None:
        repo_root = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(repo_root, "rollout_profile.json")

    # Deep copy defaults to avoid mutation
    profile = {
        "version": DEFAULT_ROLLOUT_PROFILE["version"],
        "global_level": DEFAULT_ROLLOUT_PROFILE["global_level"],
        "capabilities": dict(DEFAULT_ROLLOUT_PROFILE["capabilities"]),
        "description": DEFAULT_ROLLOUT_PROFILE["description"],
    }

    if os.path.isfile(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            override = json.load(f)
        if "global_level" in override:
            gl = override["global_level"]
            if gl in ROLLOUT_LEVELS:
                profile["global_level"] = gl
        if "capabilities" in override and isinstance(override["capabilities"], dict):
            for cap in CAPABILITIES:
                if cap in override["capabilities"]:
                    lvl = override["capabilities"][cap]
                    if lvl in ROLLOUT_LEVELS:
                        profile["capabilities"][cap] = lvl
                    else:
                        profile["capabilities"][cap] = DEFAULT_LEVEL
        return profile, f"file:{config_path}"
    return dict(DEFAULT_ROLLOUT_PROFILE), "default"


# Load profile at import time
_active_profile, _profile_source = _load_profile_from_file()


# ─── Public API ──────────────────────────────────────────────────────────────

def get_rollout_profile():
    """Return the current active rollout profile."""
    return {
        "version": _active_profile["version"],
        "global_level": _active_profile["global_level"],
        "capabilities": dict(_active_profile["capabilities"]),
        "source": _profile_source,
    }


def get_capability_level(capability):
    """Return the rollout level for a specific capability.

    Falls back to global_level if the capability is not explicitly configured.
    """
    if capability not in CAPABILITIES:
        return None
    cap_level = _active_profile["capabilities"].get(capability)
    if cap_level is None:
        return _active_profile["global_level"]
    return cap_level


def is_allowed(capability, required_level):
    """Check if a capability is allowed at the required rollout level.

    A capability is allowed if its current level >= required_level
    in the rollout hierarchy.

    Hierarchy (low → high):
      disabled < internal_only < pilot_readonly < pilot_with_approval < limited_automation
    """
    current = get_capability_level(capability)
    if current is None:
        return False
    if current == "disabled":
        return False
    current_idx = ROLLOUT_LEVELS.index(current)
    required_idx = ROLLOUT_LEVELS.index(required_level)
    return current_idx >= required_idx


def check_rollout(capability, operation=None):
    """Enforce rollout gating for a capability.

    Returns dict with:
        - allowed: bool
        - capability: str
        - current_level: str
        - operation: str or None
        - message: str — human-readable gating message

    If not allowed, the message explains which gating rule blocked it.
    """
    current_level = get_capability_level(capability)
    if current_level is None:
        return {
            "allowed": False,
            "capability": capability,
            "current_level": "unknown",
            "operation": operation,
            "message": f"Unknown capability '{capability}' — rollout gating denies by default",
            "reason": f"Unknown capability '{capability}' — rollout gating denies by default",
            "decision_state": "rollout_gated",
            "next_action": "Verify the capability name or update the rollout profile.",
            "requires_approval": False,
            "gating_rule": "unknown_capability",
        }

    if current_level == "disabled":
        return {
            "allowed": False,
            "capability": capability,
            "current_level": current_level,
            "operation": operation,
            "message": f"Capability '{capability}' is disabled in rollout profile — all operations blocked",
            "reason": f"Capability '{capability}' is disabled in rollout profile",
            "decision_state": "rollout_gated",
            "next_action": "Update the rollout profile to a level that enables this capability.",
            "requires_approval": False,
            "gating_rule": "disabled",
        }

    # Check if the capability meets the minimum for the operation
    op_required = _operation_required_level(operation)
    if op_required and not is_allowed(capability, op_required):
        return {
            "allowed": False,
            "capability": capability,
            "current_level": current_level,
            "operation": operation,
            "message": (
                f"Capability '{capability}' at level '{current_level}' "
                f"does not meet required level '{op_required}' for operation '{operation}'"
            ),
            "reason": f"Current level '{current_level}' is insufficient for operation '{operation}' (requires '{op_required}')",
            "decision_state": "rollout_gated",
            "next_action": f"Update rollout profile to at least '{op_required}' or use a supported operation.",
            "requires_approval": False,
            "gating_rule": "level_insufficient",
        }

    return {
        "allowed": True,
        "capability": capability,
        "current_level": current_level,
        "operation": operation,
        "message": f"Capability '{capability}' is allowed at level '{current_level}'",
        "gating_rule": None,
    }


def get_rollout_status():
    """Return full rollout status for operator visibility.

    Returns dict with:
        - profile: current rollout profile
        - capabilities: per-capability status with allowed/level/message
        - global_level: string
        - checked_at: timestamp
    """
    caps = {}
    for cap in CAPABILITIES:
        result = check_rollout(cap)
        caps[cap] = {
            "level": result["current_level"],
            "allowed": result["allowed"],
            "message": result["message"],
        }

    return {
        "profile": get_rollout_profile(),
        "capabilities": caps,
        "global_level": _active_profile["global_level"],
        "checked_at": _timestamp(),
    }


def reload_rollout_profile(config_path=None):
    """Reload rollout profile from file.

    Returns dict with success status.
    """
    global _active_profile, _profile_source  # noqa: PLW0603
    try:
        profile, source = _load_profile_from_file(config_path)
        _active_profile = profile
        _profile_source = source
        return {"success": True, "source": source, "profile": profile}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Operation → Required Level Mapping ─────────────────────────────────────

def _operation_required_level(operation):
    """Map an operation name to its minimum required rollout level.

    Operations that mutate or automate require higher levels.
    """
    if operation is None:
        return None

    # Mutation / automation operations require at least pilot_with_approval
    mutation_ops = {
        "provider:select",
        "auto_remediation:execute",
        "auto_remediation:evaluate",
        "approval:approve",
        "approval:retry",
    }

    # Read-only operations only need internal_only
    readonly_ops = {
        "run:dry_run",
        "run:query",
        "provider:status",
        "health:check",
    }

    if operation in mutation_ops:
        return "pilot_with_approval"
    if operation in readonly_ops:
        return "internal_only"

    # Default: unknown operations require pilot_with_approval (safe default)
    return "pilot_with_approval"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _timestamp():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
