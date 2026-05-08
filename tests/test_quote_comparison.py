import os
import unittest
import tempfile
from orchestrator import route_query
from skills.registry import get_registry
from skills.quote_comparison_summary import handle_quote_comparison

class QuoteComparisonTest(unittest.TestCase):
    def test_registry_routing_keywords(self):
        """Registry routes to quote skill using keywords."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        registry = get_registry()
        
        skill = registry.match_skill("幫我比較 Steel 的供應商報價", [])
        self.assertIsNotNone(skill)
        self.assertEqual(skill["name"], "quote-comparison-summary")
        
        skill2 = registry.match_skill("quote comparison for steel", [])
        self.assertEqual(skill2["name"], "quote-comparison-summary")

    def test_skill_no_order_id_required(self):
        """Skill executes successfully without order IDs."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = route_query("Steel 報價", mock_data_dir)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skill"], "quote-comparison-summary")
        self.assertEqual(result["order_ids"], [])
        # Single material query returns fields directly
        self.assertEqual(result["data"]["details"]["material"], "Steel")
        self.assertIn("recommended_supplier", result["data"]["details"])

    def test_skill_csv_mode(self):
        """Skill reads correctly from CSV data."""
        data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        # Check if quotes.csv exists in data dir
        if not os.path.exists(os.path.join(data_dir, "quotes.csv")):
            self.skipTest("data/quotes.csv not found")
            
        result = route_query("Steel 報價", data_dir)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skill"], "quote-comparison-summary")
        self.assertEqual(result["data"]["details"]["material"], "Steel")

    def test_skill_recommendation_logic(self):
        """Skill recommends lowest risk/reasonable price supplier."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = handle_quote_comparison([], mock_data_dir, "Steel 報價")
        
        self.assertNotIn("error", result)
        # Check standardized fields
        self.assertIn("decision", result)
        self.assertIn("confidence", result)
        # Check material-specific fields in details
        self.assertEqual(result["details"]["material"], "Steel")
        self.assertIn("recommended_supplier", result["details"])
        self.assertIn("price_spread", result["details"])
        self.assertIn("risks", result["details"])

    def test_unspecified_material_returns_all_materials(self):
        """Generic quote query returns all material summaries."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = route_query("幫我比較供應商報價", mock_data_dir)

        self.assertEqual(result["status"], "success")
        # Materials are now in details
        self.assertIn("materials", result["data"]["details"])
        self.assertGreater(len(result["data"]["details"]["materials"]), 1)

    def test_validation_catches_quote_errors(self):
        """Validation detects missing fields or bad types in quotes."""
        with tempfile.TemporaryDirectory() as bad_dir:
            # Create a quotes.json with missing fields
            import json
            with open(os.path.join(bad_dir, "quotes.json"), "w") as f:
                json.dump([{"quote_id": "Q-1", "material": "Steel"}], f) # Missing required fields
            
            result = route_query("Steel 報價", bad_dir)
            
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["type"], "validation_failed")
            # Should mention missing required field
            self.assertIn("Missing required field", " ".join(result["details"]))

    def test_validation_catches_type_errors(self):
        """Validation detects bad numeric types in quotes."""
        with tempfile.TemporaryDirectory() as bad_dir:
            import json
            with open(os.path.join(bad_dir, "quotes.json"), "w") as f:
                json.dump([{
                    "quote_id": "Q-1", "material": "Steel", "supplier": "A",
                    "unit_price": "abc", "currency": "USD", "lead_time_days": "fast",
                    "moq": "100", "quality_rating": "good", "risk_level": "low", "valid_until": "2026-06-01"
                }], f)
            
            result = route_query("Steel 報價", bad_dir)
            
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["type"], "validation_failed")
            self.assertIn("expected", " ".join(result["details"]).lower())
