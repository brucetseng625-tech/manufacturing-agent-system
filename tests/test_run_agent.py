import unittest

from run_agent import extract_order_ids


class RunAgentTest(unittest.TestCase):
    def test_extract_numeric_order_id(self):
        self.assertEqual(extract_order_ids("這張急單 ORD-1001 能不能準時出？"), ["ORD-1001"])

    def test_extract_csv_style_order_id(self):
        self.assertEqual(
            extract_order_ids("這張急單 ORD-CSV-001 能不能準時出？"),
            ["ORD-CSV-001"],
        )


if __name__ == "__main__":
    unittest.main()
