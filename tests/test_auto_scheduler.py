import unittest
import os
from skills.auto_scheduler import execute_auto_scheduler

class TestAutoScheduler(unittest.TestCase):
    def setUp(self):
        self.data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")

    def test_execute_auto_scheduler(self):
        res = execute_auto_scheduler(order_ids=["ORD-1001"], data_dir=self.data_dir)
        self.assertEqual(res["status"], "success")
        self.assertIn("WO-1001-B", res["decision"])
        self.assertIn("CNC-01", res["decision"])
        self.assertTrue(len(res["before"]) > 0)
        self.assertTrue(len(res["after"]) > 0)

if __name__ == "__main__":
    unittest.main()
