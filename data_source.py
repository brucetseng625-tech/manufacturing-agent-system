
import json
import os
import csv
import time
import threading
from abc import ABC, abstractmethod
from enum import Enum
from config import get_config_value

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

    def degradation_status(self, data_dir: str = None) -> dict:
        """Return degradation-mode visibility info.

        Default: this provider has no degradation concept.

        Returns:
            dict with keys:
                is_degraded (bool): whether serving in degraded mode
                mode (str): provider mode
                active_path (str): which path is currently serving
                reason (str): why degraded (empty if not degraded)
                live_readiness (str|None): live provider readiness if applicable
                fallback_readiness (str|None): fallback readiness if applicable
                recommendations (list): suggested actions
        """
        return {
            "is_degraded": False,
            "mode": self.name(),
            "active_path": self.name(),
            "reason": "",
            "live_readiness": None,
            "fallback_readiness": None,
            "recommendations": [],
        }


class LocalFileProvider(DataProvider):
    """Loads data from local JSON/CSV files. Preserves existing behavior."""

    mode = "local"

    def name(self) -> str:
        return "local"

    def capabilities(self) -> list:
        return [ProviderCapability.READ.value]

    def readiness(self, data_dir: str = None) -> str:
        if not get_config_value("rollout.local.enabled", True):
            return ProviderReadiness.DISABLED.value
        if data_dir and not self.is_available(data_dir):
            return ProviderReadiness.DISABLED.value
        return ProviderReadiness.READY.value

    def health_check(self, data_dir: str = None) -> dict:
        if not get_config_value("rollout.local.enabled", True):
            return {
                "supported": True,
                "status": "disabled",
                "details": {"message": "Local provider disabled by rollout control"},
            }
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
        if not get_config_value("rollout.local.enabled", True):
            return False
        return os.path.isdir(data_dir)

    def degradation_status(self, data_dir: str = None) -> dict:
        """Local-only mode: not degraded, this is the intended path."""
        return {
            "is_degraded": False,
            "mode": "local",
            "active_path": "local",
            "reason": "",
            "live_readiness": None,
            "fallback_readiness": None,
            "recommendations": [],
        }


class LiveDataProvider(DataProvider):
    """Skeleton provider for MCP/ERP integration.

    In production, this would connect to a live data source via MCP,
    REST API, database, or other enterprise integration.

    Current behavior: returns empty data and marks itself unavailable
    so the fallback to local files triggers automatically.
    """

    mode = "live"

    def name(self) -> str:
        return "live"

    def capabilities(self) -> list:
        return [
            ProviderCapability.READ.value,
            ProviderCapability.WRITE.value,
            ProviderCapability.HEALTH_CHECK.value,
        ]

    def readiness(self, data_dir: str = None) -> str:
        if not get_config_value("rollout.live.enabled", True):
            return ProviderReadiness.DISABLED.value
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
        if not get_config_value("rollout.live.enabled", True):
            return False
        """Check if live source is reachable.

        Override this to implement health checks (e.g., ping ERP endpoint).
        Default returns False to indicate unconfigured state.
        """
        return False

    def health_check(self, data_dir: str = None) -> dict:
        if not get_config_value("rollout.live.enabled", True):
            return {
                "supported": True,
                "status": "disabled",
                "details": {"message": "Live provider disabled by rollout control"},
            }
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

    def degradation_status(self, data_dir: str = None) -> dict:
        """Live-only mode: if not available, this IS a degradation."""
        live_ready = self.is_available(data_dir) if data_dir else False
        rollout_enabled = get_config_value("rollout.live.enabled", True)

        if not rollout_enabled:
            return {
                "is_degraded": True,
                "mode": "live",
                "active_path": "none",
                "reason": "Live provider disabled by rollout control",
                "live_readiness": "disabled",
                "fallback_readiness": None,
                "recommendations": ["Set rollout.live.enabled=true to re-enable live path"],
            }

        if not live_ready:
            return {
                "is_degraded": True,
                "mode": "live",
                "active_path": "none",
                "reason": "Live provider not available (not configured or unreachable)",
                "live_readiness": "not_configured",
                "fallback_readiness": None,
                "recommendations": [
                    "Configure live provider (ERP/MCP endpoint) for full functionality",
                    "Consider switching to 'auto' mode for automatic fallback",
                ],
            }

        return {
            "is_degraded": False,
            "mode": "live",
            "active_path": "live",
            "reason": "",
            "live_readiness": "ready",
            "fallback_readiness": None,
            "recommendations": [],
        }


class AutoFailoverProvider(DataProvider):
    """Tries live provider first, falls back to local on failure.

    This is the 'auto' mode provider — it wraps both live and local
    and handles the failover transparently.

    Includes an optional circuit breaker to prevent repeated calls to
    a failing live source and enable automatic recovery probing.
    """

    mode = "auto"

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
        if not get_config_value("rollout.auto.enabled", True):
            return ProviderReadiness.DISABLED.value
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
        if not get_config_value("rollout.auto.enabled", True):
            return {
                "name": self.name(),
                "capabilities": self.capabilities(),
                "readiness": ProviderReadiness.DISABLED.value,
                "available": False,
            }
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
        if not get_config_value("rollout.auto.enabled", True):
            return {
                "supported": True,
                "status": "disabled",
                "details": {"message": "Auto-failover provider disabled by rollout control"},
            }
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
        if not get_config_value("rollout.auto.enabled", True):
            return False
        return self._live.is_available(data_dir) or self._fallback.is_available(data_dir)

    def degradation_status(self, data_dir: str = None) -> dict:
        """Determine if auto-failover is serving in degraded mode.

        Degraded scenarios:
        - Live provider unavailable and serving from fallback
        - Circuit breaker is OPEN (live blocked, using fallback)
        - Live provider readiness is degraded/not_configured
        - Rollout controls disabled a path

        Returns structured visibility into which path is active and why.
        """
        if not get_config_value("rollout.auto.enabled", True):
            return {
                "is_degraded": True,
                "mode": "auto",
                "active_path": "none",
                "reason": "Auto-failover provider disabled by rollout control",
                "live_readiness": "disabled",
                "fallback_readiness": "disabled",
                "circuit_breaker": None,
                "recommendations": ["Set rollout.auto.enabled=true to re-enable auto mode"],
            }

        live_ready = self._live.is_available(data_dir) if data_dir else False
        fallback_ready = self._fallback.is_available(data_dir) if data_dir else False
        live_readiness = self._live.readiness(data_dir)
        fallback_readiness = self._fallback.readiness(data_dir)
        circuit = self.get_circuit_status()
        circuit_state = circuit["state"] if circuit else None

        # Determine which path is currently active
        if circuit_state == "open":
            active_path = "fallback"
            reason = f"Circuit breaker is OPEN — live provider blocked after failures (fallback serving)"
            is_degraded = True
        elif not live_ready:
            active_path = "fallback"
            if live_readiness == "not_configured":
                reason = "Live provider not configured — using local fallback"
            elif live_readiness == "disabled":
                reason = "Live provider disabled by rollout control — using local fallback"
            else:
                reason = f"Live provider unavailable (readiness={live_readiness}) — using local fallback"
            is_degraded = True
        else:
            active_path = "live"
            reason = ""
            is_degraded = False

        # Build recommendations
        recommendations = []
        if not fallback_ready and is_degraded:
            recommendations.append("CRITICAL: Fallback (local) is also unavailable — system cannot serve data")
        if live_readiness == "not_configured":
            recommendations.append("Configure live provider (ERP/MCP endpoint) for full functionality")
        if live_readiness == "disabled":
            recommendations.append("Set rollout.live.enabled=true to re-enable live path")
        if circuit_state == "open":
            recommendations.append(
                f"Circuit breaker will probe live provider in {circuit['recovery_seconds']}s "
                f"if not already in half-open state"
            )
        if circuit_state == "half_open":
            recommendations.append("Circuit breaker is probing live provider — monitor for recovery")

        return {
            "is_degraded": is_degraded,
            "mode": "auto",
            "active_path": active_path,
            "reason": reason,
            "live_readiness": live_readiness,
            "fallback_readiness": fallback_readiness,
            "circuit_breaker": circuit,
            "recommendations": recommendations,
        }


# Valid data source modes
VALID_MODES = ("local", "live", "auto")


class HttpReadonlyProvider(DataProvider):
    """Read-only HTTP provider that fetches JSON from a configurable base URL.

    Configuration via config.json:
    ```json
    {
      "live_provider": {
        "http": {
          "base_url": "https://api.example.com/data",
          "timeout_seconds": 10,
          "health_path": "/health"
        }
      }
    }
    ```

    Data loading: `{base_url}/{filename_without_ext}`
    Health check: `{base_url}{health_path}` or `{base_url}` if no health_path.

    This replaces the skeleton LiveDataProvider with a concrete readonly
    integration that can fetch from real REST/JSON endpoints.
    """

    mode = "http_readonly"

    def __init__(self, base_url=None, timeout=None, health_path=None):
        self._base_url = base_url
        self._timeout = timeout or 10
        self._health_path = health_path or ""
        self._last_health = None
        self._last_health_time = None

    @staticmethod
    def _from_config():
        """Create from config.json settings."""
        base_url = get_config_value("live_provider.http.base_url", "")
        timeout = get_config_value("live_provider.http.timeout_seconds", 10)
        health_path = get_config_value("live_provider.http.health_path", "")
        if not base_url:
            return None
        return HttpReadonlyProvider(base_url, timeout, health_path)

    def name(self) -> str:
        return "http_readonly"

    def capabilities(self) -> list:
        return [
            ProviderCapability.READ.value,
            ProviderCapability.HEALTH_CHECK.value,
        ]

    def _is_configured(self) -> bool:
        return bool(self._base_url)

    def readiness(self, data_dir: str = None) -> str:
        if not get_config_value("rollout.live.enabled", True):
            return ProviderReadiness.DISABLED.value
        if not self._is_configured():
            return ProviderReadiness.NOT_CONFIGURED.value
        return ProviderReadiness.READY.value

    def is_available(self, data_dir: str) -> bool:
        if not get_config_value("rollout.live.enabled", True):
            return False
        if not self._is_configured():
            return False
        return True

    def _should_apply_mapping(self) -> bool:
        """Check if auto-mapping is enabled in config."""
        return get_config_value("live_provider.data_mapping.enabled", False)

    def load(self, data_dir: str, filename: str) -> list:
        """Fetch JSON from {base_url}/{filename_without_ext}.

        Optionally applies data mapping and validation when
        live_provider.data_mapping.enabled is true.
        """
        import urllib.request
        import urllib.error

        if not self._is_configured():
            raise RuntimeError("HttpReadonlyProvider not configured — set live_provider.http.base_url")

        base_name = os.path.splitext(filename)[0]
        url = f"{self._base_url.rstrip('/')}/{base_name}"

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read().decode("utf-8")
                data = json.loads(body)
                if isinstance(data, list):
                    raw_data = data
                elif isinstance(data, dict):
                    raw_data = [data]
                else:
                    raw_data = []
        except urllib.error.HTTPError as e:
            try:
                raise RuntimeError(
                    f"HTTP {e.code} from {url}: {e.reason}"
                ) from e
            finally:
                try:
                    e.close()
                except Exception:
                    pass
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Failed to reach {url}: {e.reason}"
            ) from e
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Invalid JSON from {url}: {e}"
            ) from e

        # Apply mapping + validation if configured
        if self._should_apply_mapping() and raw_data:
            try:
                from data_mapper import apply_mapping
                mapped_data, report = apply_mapping(raw_data, base_name)
                if report.get("errors", 0) > 0:
                    import logging
                    logger = logging.getLogger("data_mapper")
                    logger.warning(
                        f"Mapping errors for {base_name}: {report['errors']}/{report['total']} records failed. "
                        f"Details: {json.dumps(report.get('error_details', [])[:3])}"
                    )
                return mapped_data
            except Exception as e:
                # If mapping fails, fall back to raw data to avoid breaking data loading
                import logging
                logger = logging.getLogger("data_mapper")
                logger.warning(f"Mapping failed for {base_name}, returning raw data: {e}")
                return raw_data

        return raw_data

    def health_check(self, data_dir: str = None) -> dict:
        """Ping health endpoint or base URL to check connectivity."""
        import urllib.request
        import urllib.error

        if not get_config_value("rollout.live.enabled", True):
            return {
                "supported": True,
                "status": "disabled",
                "details": {"message": "Live provider disabled by rollout control"},
            }
        if not self._is_configured():
            return {
                "supported": True,
                "status": "not_configured",
                "details": {
                    "message": "live_provider.http.base_url not set",
                    "configured": False,
                },
            }

        health_url = f"{self._base_url.rstrip('/')}{self._health_path}"
        try:
            req = urllib.request.Request(health_url)
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                status_code = resp.status
                body = resp.read().decode("utf-8")
                is_healthy = 200 <= status_code < 300
                self._last_health = "ok" if is_healthy else "unhealthy"
                self._last_health_time = time.time()
                return {
                    "supported": True,
                    "status": "ok" if is_healthy else "unhealthy",
                    "details": {
                        "url": health_url,
                        "status_code": status_code,
                        "configured": True,
                        "response_preview": body[:200] if not is_healthy else "",
                    },
                }
        except Exception as e:
            self._last_health = "unreachable"
            self._last_health_time = time.time()
            return {
                "supported": True,
                "status": "unreachable",
                "details": {
                    "url": health_url,
                    "configured": True,
                    "error": str(e),
                },
            }

    def degradation_status(self, data_dir: str = None) -> dict:
        is_configured = self._is_configured()
        rollout_enabled = get_config_value("rollout.live.enabled", True)

        if not rollout_enabled:
            return {
                "is_degraded": True,
                "mode": self.name(),
                "active_path": "none",
                "reason": "Live provider disabled by rollout control",
                "live_readiness": "disabled",
                "fallback_readiness": None,
                "circuit_breaker": None,
                "recommendations": ["Set rollout.live.enabled=true to re-enable"],
            }

        if not is_configured:
            return {
                "is_degraded": True,
                "mode": self.name(),
                "active_path": "none",
                "reason": "HTTP base_url not configured",
                "live_readiness": "not_configured",
                "fallback_readiness": None,
                "circuit_breaker": None,
                "recommendations": ["Set live_provider.http.base_url in config.json"],
            }

        last_health = self._last_health or "unknown"
        return {
            "is_degraded": last_health != "ok",
            "mode": self.name(),
            "active_path": "http" if last_health == "ok" else "none",
            "reason": f"Last health check: {last_health}",
            "live_readiness": "ready" if last_health == "ok" else "degraded",
            "fallback_readiness": None,
            "circuit_breaker": None,
            "recommendations": [f"Verify {self._base_url} is reachable"] if last_health != "ok" else [],
        }


# Default provider (local)
_default_provider = LocalFileProvider()
_default_provider_mode = "local"


def get_data_source() -> DataProvider:
    """Get the active data source provider.

    Thread-local: each thread can have its own provider.
    Falls back to the global default provider if not explicitly set.
    """
    return getattr(_local, "provider", _default_provider)


def set_data_source(provider: DataProvider) -> None:
    """Set the active data source provider for the current thread."""
    _local.provider = provider


def set_default_provider(mode: str) -> DataProvider:
    """Set the global default provider mode.

    Affects all threads that don't have a thread-local override.
    This is the mechanism for runtime provider selection.

    Args:
        mode: 'local', 'live', or 'auto'

    Returns:
        The newly created provider instance.
    """
    global _default_provider, _default_provider_mode
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid mode: {mode}. Must be one of {VALID_MODES}")
    _default_provider = create_provider(mode)
    _default_provider_mode = mode
    return _default_provider


def get_default_provider_mode() -> str:
    """Return the current global default provider mode."""
    return _default_provider_mode


def create_provider(mode: str, live_provider: DataProvider = None,
                    cb_threshold=0, cb_recovery=60) -> DataProvider:
    """Create a provider for the given mode.

    Args:
        mode: 'local', 'live', or 'auto'
        live_provider: Optional custom LiveDataProvider instance.
                      If not provided, auto-detects HttpReadonlyProvider
                      from config, or falls back to skeleton LiveDataProvider.
        cb_threshold: Circuit breaker failure threshold (0 = disabled).
        cb_recovery: Circuit breaker recovery seconds.

    Returns:
        Configured DataProvider instance.
    """
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid data source mode: {mode}. Must be one of {VALID_MODES}")

    local = LocalFileProvider()

    # Auto-detect live provider: HttpReadonlyProvider if configured, else skeleton
    if live_provider is None:
        http_provider = HttpReadonlyProvider._from_config()
        live = http_provider if http_provider else LiveDataProvider()
    else:
        live = live_provider

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


def get_degradation_status(data_dir: str = None) -> dict:
    """Get degradation-mode visibility for the active provider.

    Returns a dict showing whether the system is serving in degraded mode,
    which path is active, why, and recommendations.

    Works with any provider mode:
    - local: always not_degraded (this is the intended path)
    - live: degraded if live provider not available
    - auto: degraded if fallback is active or circuit breaker is open
    """
    provider = get_data_source()
    return provider.degradation_status(data_dir)


def get_system_status(data_dir: str = None) -> dict:
    """Aggregated operator-facing system status.

    Combines provider status, health, degradation visibility, config state,
    and data directory metadata into a single view for operators.

    This is the canonical "is everything OK?" endpoint.

    Args:
        data_dir: Optional data directory path. Defaults to mock_data.

    Returns:
        dict with keys:
            system: overall status (ok/degraded/unhealthy)
            provider: full provider status dict
            health: health check result dict
            degradation: degradation visibility dict
            config: config metadata (source, reload_count, last_reloaded)
            data_dir: data directory metadata (file_count, last_modified, files)
            uptime_seconds: server uptime (None if server not running)
            timestamp: ISO 8601 UTC timestamp
    """
    # Resolve default data_dir
    if data_dir is None:
        from config import get_config_value
        data_dir = get_config_value("runtime.default_data_dir", raw=True)
        if not data_dir:
            data_dir = "mock_data"

    # Aggregate provider views
    provider_status = get_provider_status(data_dir)
    health = get_provider_health(data_dir)
    degradation = get_degradation_status(data_dir)

    # Add default mode to provider status
    provider_status['default_mode'] = get_default_provider_mode()

    # Determine overall system status
    health_status = health.get("status", "unknown")
    is_degraded = degradation.get("is_degraded", False)
    provider_readiness = provider_status.get("readiness", "unknown")

    if health_status == "ok" and not is_degraded:
        overall = "ok"
    elif health_status in ("unreachable", "unhealthy") or provider_readiness == "disabled":
        overall = "unhealthy"
    else:
        overall = "degraded"

    # Config metadata
    try:
        from config import get_config_metadata
        config_meta = get_config_metadata()
    except Exception:
        config_meta = {"source": "unknown", "reload_count": 0, "last_reloaded": None}

    # Data directory metadata
    try:
        from data_dir_monitor import get_data_dir_metadata
        data_dir_meta = get_data_dir_metadata(data_dir)
    except Exception:
        data_dir_meta = {"data_dir": data_dir, "error": "Failed to scan data directory"}

    # Server uptime (set by server.py at startup)
    uptime = getattr(get_system_status, "_uptime_start", None)
    if uptime is not None:
        uptime = round(time.monotonic() - uptime, 1)

    return {
        "system": overall,
        "provider": provider_status,
        "health": health,
        "degradation": degradation,
        "config": {
            "source": config_meta.get("source", "unknown"),
            "reload_count": config_meta.get("reload_count", 0),
            "last_reloaded": config_meta.get("last_reloaded"),
        },
        "data_dir": data_dir_meta,
        "uptime_seconds": uptime,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
