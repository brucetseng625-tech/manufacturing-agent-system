"""Tests for data_mapper — schema mapping, validation, and diagnostics."""

import unittest
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_mapper import (
    SchemaMapper,
    SchemaValidator,
    apply_mapping,
    apply_mapping_single,
    get_mapping_diagnostics,
    reset_mapping_stats,
    _coerce_value,
)
from config import set_config


class TestCoerceValue(unittest.TestCase):
    """Type coercion tests."""

    def test_string_passthrough(self):
        self.assertEqual(_coerce_value("hello", "str"), (True, "hello"))

    def test_string_to_int(self):
        self.assertEqual(_coerce_value("42", "int"), (True, 42))

    def test_string_to_float(self):
        self.assertEqual(_coerce_value("3.14", "float"), (True, 3.14))

    def test_int_to_float(self):
        self.assertEqual(_coerce_value(42, "float"), (True, 42.0))

    def test_float_to_int(self):
        self.assertEqual(_coerce_value(3.14, "int"), (True, 3))

    def test_string_float_to_int(self):
        self.assertEqual(_coerce_value("123.0", "int"), (True, 123))

    def test_bool_true_strings(self):
        for val in ("true", "True", "1", "yes"):
            success, result = _coerce_value(val, "bool")
            self.assertTrue(success)
            self.assertTrue(result)

    def test_bool_false_strings(self):
        for val in ("false", "0", "no"):
            success, result = _coerce_value(val, "bool")
            self.assertTrue(success)
            self.assertFalse(result)

    def test_none_passthrough(self):
        self.assertEqual(_coerce_value(None, "int"), (True, None))

    def test_unknown_type_passthrough(self):
        self.assertEqual(_coerce_value("anything", "xyz"), (True, "anything"))

    def test_type_mismatch(self):
        success, result = _coerce_value("not_a_number", "int")
        self.assertFalse(success)
        self.assertEqual(result, "not_a_number")


class TestSchemaMapper(unittest.TestCase):
    """Field mapping tests."""

    def test_no_mapping(self):
        mapper = SchemaMapper()
        record = {"id": 1, "name": "test"}
        self.assertEqual(mapper.map_record(record), {"id": 1, "name": "test"})

    def test_simple_mapping(self):
        mapper = SchemaMapper({"id": "order_id", "name": "customer"})
        record = {"id": 1, "name": "test"}
        result = mapper.map_record(record)
        self.assertEqual(result["order_id"], 1)
        self.assertEqual(result["customer"], "test")
        self.assertNotIn("id", result)
        self.assertNotIn("name", result)

    def test_partial_mapping(self):
        mapper = SchemaMapper({"id": "order_id"})
        record = {"id": 1, "name": "test", "extra": True}
        result = mapper.map_record(record)
        self.assertEqual(result["order_id"], 1)
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["extra"], True)
        self.assertNotIn("id", result)

    def test_mapping_preserves_unmapped(self):
        mapper = SchemaMapper({"ext_a": "int_a"})
        record = {"ext_a": 1, "ext_b": 2, "ext_c": 3}
        result = mapper.map_record(record)
        self.assertEqual(result["int_a"], 1)
        self.assertEqual(result["ext_b"], 2)
        self.assertEqual(result["ext_c"], 3)

    def test_mapping_with_overlapping_names(self):
        # When external name maps to internal, but another field has same internal name
        mapper = SchemaMapper({"a": "x"})
        record = {"a": 1, "x": 2}
        result = mapper.map_record(record)
        # "a" maps to "x", so "x" should be 1
        self.assertEqual(result["x"], 1)

    def test_empty_record(self):
        mapper = SchemaMapper({"a": "b"})
        self.assertEqual(mapper.map_record({}), {})


class TestSchemaValidator(unittest.TestCase):
    """Validation and normalization tests."""

    def test_valid_record(self):
        validator = SchemaValidator(
            required_fields=["order_id", "customer"],
            type_rules={"quantity": "int"},
        )
        success, result, issues = validator.validate_and_normalize({
            "order_id": "ORD-1", "customer": "Test", "quantity": "100"
        })
        self.assertTrue(success)
        self.assertEqual(result["quantity"], 100)
        self.assertEqual(issues, [])

    def test_missing_required_field(self):
        validator = SchemaValidator(required_fields=["order_id", "customer"])
        success, result, issues = validator.validate_and_normalize({
            "order_id": "ORD-1"
        })
        self.assertFalse(success)
        self.assertIn("missing_required: customer", issues)

    def test_type_coercion_success(self):
        validator = SchemaValidator(
            required_fields=["id"],
            type_rules={"id": "int", "price": "float"},
        )
        success, result, issues = validator.validate_and_normalize({
            "id": "42", "price": "9.99"
        })
        self.assertTrue(success)
        self.assertEqual(result["id"], 42)
        self.assertEqual(result["price"], 9.99)

    def test_type_coercion_failure(self):
        validator = SchemaValidator(
            required_fields=["id"],
            type_rules={"id": "int"},
        )
        success, result, issues = validator.validate_and_normalize({
            "id": "not_a_number"
        })
        self.assertFalse(success)
        self.assertTrue(any("type_mismatch" in i for i in issues))

    def test_default_values(self):
        validator = SchemaValidator(
            required_fields=["id"],
            default_values={"priority": "Normal", "tier": "Standard"},
        )
        success, result, issues = validator.validate_and_normalize({"id": 1})
        self.assertTrue(success)
        self.assertEqual(result["priority"], "Normal")
        self.assertEqual(result["tier"], "Standard")

    def test_default_values_not_override(self):
        validator = SchemaValidator(
            required_fields=["id"],
            default_values={"priority": "Normal"},
        )
        success, result, issues = validator.validate_and_normalize({"id": 1, "priority": "High"})
        self.assertTrue(success)
        self.assertEqual(result["priority"], "High")  # Should not override

    def test_empty_validator(self):
        validator = SchemaValidator()
        success, result, issues = validator.validate_and_normalize({"anything": True})
        self.assertTrue(success)
        self.assertEqual(result, {"anything": True})
        self.assertEqual(issues, [])

    def test_none_required_value(self):
        validator = SchemaValidator(required_fields=["order_id"])
        success, result, issues = validator.validate_and_normalize({"order_id": None})
        self.assertFalse(success)
        self.assertIn("missing_required: order_id", issues)


class TestApplyMapping(unittest.TestCase):
    """Integration tests for the apply_mapping pipeline."""

    def setUp(self):
        self._original_config = {}
        reset_mapping_stats()

    def _set_config(self, config_dict):
        """Helper to set config for tests."""
        from config import set_config
        set_config(config_dict)

    def test_mapping_disabled_returns_raw_data(self):
        self._set_config({"live_provider": {"data_mapping": {"enabled": False}}})
        data = [{"order_id": "ORD-1", "customer": "Test"}]
        mapped, report = apply_mapping(data, "orders")
        self.assertEqual(mapped, data)
        self.assertEqual(report["total"], 1)
        self.assertEqual(report["mapped"], 1)
        self.assertEqual(report["errors"], 0)

    def test_mapping_disabled_no_config(self):
        self._set_config({})
        data = [{"id": 1}]
        mapped, report = apply_mapping(data, "orders")
        self.assertEqual(mapped, data)

    def test_mapping_enabled_simple(self):
        self._set_config({
            "live_provider": {
                "data_mapping": {
                    "enabled": True,
                    "datasets": {
                        "orders": {
                            "enabled": True,
                            "field_mapping": {"id": "order_id", "client": "customer"},
                            "required_fields": ["order_id"],
                        }
                    }
                }
            }
        })
        data = [{"id": "ORD-1", "client": "Test Co"}]
        mapped, report = apply_mapping(data, "orders")
        self.assertEqual(len(mapped), 1)
        self.assertEqual(mapped[0]["order_id"], "ORD-1")
        self.assertEqual(mapped[0]["customer"], "Test Co")
        self.assertNotIn("id", mapped[0])
        self.assertEqual(report["errors"], 0)

    def test_mapping_with_defaults(self):
        self._set_config({
            "live_provider": {
                "data_mapping": {
                    "enabled": True,
                    "datasets": {
                        "orders": {
                            "enabled": True,
                            "field_mapping": {"id": "order_id"},
                            "required_fields": ["order_id"],
                            "default_values": {"priority": "Normal", "tier": "Standard"},
                        }
                    }
                }
            }
        })
        data = [{"id": "ORD-1"}]
        mapped, report = apply_mapping(data, "orders")
        self.assertEqual(len(mapped), 1)
        self.assertEqual(mapped[0]["priority"], "Normal")
        self.assertEqual(mapped[0]["tier"], "Standard")

    def test_mapping_skips_invalid_records(self):
        self._set_config({
            "live_provider": {
                "data_mapping": {
                    "enabled": True,
                    "datasets": {
                        "orders": {
                            "enabled": True,
                            "field_mapping": {"id": "order_id"},
                            "required_fields": ["order_id"],
                        }
                    }
                }
            }
        })
        data = [
            {"id": "ORD-1"},      # valid
            {"name": "no_id"},    # missing required
            {"id": "ORD-2"},      # valid
        ]
        mapped, report = apply_mapping(data, "orders")
        self.assertEqual(len(mapped), 2)
        self.assertEqual(report["total"], 3)
        self.assertEqual(report["errors"], 1)
        self.assertEqual(report["mapped"], 2)

    def test_non_list_input(self):
        self._set_config({"live_provider": {"data_mapping": {"enabled": True}}})
        mapped, report = apply_mapping("not a list", "orders")
        self.assertEqual(mapped, [])
        self.assertEqual(report["errors"], 1)

    def test_empty_list(self):
        self._set_config({"live_provider": {"data_mapping": {"enabled": True}}})
        mapped, report = apply_mapping([], "orders")
        self.assertEqual(mapped, [])
        self.assertEqual(report["total"], 0)

    def test_dataset_not_configured(self):
        self._set_config({
            "live_provider": {
                "data_mapping": {
                    "enabled": True,
                    "datasets": {}
                }
            }
        })
        data = [{"id": 1}]
        mapped, report = apply_mapping(data, "unknown_dataset")
        self.assertEqual(mapped, data)  # Returns as-is

    def test_dataset_disabled(self):
        self._set_config({
            "live_provider": {
                "data_mapping": {
                    "enabled": True,
                    "datasets": {
                        "orders": {"enabled": False}
                    }
                }
            }
        })
        data = [{"id": 1}]
        mapped, report = apply_mapping(data, "orders")
        self.assertEqual(mapped, data)

    def test_type_coercion_in_mapping(self):
        self._set_config({
            "live_provider": {
                "data_mapping": {
                    "enabled": True,
                    "datasets": {
                        "orders": {
                            "enabled": True,
                            "field_mapping": {"qty": "quantity"},
                            "required_fields": ["quantity"],
                            "type_rules": {"quantity": "int"},
                        }
                    }
                }
            }
        })
        data = [{"qty": "42"}]
        mapped, report = apply_mapping(data, "orders")
        self.assertEqual(len(mapped), 1)
        self.assertEqual(mapped[0]["quantity"], 42)
        self.assertIsInstance(mapped[0]["quantity"], int)

    def test_error_details_capped(self):
        """Error details should be capped at 10 entries."""
        self._set_config({
            "live_provider": {
                "data_mapping": {
                    "enabled": True,
                    "datasets": {
                        "orders": {
                            "enabled": True,
                            "required_fields": ["order_id"],
                        }
                    }
                }
            }
        })
        # Create 15 invalid records
        data = [{"name": f"test_{i}"} for i in range(15)]
        mapped, report = apply_mapping(data, "orders")
        self.assertEqual(report["errors"], 15)
        self.assertEqual(report["mapped"], 0)
        self.assertLessEqual(len(report["error_details"]), 10)


class TestApplyMappingSingle(unittest.TestCase):
    """Tests for single record mapping."""

    def setUp(self):
        from config import set_config
        set_config({})

    def test_mapping_disabled(self):
        from config import set_config
        set_config({"live_provider": {"data_mapping": {"enabled": False}}})
        record = {"id": 1}
        success, result, issues = apply_mapping_single(record, "orders")
        self.assertTrue(success)
        self.assertEqual(result, record)

    def test_mapping_enabled(self):
        from config import set_config
        set_config({
            "live_provider": {
                "data_mapping": {
                    "enabled": True,
                    "datasets": {
                        "orders": {
                            "enabled": True,
                            "field_mapping": {"id": "order_id"},
                            "required_fields": ["order_id"],
                        }
                    }
                }
            }
        })
        record = {"id": "ORD-1"}
        success, result, issues = apply_mapping_single(record, "orders")
        self.assertTrue(success)
        self.assertEqual(result["order_id"], "ORD-1")

    def test_missing_required(self):
        from config import set_config
        set_config({
            "live_provider": {
                "data_mapping": {
                    "enabled": True,
                    "datasets": {
                        "orders": {
                            "enabled": True,
                            "required_fields": ["order_id"],
                        }
                    }
                }
            }
        })
        record = {"name": "test"}
        success, result, issues = apply_mapping_single(record, "orders")
        self.assertFalse(success)
        self.assertTrue(any("missing_required" in i for i in issues))


class TestMappingDiagnostics(unittest.TestCase):
    """Tests for mapping diagnostics."""

    def setUp(self):
        from config import set_config
        set_config({})
        reset_mapping_stats()

    def test_diagnostics_disabled(self):
        diag = get_mapping_diagnostics()
        self.assertFalse(diag["enabled"])
        self.assertEqual(diag["datasets"], {})

    def test_diagnostics_enabled(self):
        from config import set_config
        set_config({
            "live_provider": {
                "data_mapping": {
                    "enabled": True,
                    "datasets": {
                        "orders": {
                            "enabled": True,
                            "field_mapping": {"id": "order_id"},
                            "required_fields": ["order_id"],
                            "type_rules": {"quantity": "int"},
                            "default_values": {"priority": "Normal"},
                        },
                        "materials": {"enabled": False}
                    }
                }
            }
        })
        diag = get_mapping_diagnostics()
        self.assertTrue(diag["enabled"])
        self.assertIn("orders", diag["datasets"])
        self.assertIn("materials", diag["datasets"])
        self.assertTrue(diag["datasets"]["orders"]["enabled"])
        self.assertEqual(diag["datasets"]["orders"]["field_mapping_count"], 1)
        self.assertEqual(diag["datasets"]["orders"]["required_field_count"], 1)
        self.assertEqual(diag["datasets"]["orders"]["type_rule_count"], 1)
        self.assertEqual(diag["datasets"]["orders"]["default_value_count"], 1)
        self.assertFalse(diag["datasets"]["materials"]["enabled"])

    def test_runtime_stats(self):
        from config import set_config
        set_config({
            "live_provider": {
                "data_mapping": {
                    "enabled": True,
                    "datasets": {
                        "orders": {
                            "enabled": True,
                            "required_fields": ["id"],
                        }
                    }
                }
            }
        })
        # Run some mappings
        apply_mapping([{"id": 1}, {"name": "no_id"}], "orders")

        diag = get_mapping_diagnostics()
        stats = diag["runtime_stats"]
        self.assertIn("orders", stats)
        self.assertEqual(stats["orders"]["total"], 2)
        self.assertEqual(stats["orders"]["mapped"], 1)
        self.assertEqual(stats["orders"]["errors"], 1)

    def test_reset_stats(self):
        from config import set_config
        set_config({
            "live_provider": {
                "data_mapping": {
                    "enabled": True,
                    "datasets": {
                        "orders": {
                            "enabled": True,
                            "required_fields": ["id"],
                        }
                    }
                }
            }
        })
        apply_mapping([{"id": 1}], "orders")
        diag = get_mapping_diagnostics()
        self.assertEqual(diag["runtime_stats"]["orders"]["total"], 1)

        reset_mapping_stats()
        diag = get_mapping_diagnostics()
        self.assertEqual(diag["runtime_stats"], {})


if __name__ == "__main__":
    unittest.main()
