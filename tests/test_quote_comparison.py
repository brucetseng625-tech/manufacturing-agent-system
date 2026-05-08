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
        self.assertEqual(result["details"]["material"], "Steel")

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

    def test_scoring_uses_reliability_and_quality(self):
        """Supplier with higher reliability may beat cheaper but less reliable one."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = handle_quote_comparison([], mock_data_dir, "Steel")
        
        self.assertNotIn("error", result)
        # Check that supplier_scores exist and include breakdown
        details = result.get("details", {})
        self.assertIn("supplier_scores", details)
        scores = details["supplier_scores"]
        # At least one supplier should have a breakdown with all 5 criteria
        for supplier, info in scores.items():
            self.assertIn("score", info)
            self.assertIn("breakdown", info)
            breakdown = info["breakdown"]
            for key in ("price_score", "reliability_score", "quality_score", "lead_time_score", "risk_score"):
                self.assertIn(key, breakdown)

    def test_scoring_prefers_reliable_over_cheap(self):
        """A reliable supplier with moderate price beats a cheap but unreliable one."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = handle_quote_comparison([], mock_data_dir, "Aluminum")
        
        self.assertNotIn("error", result)
        details = result.get("details", {})
        # Supplier A (reliability 0.95, $30) should beat Supplier D (reliability 0.55, $25)
        self.assertEqual(details["recommended_supplier"], "Supplier A")

    def test_tradeoffs_identified(self):
        """Tradeoffs between top suppliers are identified and documented."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = handle_quote_comparison([], mock_data_dir, "Steel")
        
        details = result.get("details", {})
        tradeoffs = details.get("tradeoffs", [])
        # With 3 Steel suppliers, there should be at least one tradeoff note
        self.assertGreater(len(tradeoffs), 0)
        # Tradeoff should mention price or reliability comparison
        tradeoff_text = " ".join(tradeoffs)
        self.assertTrue(
            "cheaper" in tradeoff_text.lower() or "reliability" in tradeoff_text.lower() or "lead time" in tradeoff_text.lower()
        )

    def test_recommendation_mentions_score_and_reliability(self):
        """Recommendation text includes score and reliability context."""
        mock_data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")
        result = handle_quote_comparison([], mock_data_dir, "Steel")
        
        # recommendation is normalized to next_action by schema
        next_action = result.get("next_action", "")
        self.assertIn("score", next_action.lower())
        self.assertIn(result["details"]["recommended_supplier"], next_action)

    def test_missing_reliability_field_graceful_fallback(self):
        """Skill works when supplier_reliability is missing (falls back to risk_level)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            import json
            # Create quotes without supplier_reliability
            quotes = [
                {"quote_id": "Q-1", "material": "Steel", "supplier": "Alpha",
                 "unit_price": 40.0, "currency": "USD", "lead_time_days": 5,
                 "moq": 100, "quality_rating": 4.0, "risk_level": "low",
                 "valid_until": "2026-06-01"},
                {"quote_id": "Q-2", "material": "Steel", "supplier": "Beta",
                 "unit_price": 35.0, "currency": "USD", "lead_time_days": 10,
                 "moq": 200, "quality_rating": 3.5, "risk_level": "high",
                 "valid_until": "2026-05-15"},
            ]
            with open(os.path.join(tmp_dir, "quotes.json"), "w") as f:
                json.dump(quotes, f)
            
            result = handle_quote_comparison([], tmp_dir, "Steel")
            self.assertNotIn("error", result)
            details = result.get("details", {})
            self.assertIn("recommended_supplier", details)
            # Score should still be computed via fallback
            self.assertIn("supplier_scores", details)
