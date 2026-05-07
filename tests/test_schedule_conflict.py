
import os
import unittest
from skills.schedule_conflict_check import check_schedule_conflict

class ScheduleConflictTest(unittest.TestCase):
    def test_conflict_detection(self):
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = check_schedule_conflict(["ORD-1001", "ORD-1002"], mock_data_dir)

        self.assertEqual(result["status"], "conflict_detected")
        self.assertEqual(len(result["conflicts"]), 1)
        conflict = result["conflicts"][0]
        self.assertIn("CNC-01", conflict["machine_id"])
        self.assertEqual(conflict["winner"], "ORD-1001")
        self.assertEqual(conflict["loser"], "ORD-1002")
        self.assertIn("2026-05-14T16:00:00", conflict["suggestion"])

    def test_conflict_priority_is_stable_when_order_input_is_reversed(self):
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = check_schedule_conflict(["ORD-1002", "ORD-1001"], mock_data_dir)

        conflict = result["conflicts"][0]
        self.assertEqual(conflict["winner"], "ORD-1001")
        self.assertEqual(conflict["loser"], "ORD-1002")

    def test_no_conflict(self):
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = check_schedule_conflict(["ORD-1003"], mock_data_dir)
        self.assertEqual(result["status"], "no_conflict")
