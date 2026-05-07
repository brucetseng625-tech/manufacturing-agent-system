
import os
import unittest
from data_validator import validate_dataset

class DataValidatorTest(unittest.TestCase):
    def test_valid_orders(self):
        data = [
            {"order_id": "ORD-1", "customer": "A", "product": "P", "quantity": 10, "due_date": "2026-01-01", "priority": "High"}
        ]
        errors = validate_dataset("orders", data)
        self.assertEqual(len(errors), 0)

    def test_missing_field(self):
        data = [
            {"order_id": "ORD-1", "customer": "A"} # Missing others
        ]
        errors = validate_dataset("orders", data)
        self.assertTrue(len(errors) > 0)
        self.assertIn("Missing required field", " ".join(errors))

    def test_invalid_date(self):
        data = [
            {"order_id": "ORD-1", "customer": "A", "product": "P", "quantity": 10, "due_date": "not-a-date", "priority": "High"}
        ]
        errors = validate_dataset("orders", data)
        self.assertTrue(len(errors) > 0)
        self.assertIn("invalid date format", " ".join(errors))

    def test_wrong_type(self):
        data = [
            {"order_id": "ORD-1", "customer": "A", "product": "P", "quantity": "ten", "due_date": "2026-01-01", "priority": "High"}
        ]
        errors = validate_dataset("orders", data)
        self.assertTrue(len(errors) > 0)
        self.assertIn("expected int", " ".join(errors))
