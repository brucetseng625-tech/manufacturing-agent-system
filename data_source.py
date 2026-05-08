
import json
import os
import csv
import time
import threading
from abc import ABC, abstractmethod
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker for live provider calls.

    States:
    - CLOSED: normal operation, failures counted
    - OPEN: circuit tripped, all calls fail fast (fallback immediately)
    - HALF_OPEN: recovery timeout elapsed, allow one probe call

    Transitions:
    - CLOSED → OPEN: when consecutive failures reach threshold
    - OPEN → HALF_OPEN: when recovery_seconds elapses
    - HALF_OPEN → CLOSED: probe call succeeds
    - HALF_OPEN → OPEN: probe call fails (reset timer)
    """

    def __init__(self, failure_threshold=3, recovery_seconds=60):
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._last_failure_time = None
        self._total_failures = 0
        self._total_successes = 0

    @property
    def state(self):
        with self._lock:
            self._check_transition()
            return self._state.value

    def _check_transition(self):
        """Check if we should transition from OPEN to HALF_OPEN."""
        if self._state == CircuitState.OPEN and self._last_failure_time is not None:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self._recovery_seconds:
                self._state = CircuitState.HALF_OPEN

    def before_call(self):
        """Check if call should proceed. Raises RuntimeError if circuit is open."""
        with self._lock:
            self._check_transition()
            if self._state == CircuitState.OPEN:
                raise RuntimeError(
                    f"Circuit breaker is OPEN. "
                    f"Recovery in {self._recovery_seconds - (time.monotonic() - self._last_failure_time):.0f}s"
                )

    def record_success(self):
        with self._lock:
            self._total_successes += 1
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._last_failure_time = None
            else:
                self._failure_count = 0
                self._last_failure_time = None

    def record_failure(self):
        with self._lock:
            self._failure_count += 1
            self._total_failures += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Probe failed — go back to open
                self._state = CircuitState.OPEN
            elif self._failure_threshold > 0 and self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN

    def get_status(self):
        with self._lock:
            self._check_transition()
            return {
                "state": self._state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self._failure_threshold,
                "recovery_seconds": self._recovery_seconds,
                "total_failures": self._total_failures,
                "total_successes": self._total_successes,
                "last_failure_ago": (
                    round(time.monotonic() - self._last_failure_time, 1)
                    if self._last_failure_time is not None
                    else None
                ),
            }



class ProviderCapability(Enum):
    """Provider capability flags."""
    READ = "read"           # Can load data
    WRITE = "write"         # Can write/update data
    HEALTH_CHECK = "health_check"  # Can perform health diagnostics


class ProviderReadiness(Enum):
    """Provider readiness states."""
    READY = "ready"
    NOT_CONFIGURED = "not_configured"
    DEGRADED = "degraded"
    DISABLED = "disabled"
    CIRCUIT_OPEN = "circuit_open"

# Thread-local storage for the active data source
_local = threading.local()


class DataProvider(ABC):
    """Abstract base class for data providers."""

    @abstractmethod
    def name(self) -> str:
        """Return a human-readable provider name."""

    @abstractmethod
    def load(self, data_dir: str, filename: str) -> list:
        """Load data from the given source. Returns a list of dicts."""

    def is_available(self, data_dir: str) -> bool:
        """Check if this provider can serve data. Default: True."""
        return True

    def capabilities(self) -> list:
        """Return list of ProviderCapability values this provider supports."""
        return [ProviderCapability.READ.value]

    def readiness(self, data_dir: str = None) -> str:
        """Return ProviderReadiness state. Default: READY if available, else DISABLED."""
        if data_dir and not self.is_available(data_dir):
            return ProviderReadiness.DISABLED.value
        return ProviderReadiness.READY.value

    def status(self, data_dir: str = None) -> dict:
        """Return comprehensive provider status dict."""
        return {
            "name": self.name(),
            "capabilities": self.capabilities(),
            "readiness": self.readiness(data_dir),
            "available": self.is_available(data_dir) if data_dir else None,
        }

    def health_check(self, data_dir: str = None) -> dict:
        """Perform a health check and return diagnostics.

        Default implementation reports that health checks are not supported.
        Subclasses should override to provide real diagnostics.

        Returns:
            dict with keys: supported (bool), status (str), details (dict)
        """
        return {
            "supported": False,
            "status": "not_available",
            "details": {"message": "Health check not implemented for this provider"},
        }


class LocalFileProvider(DataProvider):
    """Loads data from local JSON/CSV files. Preserves existing behavior."""

    def name(self) -> str:
        return "local"

    def capabilities(self) -> list:
        return [ProviderCapability.READ.value]

    def readiness(self, data_dir: str = None) -> str:
        if data_dir and not self.is_available(data_dir):
            return ProviderReadiness.DISABLED.value
        return ProviderReadiness.READY.value

    def health_check(self, data_dir: str = None) -> dict:
        """Local provider health: check if data dir exists and is readable."""
        if data_dir is None:
            return {
                "supported": True,
                "status": "ok",
                "details": {"message": "No data_dir specified — skipping filesystem check"},
            }
        exists = os.path.isdir(data_dir)
        readable = exists and os.access(data_dir, os.R_OK)
        if readable:
            return {
                "supported": True,
                "status": "ok",
                "details": {
                    "data_dir": data_dir,
                    "exists": True,
                    "readable": True,
                },
            }
        return {
            "supported": True,
            "status": "unhealthy" if exists else "unreachable",
            "details": {
                "data_dir": data_dir,
                "exists": exists,
                "readable": readable,
                "error": None if exists else f"Directory not found: {data_dir}",
            },
        }

    def load(self, data_dir: str, filename: str) -> list:
        base_name = os.path.splitext(filename)[0]
        json_path = os.path.join(data_dir, f"{base_name}.json")
        csv_path = os.path.join(data_dir, f"{base_name}.csv")

        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)

        if os.path.exists(csv_path):
            data = []
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Basic type conversion for common fields
                    if "quantity" in row:
                        row["quantity"] = int(row["quantity"])
                    if "progress_percent" in row:
                        row["progress_percent"] = int(row["progress_percent"])
                    if "required_qty" in row:
                        row["required_qty"] = int(row["required_qty"])
                    if "available_qty" in row:
                        row["available_qty"] = int(row["available_qty"])
                    if "load_percent" in row:
                        row["load_percent"] = int(row["load_percent"])
                    if "unit_price" in row:
                        row["unit_price"] = float(row["unit_price"])
                    if "lead_time_days" in row:
                        row["lead_time_days"] = int(row["lead_time_days"])
                    if "moq" in row:
                        row["moq"] = int(row["moq"])
                    if "quality_rating" in row:
                        row["quality_rating"] = float(row["quality_rating"])
                    data.append(row)
            return data

        return []

    def is_available(self, data_dir: str) -> bool:
        return os.path.isdir(data_dir)


class LiveDataProvider(DataProvider):
    """Skeleton provider for MCP/ERP integration.

    In production, this would connect to a live data source via MCP,
    REST API, database, or other enterprise integration.

    Current behavior: returns empty data and marks itself unavailable
    so the fallback to local files triggers automatically.
    """

    def name(self) -> str:
        return "live"

    def capabilities(self) -> list:
        return [
            ProviderCapability.READ.value,
            ProviderCapability.WRITE.value,
            ProviderCapability.HEALTH_CHECK.value,
        ]

    def readiness(self, data_dir: str = None) -> str:
        """Live provider is NOT_CONFIGURED until a real implementation is provided."""
        return ProviderReadiness.NOT_CONFIGURED.value

    def load(self, data_dir: str, filename: str) -> list:
        """Attempt to load from a live source.

        Override this method in a subclass to implement real MCP/ERP integration.
        The base implementation raises NotImplementedError to trigger fallback.
        """
        raise NotImplementedError(
            "LiveDataProvider is a skeleton. Override load() to implement MCP/ERP integration."
        )

    def is_available(self, data_dir: str) -> bool:
        """Check if live source is reachable.

        Override this to implement health checks (e.g., ping ERP endpoint).
        Default returns False to indicate unconfigured state.
        """
        return False

    def health_check(self, data_dir: str = None) -> dict:
        """Live provider health: reports not configured by default.

        Subclasses should override to implement real diagnostics
        (e.g., ping ERP endpoint, check DB connection).
        """
        return {
            "supported": True,
            "status": "not_configured",
            "details": {
                "message": "LiveDataProvider is a skeleton — override health_check() to implement real diagnostics",
                "configured": False,
            },
        }


class AutoFailoverProvider(DataProvider):
    """Tries live provider first, falls back to local on failure.

    This is the 'auto' mode provider — it wraps both live and local
    and handles the failover transparently.

    Includes an optional circuit breaker to prevent repeated calls to
    a failing live source and enable automatic recovery probing.
    """

    def __init__(self, live: LiveDataProvider, fallback: LocalFileProvider,
                 failure_threshold=0, recovery_seconds=60):
        self._live = live
        self._fallback = fallback
        self._circuit = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_seconds=recovery_seconds,
        ) if failure_threshold > 0 else None

    def name(self) -> str:
        return "auto"

    def capabilities(self) -> list:
        """Union of live and fallback capabilities."""
        caps = set(self._live.capabilities()) | set(self._fallback.capabilities())
        return sorted(caps)

    def readiness(self, data_dir: str = None) -> str:
        """Readiness based on live availability and circuit state."""
        if self._circuit is not None:
            try:
                self._circuit.before_call()
            except RuntimeError:
                return ProviderReadiness.CIRCUIT_OPEN.value
        if data_dir and self._live.is_available(data_dir):
            return ProviderReadiness.READY.value
        # Fallback to local is available
        if data_dir and self._fallback.is_available(data_dir):
            return ProviderReadiness.DEGRADED.value
        return ProviderReadiness.DISABLED.value

    def status(self, data_dir: str = None) -> dict:
        """Extended status including circuit breaker and sub-provider info."""
        result = {
            "name": self.name(),
            "capabilities": self.capabilities(),
            "readiness": self.readiness(data_dir),
            "available": self.is_available(data_dir) if data_dir else None,
        }
        circuit = self.get_circuit_status()
        if circuit is not None:
            result["circuit_breaker"] = circuit
        result["live_provider"] = {
            "name": self._live.name(),
            "capabilities": self._live.capabilities(),
            "readiness": self._live.readiness(data_dir),
        }
        result["fallback_provider"] = {
            "name": self._fallback.name(),
            "capabilities": self._fallback.capabilities(),
            "readiness": self._fallback.readiness(data_dir),
        }
        return result

    def health_check(self, data_dir: str = None) -> dict:
        """Aggregate health diagnostics from live and fallback providers."""
        live_health = self._live.health_check(data_dir)
        fallback_health = self._fallback.health_check(data_dir)

        # Determine overall status
        if live_health.get("status") == "ok":
            overall = "ok"
        elif self._circuit is not None:
            try:
                self._circuit.before_call()
                overall = "degraded"  # live not ok but circuit allows probe
            except RuntimeError:
                overall = "circuit_open"
        elif fallback_health.get("status") == "ok":
            overall = "degraded"
        else:
            overall = "unhealthy"

        return {
            "supported": True,
            "status": overall,
            "details": {
                "live": live_health,
                "fallback": fallback_health,
                "circuit_breaker": self.get_circuit_status(),
            },
        }

    def load(self, data_dir: str, filename: str) -> list:
        # Circuit breaker path
        if self._circuit is not None:
            return self._load_with_circuit(data_dir, filename)
        # Legacy simple failover path
        return self._load_simple(data_dir, filename)

    def _load_with_circuit(self, data_dir: str, filename: str) -> list:
        try:
            self._circuit.before_call()
        except RuntimeError:
            # Circuit is OPEN — fail fast to local
            return self._fallback.load(data_dir, filename)

        try:
            data = self._live.load(data_dir, filename)
            self._circuit.record_success()
            return data
        except Exception:
            self._circuit.record_failure()
            return self._fallback.load(data_dir, filename)

    def _load_simple(self, data_dir: str, filename: str) -> list:
        # Backward compatible: simple boolean failover
        if not hasattr(self, "_live_available"):
            self._live_available = None
        if self._live_available is None:
            self._live_available = self._live.is_available(data_dir)
        if self._live_available:
            try:
                data = self._live.load(data_dir, filename)
                return data
            except Exception:
                self._live_available = False
                return self._fallback.load(data_dir, filename)
        return self._fallback.load(data_dir, filename)

    def get_circuit_status(self):
        """Return circuit breaker status, or None if not configured."""
        if self._circuit is None:
            return None
        return self._circuit.get_status()

    def is_available(self, data_dir: str) -> bool:
        return self._live.is_available(data_dir) or self._fallback.is_available(data_dir)


# Valid data source modes
VALID_MODES = ("local", "live", "auto")

# Default provider (local)
_default_provider = LocalFileProvider()


def get_data_source() -> DataProvider:
    """Get the active data source provider.

    Thread-local: each thread can have its own provider.
    Falls back to LocalFileProvider if not explicitly set.
    """
    return getattr(_local, "provider", _default_provider)


def set_data_source(provider: DataProvider) -> None:
    """Set the active data source provider for the current thread."""
    _local.provider = provider


def create_provider(mode: str, live_provider: DataProvider = None,
                    cb_threshold=0, cb_recovery=60) -> DataProvider:
    """Create a provider for the given mode.

    Args:
        mode: 'local', 'live', or 'auto'
        live_provider: Optional custom LiveDataProvider instance.
                      If not provided, uses the skeleton LiveDataProvider.
        cb_threshold: Circuit breaker failure threshold (0 = disabled).
        cb_recovery: Circuit breaker recovery seconds.

    Returns:
        Configured DataProvider instance.
    """
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid data source mode: {mode}. Must be one of {VALID_MODES}")

    local = LocalFileProvider()
    live = live_provider or LiveDataProvider()

    if mode == "local":
        return local
    elif mode == "live":
        return live
    else:  # auto
        return AutoFailoverProvider(live, local, cb_threshold, cb_recovery)


def load_data(data_dir: str, filename: str) -> list:
    """Load data using the active provider.

    This is the unified entry point that skills and other components
    should use instead of calling load_json_or_csv directly.
    """
    provider = get_data_source()
    return provider.load(data_dir, filename)


def get_provider_name() -> str:
    """Get the name of the active provider."""
    return get_data_source().name()


def get_provider_status(data_dir: str = None) -> dict:
    """Get comprehensive status of the active provider.

    Returns a dict with name, capabilities, readiness, and optionally
    circuit breaker and sub-provider details for auto mode.
    """
    provider = get_data_source()
    return provider.status(data_dir)


def get_provider_health(data_dir: str = None) -> dict:
    """Get health diagnostics of the active provider.

    Returns a dict with supported, status, and details from the
    provider's health_check() method.
    """
    provider = get_data_source()
    return provider.health_check(data_dir)
