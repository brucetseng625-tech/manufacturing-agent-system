import json
import os
import time
import unittest
import threading
from unittest.mock import MagicMock, patch

from data_source import (
    CircuitBreaker,
    CircuitState,
    AutoFailoverProvider,
    LocalFileProvider,
    LiveDataProvider,
    create_provider,
)


class CircuitStateTest(unittest.TestCase):
    """Tests for CircuitState enum."""

    def test_states_exist(self):
        self.assertEqual(CircuitState.CLOSED.value, "closed")
        self.assertEqual(CircuitState.OPEN.value, "open")
        self.assertEqual(CircuitState.HALF_OPEN.value, "half_open")


class CircuitBreakerUnitTest(unittest.TestCase):
    """Tests for CircuitBreaker class."""

    def test_starts_closed(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_seconds=1)
        self.assertEqual(cb.state, "closed")

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_seconds=60)
        cb.record_failure()
        self.assertEqual(cb.state, "closed")
        cb.record_failure()
        self.assertEqual(cb.state, "closed")
        cb.record_failure()
        self.assertEqual(cb.state, "open")

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_seconds=60)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        self.assertEqual(cb.state, "closed")
        # Now need 3 more failures to open
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, "closed")

    def test_open_circuit_raises_before_call(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_seconds=60)
        cb.record_failure()
        self.assertEqual(cb.state, "open")
        with self.assertRaises(RuntimeError) as ctx:
            cb.before_call()
        self.assertIn("OPEN", str(ctx.exception))

    def test_half_open_after_recovery(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_seconds=0.1)
        cb.record_failure()
        self.assertEqual(cb.state, "open")
        time.sleep(0.15)
        self.assertEqual(cb.state, "half_open")

    def test_half_open_to_closed_on_success(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_seconds=0.1)
        cb.record_failure()
        time.sleep(0.15)
        self.assertEqual(cb.state, "half_open")
        cb.before_call()  # allowed in half_open
        cb.record_success()
        self.assertEqual(cb.state, "closed")

    def test_half_open_to_open_on_failure(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_seconds=0.1)
        cb.record_failure()
        time.sleep(0.15)
        self.assertEqual(cb.state, "half_open")
        cb.record_failure()
        self.assertEqual(cb.state, "open")

    def test_get_status(self):
        cb = CircuitBreaker(failure_threshold=5, recovery_seconds=30)
        cb.record_failure()
        cb.record_success()
        status = cb.get_status()
        self.assertEqual(status["state"], "closed")
        self.assertEqual(status["failure_threshold"], 5)
        self.assertEqual(status["recovery_seconds"], 30)
        self.assertEqual(status["total_failures"], 1)
        self.assertEqual(status["total_successes"], 1)
        self.assertIsNone(status["last_failure_ago"])  # reset by success

    def test_total_failures_accumulates(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_seconds=0.05)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.1)
        cb.record_failure()  # half_open -> open
        status = cb.get_status()
        self.assertEqual(status["total_failures"], 3)

    def test_disabled_threshold_never_opens(self):
        cb = CircuitBreaker(failure_threshold=0, recovery_seconds=1)
        for _ in range(100):
            cb.record_failure()
        self.assertEqual(cb.state, "closed")


class AutoFailoverCircuitTest(unittest.TestCase):
    """Tests for AutoFailoverProvider with circuit breaker."""

    def _make_live(self, fail=False):
        live = MagicMock(spec=LiveDataProvider)
        live.name.return_value = "live"
        live.is_available.return_value = True
        if fail:
            live.load.side_effect = ConnectionError("live down")
        else:
            live.load.return_value = [{"id": 1}]
        return live

    def _make_local(self):
        local = MagicMock(spec=LocalFileProvider)
        local.name.return_value = "local"
        local.is_available.return_value = True
        local.load.return_value = [{"id": 99}]
        return local

    def test_circuit_disabled_uses_simple_path(self):
        live = self._make_live(fail=True)
        local = self._make_local()
        provider = AutoFailoverProvider(live, local, failure_threshold=0)
        result = provider.load("/data", "orders")
        self.assertEqual(result, [{"id": 99}])
        self.assertIsNone(provider.get_circuit_status())

    def test_circuit_enabled_fallbacks_on_failure(self):
        live = self._make_live(fail=True)
        local = self._make_local()
        provider = AutoFailoverProvider(live, local, failure_threshold=3, recovery_seconds=60)
        # Each call fails live, falls back to local
        for _ in range(3):
            result = provider.load("/data", "orders")
            self.assertEqual(result, [{"id": 99}])
        # After 3 failures, circuit should be open
        status = provider.get_circuit_status()
        self.assertEqual(status["state"], "open")

    def test_circuit_open_skips_live(self):
        live = self._make_live(fail=True)
        local = self._make_local()
        provider = AutoFailoverProvider(live, local, failure_threshold=2, recovery_seconds=60)
        provider.load("/data", "orders")
        provider.load("/data", "orders")
        status = provider.get_circuit_status()
        self.assertEqual(status["state"], "open")
        # Clear call count to verify live is NOT called
        live.load.reset_mock()
        # Next call should skip live entirely
        result = provider.load("/data", "orders")
        self.assertEqual(result, [{"id": 99}])
        live.load.assert_not_called()

    def test_circuit_recovery_allows_probe(self):
        live = self._make_live(fail=False)  # Now live recovers
        local = self._make_local()
        provider = AutoFailoverProvider(live, local, failure_threshold=1, recovery_seconds=0.05)
        # Trip the circuit
        live_fail = MagicMock(spec=LiveDataProvider)
        live_fail.name.return_value = "live"
        live_fail.is_available.return_value = True
        live_fail.load.side_effect = ConnectionError("down")
        provider._live = live_fail
        provider.load("/data", "orders")
        self.assertEqual(provider.get_circuit_status()["state"], "open")
        # Now swap in recovered live
        provider._live = live
        time.sleep(0.1)
        result = provider.load("/data", "orders")
        self.assertEqual(result, [{"id": 1}])
        self.assertEqual(provider.get_circuit_status()["state"], "closed")

    def test_create_provider_with_cb_params(self):
        provider = create_provider("auto", cb_threshold=5, cb_recovery=30)
        self.assertIsInstance(provider, AutoFailoverProvider)
        self.assertIsNotNone(provider._circuit)
        self.assertEqual(provider._circuit._failure_threshold, 5)

    def test_create_provider_without_cb(self):
        provider = create_provider("auto", cb_threshold=0)
        self.assertIsInstance(provider, AutoFailoverProvider)
        self.assertIsNone(provider._circuit)


class CircuitBreakerThreadSafetyTest(unittest.TestCase):
    """Verify circuit breaker is thread-safe under concurrent load."""

    def test_concurrent_failures_open_correctly(self):
        cb = CircuitBreaker(failure_threshold=10, recovery_seconds=60)
        errors = []

        def record():
            try:
                for _ in range(5):
                    cb.record_failure()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        self.assertEqual(cb.state, "open")


if __name__ == "__main__":
    unittest.main()
