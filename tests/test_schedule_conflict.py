
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
        self.assertEqual(conflict["winner"], "ORD-1001") # High priority
        self.assertEqual(conflict["loser"], "ORD-1002")

    def test_no_conflict(self):
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = check_schedule_conflict(["ORD-1001"], mock_data_dir)
        self.assertEqual(result["status"], "no_conflict")
