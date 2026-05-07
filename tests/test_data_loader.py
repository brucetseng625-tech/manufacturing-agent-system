
import os
import unittest
from data_loader import load_json_or_csv

class DataLoaderTest(unittest.TestCase):
    def test_load_json(self):
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        data = load_json_or_csv(mock_data_dir, "orders.json")
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        self.assertIn("order_id", data[0])

    def test_load_csv(self):
        csv_data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        data = load_json_or_csv(csv_data_dir, "orders.csv")
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        self.assertIn("order_id", data[0])
        # Check type conversion
        self.assertIsInstance(data[0]["quantity"], int)

    def test_fallback_json(self):
        # If both exist, JSON should be preferred (or CSV if JSON missing)
        # In mock_data, only JSON exists.
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        data = load_json_or_csv(mock_data_dir, "orders.json")
        self.assertIsInstance(data, list)
