"""
Configurable Rules / Policy Layer

Centralizes hardcoded thresholds, routing weights, escalation rules,
and decision criteria that were previously scattered across skills.

Architecture:
1. DEFAULT_POLICY contains all built-in defaults (preserves current behavior)
2. load_policy() merges DEFAULT_POLICY with a JSON config file if found
3. get_policy() returns the active policy (thread-local)
4. Skills import get_policy() and read thresholds from it

Config file location: policies/active.json (relative to repo root)
Fallback: If no file exists, DEFAULT_POLICY is used as-is.

Design principles:
- Minimal: only expose knobs that actually need tuning
- Backward compatible: defaults exactly match current hardcoded behavior
- Per-skill/team overrides: policy structure supports future extension
- Zero external dependencies: stdlib json + threading only
"""
import json
import os
import threading

_local = threading.local()

# All hardcoded thresholds from the current codebase, collected here.
# Changing these values changes behavior without touching skill code.
DEFAULT_POLICY = {
    "version": "1.0",
    "description": "Default policy — matches all current hardcoded behavior.",

    # === Routing ===
    # From skills/registry.py match_skill() and match_team()
    "routing": {
        "exact_keyword_weight": 5,       # +5 for exact keyword match
        "keyword_weight": 2,             # +2 for partial keyword match
        "multi_order_boost": 3,          # +3 for multi-order fallback
        "tie_breaker": "priority_then_registration_order",
    },

    # === Delivery Risk Decision Thresholds ===
    # From skills/delivery_risk.py decision logic
    "delivery_risk": {
        "at_risk_blocker_max": 2,        # <= 2 blockers → at_risk, > 2 → cannot_ship_on_time
        "vip_penalty_threshold": 2000,   # VIP + penalty > $2000/day → VP escalation
        "escalation": {
            "vip_vp_level_penalty": 2000,  # VIP + penalty > $X → VP-level escalation
            "immediate_blocker_count": 3,  # blockers > X → escalate immediately
            "monitor_blocker_count": 1,    # blockers > X → escalate if persists 24h
        },
    },

    # === Quote Comparison Scoring Weights ===
    # From skills/quote_comparison_summary.py _score_supplier()
    "quote_scoring": {
        "price_weight": 0.30,
        "reliability_weight": 0.25,
        "quality_weight": 0.20,
        "lead_time_weight": 0.15,
        "risk_weight": 0.10,
    },

    # === Expedite Options Ranking ===
    # From skills/expedite_options.py _compute_ranked_recommendation()
    "option_ranking": {
        "feasibility_high": 3,
        "feasibility_medium": 2,
        "feasibility_low": 1,
        "recommended_bonus": 5,
        "has_cost_bonus": 1,
    },

    # === Material Shortage Recovery ===
    # From skills/material_shortage_recovery.py
    "shortage_recovery": {
        "reliability_high_threshold": 0.85,   # reliability >= 0.85 → high feasibility
        "reliability_medium_threshold": 0.6,  # reliability >= 0.6 → medium feasibility
        "emergency_reorder_recommended_reliability": 0.7,  # min reliability for recommended
        "alternate_supplier_recommended_reliability": 0.8,  # min for alternate supplier
        "partial_production_min_ratio": 0.3,  # material ratio >= 0.3 for recommendation
        "partial_production_min_penalty": 1000,  # penalty > $1000 for partial production
    },

    # === Capacity Rebalance ===
    # From skills/capacity_rebalance.py
    "capacity_rebalance": {
        "capacity_pressure_threshold": 0.9,     # load > max_capacity * 0.9 → pressure
        "split_load_min_penalty": 500,           # penalty > $500 for split load recommendation
        "defer_order_max_penalty": 500,          # penalty < $500 for deferral recommendation
        "defer_order_max_priority": 1,           # priority <= 1 for deferral recommendation
        "priority_high": 3,
        "priority_normal": 2,
        "priority_low": 1,
    },

    # === Supplier Follow-up ===
    # From skills/supplier_followup_draft.py
    "supplier_followup": {
        "urgency_critical": 4,
        "urgency_high": 3,
        "urgency_medium": 2,
        "urgency_low": 1,
    },

    # === Reliability / Lead Time Defaults ===
    "defaults": {
        "supplier_reliability_default": 0.5,
        "reliability_floor": 0.1,  # min value for division (avoid divide-by-zero)
        "emergency_lead_reduction": 0.6,  # emergency reorder cuts lead time to 60%
        "expedite_premium_pct": 0.3,      # 30% premium for emergency shipping
    },
}


def load_policy(config_path=None):
    """Load policy from a JSON config file, merging with defaults.

    Args:
        config_path: Path to JSON config file. If None, searches for
                     policies/active.json relative to repo root.

    Returns:
        Merged policy dict (defaults overridden by config values).
    """
    policy = _deep_merge(DEFAULT_POLICY, {})

    if config_path is None:
        # Auto-detect: look for policies/active.json relative to this file
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(repo_root, "policies", "active.json")

    if os.path.isfile(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            override = json.load(f)
        policy = _deep_merge(DEFAULT_POLICY, override)
        policy["_source"] = f"file:{config_path}"
    else:
        policy["_source"] = "default"

    return policy


def get_policy():
    """Get the active policy for the current thread.

    Falls back to DEFAULT_POLICY if not explicitly set.
    """
    return getattr(_local, "policy", DEFAULT_POLICY)


def set_policy(policy):
    """Set the active policy for the current thread."""
    _local.policy = policy


def get_policy_value(key_path, default=None):
    """Get a specific policy value using dot-notation key path.

    Example: get_policy_value("routing.exact_keyword_weight") → 5
    """
    policy = get_policy()
    keys = key_path.split(".")
    val = policy
    for key in keys:
        if isinstance(val, dict) and key in val:
            val = val[key]
        else:
            return default
    return val


def _deep_merge(base, override):
    """Recursively merge override into base. Returns new dict."""
    result = {}
    for key in base:
        if key in override:
            if isinstance(base[key], dict) and isinstance(override[key], dict):
                result[key] = _deep_merge(base[key], override[key])
            else:
                result[key] = override[key]
        else:
            result[key] = base[key]
    # Include any extra keys from override not in base
    for key in override:
        if key not in base:
            result[key] = override[key]
    return result
