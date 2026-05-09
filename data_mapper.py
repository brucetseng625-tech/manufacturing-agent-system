"""Data mapping and validation layer for external ERP/HTTP data sources.

Provides configurable field mapping, type coercion, default value filling,
and schema validation for incoming external data records.

Configuration via config.json under live_provider.data_mapping:
{
  "live_provider": {
    "data_mapping": {
      "enabled": false,
      "datasets": {
        "orders": {
          "enabled": true,
          "field_mapping": {"id": "order_id", "client_name": "customer"},
          "required_fields": ["order_id", "customer", "quantity"],
          "type_rules": {"quantity": "int", "penalty_per_day": "float"},
          "default_values": {"priority": "Normal", "customer_tier": "Standard"}
        },
        "materials": { ... }
      }
    }
  }
}

Usage:
  from data_mapper import apply_mapping, get_mapping_diagnostics

  # Apply mapping to data loaded from external source
  mapped, report = apply_mapping(raw_data, "orders")

  # Check mapping configuration status
  diag = get_mapping_diagnostics()
"""

import json
import time
import threading
from config import get_config_value

# ─── Thread-safe diagnostics tracker ─────────────────────────────────────────
_mapping_stats_lock = threading.Lock()
_mapping_stats = {}  # {dataset: {"total": N, "mapped": N, "skipped": N, "errors": N, "last_updated": ts}}


def _record_stat(dataset, stat_key, count=1):
    """Record a mapping statistic for a dataset."""
    with _mapping_stats_lock:
        if dataset not in _mapping_stats:
            _mapping_stats[dataset] = {
                "total": 0, "mapped": 0, "skipped": 0, "errors": 0, "last_updated": None,
            }
        _mapping_stats[dataset][stat_key] = _mapping_stats[dataset].get(stat_key, 0) + count
        _mapping_stats[dataset]["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ─── Type Coercion ───────────────────────────────────────────────────────────

_TYPE_MAP = {
    "str": str,
    "string": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
}


def _coerce_value(value, type_name):
    """Attempt to coerce a value to the target type.

    Returns (success, coerced_value_or_original).
    """
    target_type = _TYPE_MAP.get(type_name)
    if target_type is None:
        return True, value  # Unknown type, pass through

    if value is None:
        return True, None

    if isinstance(value, target_type):
        return True, value

    try:
        if type_name in ("int",):
            # Handle float strings like "123.0" -> 123
            if isinstance(value, str):
                return True, int(float(value))
            return True, int(value)
        elif type_name in ("float",):
            return True, float(value)
        elif type_name in ("bool",):
            if isinstance(value, str):
                return True, value.lower() in ("true", "1", "yes")
            return True, bool(value)
        else:
            return True, target_type(value)
    except (ValueError, TypeError):
        return False, value


# ─── SchemaMapper ────────────────────────────────────────────────────────────

class SchemaMapper:
    """Maps external field names to internal schema field names.

    Given a field_mapping dict like {"id": "order_id", "client_name": "customer"},
    renames external keys to internal keys in each record.
    """

    def __init__(self, field_mapping=None):
        """Initialize with external->internal field mapping.

        Args:
            field_mapping: dict mapping external field name to internal field name.
        """
        self._field_mapping = field_mapping or {}

    def map_record(self, record):
        """Apply field mapping to a single record.

        Returns the record with external field names replaced by internal names.
        Fields not in the mapping are preserved as-is.
        """
        if not self._field_mapping:
            return record

        result = {}
        reverse_seen = set()  # Track internal names already set

        # First pass: map external fields to internal names
        for ext_key, int_key in self._field_mapping.items():
            if ext_key in record:
                result[int_key] = record[ext_key]
                reverse_seen.add(int_key)

        # Second pass: copy unmapped fields (only if they don't conflict with mapped names)
        for key, value in record.items():
            int_name = self._field_mapping.get(key, key)
            if int_name not in reverse_seen or key in self._field_mapping:
                # If the key was mapped, it's already in result under int_key
                # If the key was not mapped, copy it as-is
                if key not in self._field_mapping:
                    if key not in result:
                        result[key] = value

        return result


# ─── SchemaValidator ─────────────────────────────────────────────────────────

class SchemaValidator:
    """Validates records against a schema definition.

    Checks required fields, type rules, and applies type coercion + defaults.
    """

    def __init__(self, required_fields=None, type_rules=None, default_values=None):
        """Initialize validator.

        Args:
            required_fields: list of required internal field names.
            type_rules: dict of {field_name: type_name} for type validation/coercion.
            default_values: dict of {field_name: default_value} for missing optional fields.
        """
        self._required_fields = required_fields or []
        self._type_rules = type_rules or {}
        self._default_values = default_values or {}

    def validate_and_normalize(self, record):
        """Validate and normalize a single record.

        Returns (success, normalized_record, issues).
        - success: bool — True if record is valid (or fixable via coercion/defaults)
        - normalized_record: the record after type coercion and default filling
        - issues: list of issue strings (empty if success)
        """
        issues = []
        result = dict(record)

        # Fill default values for missing fields
        for field, default in self._default_values.items():
            if field not in result:
                result[field] = default

        # Check required fields
        for field in self._required_fields:
            if field not in result or result[field] is None:
                issues.append(f"missing_required: {field}")

        if issues:
            return False, result, issues

        # Type coercion
        for field, type_name in self._type_rules.items():
            if field in result:
                success, coerced = _coerce_value(result[field], type_name)
                if success:
                    result[field] = coerced
                else:
                    issues.append(f"type_mismatch: {field} (expected {type_name}, got {type(result[field]).__name__})")

        if issues:
            return False, result, issues

        return True, result, []


# ─── Main Entry Points ───────────────────────────────────────────────────────

def _get_dataset_config(dataset_name):
    """Get mapping configuration for a specific dataset.

    Returns None if mapping is disabled or not configured.
    """
    enabled = get_config_value("live_provider.data_mapping.enabled", False)
    if not enabled:
        return None

    datasets = get_config_value("live_provider.data_mapping.datasets", {})
    if not datasets:
        return None

    ds_config = datasets.get(dataset_name, {})
    if not ds_config.get("enabled", False):
        return None

    return ds_config


def apply_mapping(data, dataset_name):
    """Apply field mapping and schema validation to external data.

    Args:
        data: list of records (dicts) from external source.
        dataset_name: string identifier (e.g., "orders", "materials").

    Returns:
        tuple of (mapped_data, report):
        - mapped_data: list of validated/normalized records
        - report: dict with {"total", "mapped", "skipped", "errors", "error_details"}
    """
    if not isinstance(data, list):
        return [], {
            "total": 0, "mapped": 0, "skipped": 0, "errors": 1,
            "error_details": ["Input is not a list"],
        }

    ds_config = _get_dataset_config(dataset_name)
    if ds_config is None:
        # Mapping disabled or not configured — return data as-is
        return data, {
            "total": len(data), "mapped": len(data), "skipped": 0, "errors": 0,
            "error_details": [],
            "note": "mapping disabled or not configured",
        }

    # Build mapper and validator from config
    mapper = SchemaMapper(ds_config.get("field_mapping", {}))
    validator = SchemaValidator(
        required_fields=ds_config.get("required_fields", []),
        type_rules=ds_config.get("type_rules", {}),
        default_values=ds_config.get("default_values", {}),
    )

    mapped_data = []
    error_details = []
    skipped = 0
    errors = 0

    for i, record in enumerate(data):
        # Step 1: Field mapping (external → internal names)
        mapped_record = mapper.map_record(record)

        # Step 2: Validation and normalization
        success, normalized, issues = validator.validate_and_normalize(mapped_record)

        if success:
            mapped_data.append(normalized)
        else:
            errors += 1
            error_details.append({
                "index": i,
                "issues": issues,
                "record_preview": str(dict(list(record.items())[:3]))[:100],
            })

    _record_stat(dataset_name, "total", len(data))
    _record_stat(dataset_name, "mapped", len(mapped_data))
    _record_stat(dataset_name, "skipped", skipped)
    _record_stat(dataset_name, "errors", errors)

    report = {
        "total": len(data),
        "mapped": len(mapped_data),
        "skipped": skipped,
        "errors": errors,
        "error_details": error_details[:10],  # Cap at 10 for brevity
    }
    return mapped_data, report


def apply_mapping_single(record, dataset_name):
    """Apply mapping to a single record.

    Args:
        record: a single dict from external source.
        dataset_name: string identifier.

    Returns:
        tuple of (success, normalized_record, issues)
    """
    ds_config = _get_dataset_config(dataset_name)
    if ds_config is None:
        return True, record, []

    mapper = SchemaMapper(ds_config.get("field_mapping", {}))
    validator = SchemaValidator(
        required_fields=ds_config.get("required_fields", []),
        type_rules=ds_config.get("type_rules", {}),
        default_values=ds_config.get("default_values", {}),
    )

    mapped_record = mapper.map_record(record)
    return validator.validate_and_normalize(mapped_record)


def get_mapping_diagnostics():
    """Return mapping configuration status and runtime statistics.

    Returns:
        dict with enabled status, configured datasets, and runtime stats.
    """
    enabled = get_config_value("live_provider.data_mapping.enabled", False)
    datasets = get_config_value("live_provider.data_mapping.datasets", {})

    dataset_info = {}
    for name, config in datasets.items():
        ds_enabled = config.get("enabled", False) if isinstance(config, dict) else False
        field_mapping = config.get("field_mapping", {}) if isinstance(config, dict) else {}
        required = config.get("required_fields", []) if isinstance(config, dict) else []
        type_rules = config.get("type_rules", {}) if isinstance(config, dict) else {}
        defaults = config.get("default_values", {}) if isinstance(config, dict) else {}

        dataset_info[name] = {
            "enabled": ds_enabled,
            "field_mapping_count": len(field_mapping),
            "required_field_count": len(required),
            "type_rule_count": len(type_rules),
            "default_value_count": len(defaults),
        }

    with _mapping_stats_lock:
        stats = dict(_mapping_stats)

    return {
        "enabled": enabled,
        "datasets": dataset_info,
        "runtime_stats": stats,
    }


def reset_mapping_stats():
    """Reset runtime mapping statistics."""
    global _mapping_stats
    with _mapping_stats_lock:
        _mapping_stats = {}
