"""Tests for auto_remediation — config-driven auto-remediation hooks."""

import unittest
import json
import os
import sys
import time
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auto_remediation import (
    evaluate_hooks,
    evaluate_all_hooks,
    get_remediation_status,
    reset_remediation_state,
    get_execution_history,
    _is_enabled,
    _get_hooks,
    _check_cooldown,
    _record_execution,
    _last_execution,
    _execution_history,
    SUPPORTED_TRIGGERS,
    SUPPORTED_ACTIONS,
)
from config import set_config


class AutoRemediationConfigTest(unittest.TestCase):
    """Tests for config loading and enabled/disabled state."""

    def setUp(self):
        set_config({})
        reset_remediation_state()

    def test_disabled_by_default(self):
        """Auto-remediation should be disabled by default."""
        self.assertFalse(_is_enabled())

    def test_enabled_via_config(self):
        """Should be enabled when config says so."""
        set_config({"auto_remediation": {"enabled": True}})
        self.assertTrue(_is_enabled())

    def test_hooks_empty_when_not_configured(self):
        """Should return empty hooks when not configured."""
        set_config({"auto_remediation": {"enabled": True}})
        hooks = _get_hooks()
        self.assertEqual(hooks, {})

    def test_hooks_loaded_from_config(self):
        """Should load hook definitions from config."""
        set_config({
            "auto_remediation": {
                "enabled": True,
                "hooks": {
                    "cb_recovery": {
                        "trigger": "circuit_breaker_open",
                        "action": "alerts:reset",
                        "cooldown_seconds": 60,
                    }
                }
            }
        })
        hooks = _get_hooks()
        self.assertIn("cb_recovery", hooks)
        self.assertEqual(hooks["cb_recovery"]["trigger"], "circuit_breaker_open")
        self.assertEqual(hooks["cb_recovery"]["action"], "alerts:reset")


class AutoRemediationEvaluationTest(unittest.TestCase):
    """Tests for hook evaluation logic."""

    def setUp(self):
        set_config({})
        reset_remediation_state()

    def test_evaluate_when_disabled_returns_empty(self):
        """Should return empty list when disabled."""
        results = evaluate_hooks(trigger="circuit_breaker_open")
        self.assertEqual(results, [])

    def test_evaluate_with_no_matching_hooks(self):
        """Should return empty when no hooks match the trigger."""
        set_config({
            "auto_remediation": {
                "enabled": True,
                "hooks": {
                    "hook1": {
                        "trigger": "system_unhealthy",
                        "action": "alerts:reset",
                    }
                }
            }
        })
        results = evaluate_hooks(trigger="circuit_breaker_open")
        self.assertEqual(results, [])

    def test_evaluate_matching_hook_dry_run(self):
        """Should execute matching hook in dry-run mode by default."""
        set_config({
            "auto_remediation": {
                "enabled": True,
                "hooks": {
                    "cb_recovery": {
                        "trigger": "circuit_breaker_open",
                        "action": "alerts:reset",
                        "dry_run": True,
                    }
                }
            }
        })
        results = evaluate_hooks(trigger="circuit_breaker_open")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["hook"], "cb_recovery")
        self.assertEqual(results[0]["status"], "dry_run")
        self.assertTrue(results[0]["dry_run"])

    def test_evaluate_unsupported_trigger_skipped(self):
        """Should skip hooks with unsupported triggers."""
        set_config({
            "auto_remediation": {
                "enabled": True,
                "hooks": {
                    "bad_hook": {
                        "trigger": "some_unknown_trigger",
                        "action": "alerts:reset",
                    }
                }
            }
        })
        results = evaluate_hooks(trigger="some_unknown_trigger")
        self.assertEqual(results, [])

    def test_evaluate_unsupported_action_skipped(self):
        """Should skip hooks with unsupported actions."""
        set_config({
            "auto_remediation": {
                "enabled": True,
                "hooks": {
                    "bad_hook": {
                        "trigger": "circuit_breaker_open",
                        "action": "dangerous_write",
                    }
                }
            }
        })
        results = evaluate_hooks(trigger="circuit_breaker_open")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "skipped")

    def test_evaluate_multiple_matching_hooks(self):
        """Should execute all hooks matching the same trigger."""
        set_config({
            "auto_remediation": {
                "enabled": True,
                "hooks": {
                    "hook1": {
                        "trigger": "system_unhealthy",
                        "action": "alerts:reset",
                        "dry_run": True,
                    },
                    "hook2": {
                        "trigger": "system_unhealthy",
                        "action": "config:reload",
                        "dry_run": True,
                    }
                }
            }
        })
        results = evaluate_hooks(trigger="system_unhealthy")
        self.assertEqual(len(results), 2)

    def test_evaluate_with_context(self):
        """Should pass context to audit log."""
        set_config({
            "auto_remediation": {
                "enabled": True,
                "hooks": {
                    "test_hook": {
                        "trigger": "degradation_detected",
                        "action": "alerts:reset",
                        "dry_run": True,
                    }
                }
            }
        })
        ctx = {"provider": "live", "reason": "timeout"}
        results = evaluate_hooks(trigger="degradation_detected", context=ctx)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["trigger"], "degradation_detected")


class AutoRemediationCooldownTest(unittest.TestCase):
    """Tests for cooldown logic."""

    def setUp(self):
        set_config({})
        reset_remediation_state()

    def test_cooldown_prevents_immediate_reexecution(self):
        """Should prevent re-execution within cooldown window."""
        set_config({
            "auto_remediation": {
                "enabled": True,
                "hooks": {
                    "quick_hook": {
                        "trigger": "circuit_breaker_open",
                        "action": "alerts:reset",
                        "cooldown_seconds": 300,
                        "dry_run": True,
                    }
                }
            }
        })
        # First execution
        results1 = evaluate_hooks(trigger="circuit_breaker_open")
        self.assertEqual(results1[0]["status"], "dry_run")

        # Second execution should be in cooldown
        results2 = evaluate_hooks(trigger="circuit_breaker_open")
        self.assertEqual(results2[0]["status"], "cooldown")

    def test_cooldown_expires_allows_reexecution(self):
        """Should allow re-execution after cooldown expires."""
        set_config({
            "auto_remediation": {
                "enabled": True,
                "hooks": {
                    "quick_hook": {
                        "trigger": "circuit_breaker_open",
                        "action": "alerts:reset",
                        "cooldown_seconds": 0,
                        "dry_run": True,
                    }
                }
            }
        })
        # First execution
        results1 = evaluate_hooks(trigger="circuit_breaker_open")
        self.assertEqual(results1[0]["status"], "dry_run")

        # With 0 cooldown, should execute again immediately
        results2 = evaluate_hooks(trigger="circuit_breaker_open")
        self.assertEqual(results2[0]["status"], "dry_run")

    def test_different_hooks_have_independent_cooldowns(self):
        """Each hook should have its own cooldown."""
        set_config({
            "auto_remediation": {
                "enabled": True,
                "hooks": {
                    "hook_a": {
                        "trigger": "circuit_breaker_open",
                        "action": "alerts:reset",
                        "cooldown_seconds": 300,
                        "dry_run": True,
                    },
                    "hook_b": {
                        "trigger": "system_unhealthy",
                        "action": "config:reload",
                        "cooldown_seconds": 300,
                        "dry_run": True,
                    }
                }
            }
        })
        # Execute hook_a
        results_a = evaluate_hooks(trigger="circuit_breaker_open")
        self.assertEqual(results_a[0]["status"], "dry_run")

        # hook_b should still be executable (different cooldown)
        results_b = evaluate_hooks(trigger="system_unhealthy")
        self.assertEqual(results_b[0]["status"], "dry_run")


class AutoRemediationStatusTest(unittest.TestCase):
    """Tests for status and diagnostics."""

    def setUp(self):
        set_config({})
        reset_remediation_state()

    def test_status_returns_enabled_flag(self):
        """Status should include enabled flag."""
        set_config({"auto_remediation": {"enabled": True}})
        status = get_remediation_status()
        self.assertTrue(status["enabled"])

    def test_status_returns_hooks(self):
        """Status should include hook definitions."""
        set_config({
            "auto_remediation": {
                "enabled": True,
                "hooks": {
                    "test_hook": {
                        "trigger": "circuit_breaker_open",
                        "action": "alerts:reset",
                    }
                }
            }
        })
        status = get_remediation_status()
        self.assertIn("test_hook", status["hooks"])

    def test_status_returns_cooldown_state(self):
        """Status should include cooldown state per hook."""
        set_config({
            "auto_remediation": {
                "enabled": True,
                "hooks": {
                    "test_hook": {
                        "trigger": "circuit_breaker_open",
                        "action": "alerts:reset",
                        "cooldown_seconds": 60,
                        "dry_run": True,
                    }
                }
            }
        })
        # Execute to set cooldown
        evaluate_hooks(trigger="circuit_breaker_open")

        status = get_remediation_status()
        self.assertIn("test_hook", status["cooldown_state"])
        self.assertIn("cooldown_seconds", status["cooldown_state"]["test_hook"])
        self.assertIn("remaining_seconds", status["cooldown_state"]["test_hook"])
        self.assertIn("ready", status["cooldown_state"]["test_hook"])

    def test_status_returns_supported_lists(self):
        """Status should list supported triggers and actions."""
        status = get_remediation_status()
        self.assertEqual(set(status["supported_triggers"]), SUPPORTED_TRIGGERS)
        self.assertEqual(set(status["supported_actions"]), SUPPORTED_ACTIONS)

    def test_execution_history_populated(self):
        """Execution history should be populated after evaluations."""
        set_config({
            "auto_remediation": {
                "enabled": True,
                "hooks": {
                    "hist_hook": {
                        "trigger": "degradation_detected",
                        "action": "alerts:reset",
                        "dry_run": True,
                    }
                }
            }
        })
        evaluate_hooks(trigger="degradation_detected")

        status = get_remediation_status()
        self.assertGreater(len(status["execution_history"]), 0)
        self.assertEqual(status["execution_history"][0]["hook"], "hist_hook")


class AutoRemediationResetTest(unittest.TestCase):
    """Tests for state reset."""

    def setUp(self):
        set_config({})
        reset_remediation_state()

    def test_reset_clears_cooldowns(self):
        """Reset should clear all cooldown state."""
        set_config({
            "auto_remediation": {
                "enabled": True,
                "hooks": {
                    "test_hook": {
                        "trigger": "circuit_breaker_open",
                        "action": "alerts:reset",
                        "cooldown_seconds": 300,
                        "dry_run": True,
                    }
                }
            }
        })
        evaluate_hooks(trigger="circuit_breaker_open")

        # Verify cooldown is set
        status = get_remediation_status()
        self.assertFalse(status["cooldown_state"]["test_hook"]["ready"])

        # Reset
        reset_remediation_state()

        # Cooldown should be cleared
        status = get_remediation_status()
        self.assertTrue(status["cooldown_state"]["test_hook"]["ready"])

    def test_reset_clears_history(self):
        """Reset should clear execution history."""
        set_config({
            "auto_remediation": {
                "enabled": True,
                "hooks": {
                    "test_hook": {
                        "trigger": "circuit_breaker_open",
                        "action": "alerts:reset",
                        "dry_run": True,
                    }
                }
            }
        })
        evaluate_hooks(trigger="circuit_breaker_open")
        self.assertGreater(len(get_execution_history()), 0)

        reset_remediation_state()
        self.assertEqual(len(get_execution_history()), 0)


class AutoRemediationEvaluateAllTest(unittest.TestCase):
    """Tests for evaluate_all_hooks (manual trigger)."""

    def setUp(self):
        set_config({})
        reset_remediation_state()

    def test_evaluate_all_when_disabled(self):
        """Should return empty when disabled."""
        set_config({"auto_remediation": {"enabled": False}})
        results = evaluate_all_hooks()
        self.assertEqual(results, [])

    def test_evaluate_all_executes_all_hooks(self):
        """Should execute all configured hooks."""
        set_config({
            "auto_remediation": {
                "enabled": True,
                "hooks": {
                    "hook1": {
                        "trigger": "circuit_breaker_open",
                        "action": "alerts:reset",
                        "dry_run": True,
                    },
                    "hook2": {
                        "trigger": "system_unhealthy",
                        "action": "config:reload",
                        "dry_run": True,
                    }
                }
            }
        })
        results = evaluate_all_hooks()
        self.assertEqual(len(results), 2)


class AutoRemediationActionsTest(unittest.TestCase):
    """Tests for individual action handlers."""

    def setUp(self):
        set_config({})
        reset_remediation_state()

    def test_alerts_reset_dry_run(self):
        """alerts:reset dry-run should not actually reset."""
        from auto_remediation import _action_alerts_reset
        result = _action_alerts_reset(dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertTrue(result["would_execute"])

    def test_config_reload_dry_run(self):
        """config:reload dry-run should not actually reload."""
        from auto_remediation import _action_config_reload
        result = _action_config_reload(dry_run=True)
        self.assertTrue(result["dry_run"])

    def test_policy_reload_dry_run(self):
        """policy:reload dry-run should not actually reload."""
        from auto_remediation import _action_policy_reload
        result = _action_policy_reload(dry_run=True)
        self.assertTrue(result["dry_run"])

    def test_provider_fallback_always_dry_run(self):
        """provider:fallback should always be dry-run."""
        from auto_remediation import _action_provider_fallback
        result = _action_provider_fallback(dry_run=False)
        self.assertTrue(result["dry_run"])
        self.assertIn("current_provider", result)


if __name__ == "__main__":
    unittest.main()
