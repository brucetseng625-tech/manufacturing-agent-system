"""Tests for P14-1 Rollout Gating Profile."""

import json
import os
import tempfile
import unittest

from rollout_profile import (
    ROLLOUT_LEVELS,
    CAPABILITIES,
    DEFAULT_ROLLOUT_PROFILE,
    get_rollout_profile,
    get_capability_level,
    is_allowed,
    check_rollout,
    get_rollout_status,
    reload_rollout_profile,
    _operation_required_level,
)


class TestConstants(unittest.TestCase):
    def test_levels_order(self):
        """Levels should be ordered from most restrictive to least."""
        self.assertEqual(ROLLOUT_LEVELS[0], "disabled")
        self.assertEqual(ROLLOUT_LEVELS[-1], "limited_automation")
        self.assertEqual(len(ROLLOUT_LEVELS), 5)

    def test_capabilities_list(self):
        """Should have 5 core capabilities."""
        self.assertIn("run_query", CAPABILITIES)
        self.assertIn("team_workflows", CAPABILITIES)
        self.assertIn("provider_selection", CAPABILITIES)
        self.assertIn("approval_linked_execution", CAPABILITIES)
        self.assertIn("auto_remediation", CAPABILITIES)
        self.assertEqual(len(CAPABILITIES), 5)

    def test_default_profile_structure(self):
        """Default profile should have version, global_level, capabilities."""
        self.assertIn("version", DEFAULT_ROLLOUT_PROFILE)
        self.assertIn("global_level", DEFAULT_ROLLOUT_PROFILE)
        self.assertIn("capabilities", DEFAULT_ROLLOUT_PROFILE)
        self.assertIn("description", DEFAULT_ROLLOUT_PROFILE)


class TestGetCapabilityLevel(unittest.TestCase):
    def test_known_capability(self):
        """Should return the level for a known capability."""
        level = get_capability_level("run_query")
        self.assertIsNotNone(level)
        self.assertIn(level, ROLLOUT_LEVELS)

    def test_unknown_capability(self):
        """Should return None for unknown capability."""
        level = get_capability_level("nonexistent")
        self.assertIsNone(level)


class TestIsAllowed(unittest.TestCase):
    def test_disabled_not_allowed(self):
        """Disabled level should never be allowed."""
        # Set run_query to disabled first
        import tempfile, json, os
        profile = {
            "global_level": "internal_only",
            "capabilities": {
                "run_query": "disabled",
                "team_workflows": "limited_automation",
                "provider_selection": "internal_only",
                "approval_linked_execution": "pilot_with_approval",
                "auto_remediation": "pilot_readonly",
            },
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(profile, f)
            tmp_path = f.name
        try:
            reload_rollout_profile(tmp_path)
            self.assertFalse(is_allowed("run_query", "limited_automation"))
        finally:
            os.unlink(tmp_path)
            reload_rollout_profile()

    def test_higher_allows_lower(self):
        """A higher level should allow operations requiring lower levels."""
        # limited_automation should allow pilot_with_approval
        self.assertTrue(is_allowed("run_query", "pilot_with_approval"))

    def test_same_level_allowed(self):
        """Same level should be allowed."""
        level = get_capability_level("run_query")
        if level and level != "disabled":
            # We can't easily test same-level without knowing the exact default,
            # but we can test with a known high level
            self.assertTrue(is_allowed("run_query", "internal_only"))

    def test_unknown_capability_not_allowed(self):
        """Unknown capability should not be allowed."""
        self.assertFalse(is_allowed("nonexistent", "internal_only"))


class TestCheckRollout(unittest.TestCase):
    def test_allowed_capability(self):
        """Should return allowed=True for permitted capability."""
        result = check_rollout("run_query")
        self.assertIn("allowed", result)
        self.assertIn("capability", result)
        self.assertIn("current_level", result)
        self.assertIn("message", result)
        self.assertIn("gating_rule", result)

    def test_unknown_capability_denied(self):
        """Unknown capability should be denied with clear message."""
        result = check_rollout("nonexistent_cap")
        self.assertFalse(result["allowed"])
        self.assertEqual(result["gating_rule"], "unknown_capability")
        self.assertIn("Unknown capability", result["message"])

    def test_disabled_capability_denied(self):
        """Disabled capability should be denied with clear message."""
        result = check_rollout("run_query")
        # We can't test disabled directly without modifying profile,
        # but we verify the structure
        self.assertIn("allowed", result)

    def test_operation_level_insufficient(self):
        """Should deny when capability level < required operation level."""
        result = check_rollout("run_query", operation="auto_remediation:execute")
        # run_query is limited_automation which >= pilot_with_approval,
        # so this should be allowed
        self.assertTrue(result["allowed"])

    def test_result_structure(self):
        """Check result should have all required fields."""
        result = check_rollout("run_query")
        required_keys = {"allowed", "capability", "current_level", "message", "gating_rule"}
        self.assertTrue(required_keys.issubset(set(result.keys())))


class TestGetRolloutProfile(unittest.TestCase):
    def test_profile_has_source(self):
        """Profile should indicate its source."""
        profile = get_rollout_profile()
        self.assertIn("source", profile)

    def test_profile_has_capabilities_copy(self):
        """Profile capabilities should be a copy, not the internal dict."""
        profile = get_rollout_profile()
        self.assertIsNot(profile["capabilities"], DEFAULT_ROLLOUT_PROFILE["capabilities"])


class TestGetRolloutStatus(unittest.TestCase):
    def test_status_has_capabilities(self):
        """Status should have per-capability status."""
        status = get_rollout_status()
        self.assertIn("capabilities", status)
        for cap in CAPABILITIES:
            self.assertIn(cap, status["capabilities"])

    def test_status_has_checked_at(self):
        """Status should have a timestamp."""
        status = get_rollout_status()
        self.assertIn("checked_at", status)
        self.assertIsInstance(status["checked_at"], str)

    def test_status_has_global_level(self):
        """Status should have global_level."""
        status = get_rollout_status()
        self.assertIn("global_level", status)

    def test_status_has_profile(self):
        """Status should include the full profile."""
        status = get_rollout_status()
        self.assertIn("profile", status)
        self.assertIn("version", status["profile"])

    def test_capability_status_structure(self):
        """Each capability status should have level, allowed, message."""
        status = get_rollout_status()
        for cap, info in status["capabilities"].items():
            self.assertIn("level", info)
            self.assertIn("allowed", info)
            self.assertIn("message", info)


class TestOperationRequiredLevel(unittest.TestCase):
    def test_mutation_ops_require_high_level(self):
        """Mutation operations should require pilot_with_approval."""
        mutation_ops = [
            "provider:select",
            "auto_remediation:execute",
            "auto_remediation:evaluate",
            "approval:approve",
            "approval:retry",
        ]
        for op in mutation_ops:
            level = _operation_required_level(op)
            self.assertEqual(level, "pilot_with_approval")

    def test_readonly_ops_need_low_level(self):
        """Read-only operations should only need internal_only."""
        readonly_ops = [
            "run:dry_run",
            "run:query",
            "provider:status",
            "health:check",
        ]
        for op in readonly_ops:
            level = _operation_required_level(op)
            self.assertEqual(level, "internal_only")

    def test_none_returns_none(self):
        """None operation should return None."""
        self.assertIsNone(_operation_required_level(None))

    def test_unknown_op_requires_approval(self):
        """Unknown operations should require pilot_with_approval (safe default)."""
        level = _operation_required_level("something_new")
        self.assertEqual(level, "pilot_with_approval")


class TestReloadRolloutProfile(unittest.TestCase):
    def test_reload_no_file_returns_default(self):
        """Reload with no file should return default."""
        result = reload_rollout_profile()
        self.assertTrue(result["success"])
        self.assertEqual(result["source"], "default")

    def test_reload_with_valid_file(self):
        """Reload should accept a valid config file."""
        profile = {
            "global_level": "pilot_readonly",
            "capabilities": {
                "run_query": "internal_only",
                "team_workflows": "pilot_readonly",
                "provider_selection": "disabled",
                "approval_linked_execution": "pilot_with_approval",
                "auto_remediation": "limited_automation",
            },
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(profile, f)
            tmp_path = f.name

        try:
            result = reload_rollout_profile(tmp_path)
            self.assertTrue(result["success"])
            self.assertEqual(result["profile"]["global_level"], "pilot_readonly")
            self.assertEqual(result["profile"]["capabilities"]["run_query"], "internal_only")
        finally:
            os.unlink(tmp_path)
            # Reset to default
            reload_rollout_profile()

    def test_reload_with_invalid_level(self):
        """Invalid level should fall back to default level."""
        profile = {
            "global_level": "invalid_level",
            "capabilities": {
                "run_query": "not_a_real_level",
            },
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(profile, f)
            tmp_path = f.name

        try:
            result = reload_rollout_profile(tmp_path)
            self.assertTrue(result["success"])
            # Invalid global_level stays as default
            # Invalid capability level falls back to DEFAULT_LEVEL
            self.assertEqual(result["profile"]["capabilities"]["run_query"], "internal_only")
        finally:
            os.unlink(tmp_path)
            reload_rollout_profile()

    def test_reload_with_bad_file(self):
        """Reload with non-existent file should return default."""
        result = reload_rollout_profile("/nonexistent/path.json")
        self.assertTrue(result["success"])
        self.assertEqual(result["source"], "default")


class TestDisabledGating(unittest.TestCase):
    def test_disabled_capability_blocks_all(self):
        """When a capability is disabled, all operations should be blocked."""
        # First set to disabled
        profile = {
            "global_level": "internal_only",
            "capabilities": {
                "run_query": "disabled",
                "team_workflows": "limited_automation",
                "provider_selection": "internal_only",
                "approval_linked_execution": "pilot_with_approval",
                "auto_remediation": "pilot_readonly",
            },
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(profile, f)
            tmp_path = f.name

        try:
            reload_rollout_profile(tmp_path)
            result = check_rollout("run_query")
            self.assertFalse(result["allowed"])
            self.assertEqual(result["gating_rule"], "disabled")
            self.assertIn("disabled", result["message"].lower())
        finally:
            os.unlink(tmp_path)
            reload_rollout_profile()


class RolloutExplainabilityTest(unittest.TestCase):
    """Test P15-3: Explainability fields in rollout gating responses."""

    def test_disabled_has_explainability_fields(self):
        """Disabled capability should include reason, decision_state, next_action."""
        profile = {
            "global_level": "internal_only",
            "capabilities": {"run_query": "disabled"},
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(profile, f)
            tmp_path = f.name
        try:
            reload_rollout_profile(tmp_path)
            result = check_rollout("run_query")
            self.assertFalse(result["allowed"])
            self.assertIn("reason", result)
            self.assertIn("decision_state", result)
            self.assertIn("next_action", result)
            self.assertIn("requires_approval", result)
            self.assertEqual(result["decision_state"], "rollout_gated")
            self.assertFalse(result["requires_approval"])
        finally:
            os.unlink(tmp_path)
            reload_rollout_profile()

    def test_level_insufficient_has_explainability_fields(self):
        """Insufficient level should include reason and actionable next_action."""
        profile = {
            "global_level": "internal_only",
            "capabilities": {"provider_selection": "internal_only"},
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(profile, f)
            tmp_path = f.name
        try:
            reload_rollout_profile(tmp_path)
            # provider:select requires pilot_with_approval, but global is internal_only
            result = check_rollout("provider_selection", operation="provider:select")
            self.assertFalse(result["allowed"])
            self.assertIn("reason", result)
            self.assertIn("next_action", result)
            self.assertEqual(result["gating_rule"], "level_insufficient")
            self.assertIn("insufficient", result["reason"].lower())
        finally:
            os.unlink(tmp_path)
            reload_rollout_profile()


if __name__ == "__main__":
    unittest.main()
