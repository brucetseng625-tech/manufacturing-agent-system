
"""Backward-compatible data loader.

All calls to load_json_or_csv are delegated to the active data source provider.
Skills and other components can continue calling load_json_or_csv unchanged.

To switch data sources, use data_source.set_data_source() or
pass --data-source mode to the CLI / data_source field in API requests.
"""
from data_source import load_data as _provider_load


def load_json_or_csv(data_dir, filename):
    """Unified data loader — delegates to the active data source provider.

    Maintains the same signature and behavior as the original implementation.
    When no provider is explicitly configured, uses LocalFileProvider which
    preserves the original JSON/CSV loading behavior.
    """
    return _provider_load(data_dir, filename)
