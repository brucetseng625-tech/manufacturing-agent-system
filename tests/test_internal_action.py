import os
import unittest
import tempfile
from orchestrator import route_query
from skills.registry import get_registry
from skills.internal_action_summary import handle_internal_action_summary

class InternalActionTest(unittest.TestCase):
    def test_registry_routing_keywords(self):
        """Registry routes to internal action skill using keywords."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        registry = get_registry()
        
        skill = registry.match_skill("ORD-1001 行動計畫", [])
        self.assertIsNotNone(skill)
        self.assertEqual(skill["name"], "internal-action-summary")
        
        skill2 = registry.match_skill("ORD-1001 action plan", [])
        self.assertEqual(skill2["name"], "internal-action-summary")

    def test_skill_requires_order_id(self):
        """Skill returns error if no order ID provided."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = route_query("行動計畫", mock_data_dir)
        
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["type"], "missing_order_id")
        self.assertEqual(result["order_ids"], [])

    def test_skill_output_structure(self):
        """Skill returns all required fields."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = route_query("ORD-1001 action plan", mock_data_dir)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skill"], "internal-action-summary")
        
        data = result["data"]
        self.assertIn("order_id", data)
        self.assertIn("customer", data)
        self.assertIn("current_decision", data)
        self.assertIn("top_blockers", data)
        self.assertIn("immediate_actions", data)
        self.assertIn("owner_suggestion", data)
        self.assertIn("escalation_suggestion", data)
        self.assertIn("asana_note", data)
        self.assertIn("trace", data)

    def test_skill_asana_note_format(self):
        """Asana note is a single line string."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = route_query("ORD-1001 行動", mock_data_dir)
        
        asana_note = result["data"]["asana_note"]
        self.assertIsInstance(asana_note, str)
        self.assertIn("Action Required", asana_note)
        self.assertIn("Owner:", asana_note)

    def test_skill_escalation_logic(self):
        """Verify escalation suggestion exists and is a string."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = route_query("ORD-1001 action plan", mock_data_dir)
        
        escalation = result["data"]["escalation_suggestion"]
        self.assertIsInstance(escalation, str)
        self.assertGreater(len(escalation), 0)
        # If decision is can_ship_on_time, escalation is "None"
        if result["data"]["current_decision"] == "can_ship_on_time":
            self.assertEqual(escalation, "None")
