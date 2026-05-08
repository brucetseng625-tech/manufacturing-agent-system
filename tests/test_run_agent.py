import unittest
import tempfile
import subprocess
import sys
from pathlib import Path

from orchestrator import extract_order_ids, validate_data_dir


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

    def test_live_data_source_cli_returns_structured_error(self):
        repo_root = Path(__file__).resolve().parent.parent
        proc = subprocess.run(
            [
                sys.executable,
                "run_agent.py",
                "--data-source",
                "live",
                "ORD-1001",
                "準時出貨",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )

        self.assertEqual(proc.returncode, 1)
        self.assertIn("Operation Failed (internal_error)", proc.stdout)
        self.assertIn("LiveDataProvider is a skeleton", proc.stdout)
        self.assertNotIn("Traceback", proc.stderr)

    def test_show_config_cli(self):
        repo_root = Path(__file__).resolve().parent.parent
        proc = subprocess.run(
            [sys.executable, "run_agent.py", "--show-config"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )

        self.assertEqual(proc.returncode, 0)
        self.assertIn("Config source:", proc.stdout)
        self.assertIn("\"server\"", proc.stdout)


if __name__ == "__main__":
    unittest.main()
