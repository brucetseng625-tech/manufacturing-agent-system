import json
import os
from data_loader import load_json_or_csv
from data_validator import validate_dataset

# Import existing skills
from skills.delivery_risk import analyze_delivery_risk
from skills.schedule_conflict_check import check_schedule_conflict

class SkillRegistry:
    """
    Central registry for all agent skills.
    Eliminates hardcoded if/else routing in orchestrator.
    """
    
    def __init__(self):
        self.skills = []
        self._register_builtins()
    
    def _register_builtins(self):
        """Register built-in skills."""
        
        # 1. Schedule Conflict Check
        # Triggers on keywords OR multiple order IDs
        self.register({
            "name": "schedule-conflict-check",
            "intent": "schedule_conflict_check",
            "keywords": ["衝突", "conflict", "schedule", "overlap", "排程"],
            "handler": self._handle_schedule_conflict,
            "requires_order_id": True,
            "triggers_on_multi_order": True,
            "data_files": ["schedule.json", "work_orders.json", "orders.json"]
        })
        
        # 2. Delivery Risk Analysis
        # Triggers on keywords
        self.register({
            "name": "delivery-risk-analysis",
            "intent": "delivery_risk_analysis",
            "keywords": ["準時", "出貨", "delivery", "ship", "risk", "交期"],
            "handler": self._handle_delivery_risk,
            "requires_order_id": True,
            "triggers_on_multi_order": False,
            "data_files": ["orders.json", "work_orders.json", "materials.json", "machines.json", "operators.json", "schedule.json"]
        })
    
    def register(self, skill_config):
        """
        Register a new skill.
        
        Args:
            skill_config (dict): {
                "name": str,              # e.g. "quote-comparison"
                "intent": str,            # e.g. "quote_comparison"
                "keywords": list,         # e.g. ["報價", "quote", "price"]
                "handler": callable,      # Function that handles the skill
                "requires_order_id": bool,# Does this skill need order ID(s)?
                "triggers_on_multi_order": bool, # Auto-route if multiple orders?
                "data_files": list        # Required data files for validation
            }
        """
        self.skills.append(skill_config)
    
    def match_skill(self, query, order_ids):
        """
        Find the best matching skill for a query.
        
        Returns:
            dict: Matched skill config, or None if no match.
        """
        query_lower = query.lower()
        
        # Check multi-order trigger first
        if len(order_ids) > 1:
            for skill in self.skills:
                if skill.get("triggers_on_multi_order"):
                    return skill
        
        # Check keyword matches
        for skill in self.skills:
            if any(kw.lower() in query_lower for kw in skill["keywords"]):
                return skill
        
        return None
    
    def execute(self, skill_config, order_ids, data_dir):
        """
        Execute a matched skill.
        
        Returns:
            dict: Skill result or error.
        """
        handler = skill_config["handler"]
        return handler(order_ids, data_dir)
    
    # --- Built-in Handlers ---
    
    def _handle_schedule_conflict(self, order_ids, data_dir):
        return check_schedule_conflict(order_ids, data_dir)
    
    def _handle_delivery_risk(self, order_ids, data_dir):
        if not order_ids:
            return {"error": "Order ID is required for delivery risk analysis."}
        result = analyze_delivery_risk(order_ids[0], data_dir)
        return result

# Global singleton
registry = SkillRegistry()

def get_registry():
    """Get the global skill registry instance."""
    return registry
