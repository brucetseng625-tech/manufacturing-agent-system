import unittest
import tempfile
from pathlib import Path

from run_agent import extract_order_ids, validate_data_dir


class RunAgentTest(unittest.TestCase):
    def test_extract_numeric_order_id(self):
        self.assertEqual(extract_order_ids("這張急單 ORD-1001 能不能準時出？"), ["ORD-1001"])

    def test_extract_csv_style_order_id(self):
        self.assertEqual(
            extract_order_ids("這張急單 ORD-CSV-001 能不能準時出？"),
            ["ORD-CSV-001"],
        )

    def test_validate_data_dir_reports_invalid_csv(self):
        with tempfile.TemporaryDirectory() as data_dir:
            orders_path = Path(data_dir) / "orders.csv"
            orders_path.write_text(
                "order_id,customer,product,quantity,priority\n"
                "ORD-BAD-001,Customer,Widget,10,High\n",
                encoding="utf-8",
            )

            errors = validate_data_dir(data_dir)

        self.assertTrue(errors)
        self.assertIn("Missing required field 'due_date'", " ".join(errors))


if __name__ == "__main__":
    unittest.main()
