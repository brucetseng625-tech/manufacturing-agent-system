
import json
import os
import csv
import threading
from abc import ABC, abstractmethod

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


class LocalFileProvider(DataProvider):
    """Loads data from local JSON/CSV files. Preserves existing behavior."""

    def name(self) -> str:
        return "local"

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


class AutoFailoverProvider(DataProvider):
    """Tries live provider first, falls back to local on failure.

    This is the 'auto' mode provider — it wraps both live and local
    and handles the failover transparently.
    """

    def __init__(self, live: LiveDataProvider, fallback: LocalFileProvider):
        self._live = live
        self._fallback = fallback
        self._live_available = None  # None = not yet checked

    def name(self) -> str:
        return "auto"

    def load(self, data_dir: str, filename: str) -> list:
        # Lazy availability check
        if self._live_available is None:
            self._live_available = self._live.is_available(data_dir)

        if self._live_available:
            try:
                data = self._live.load(data_dir, filename)
                return data
            except Exception:
                # Live source failed — fall back to local
                self._live_available = False
                return self._fallback.load(data_dir, filename)

        # Live not available — use local directly
        return self._fallback.load(data_dir, filename)

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


def create_provider(mode: str, live_provider: DataProvider = None) -> DataProvider:
    """Create a provider for the given mode.

    Args:
        mode: 'local', 'live', or 'auto'
        live_provider: Optional custom LiveDataProvider instance.
                      If not provided, uses the skeleton LiveDataProvider.

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
        return AutoFailoverProvider(live, local)


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
