import json
import os
from data_loader import load_json_or_csv
from data_validator import validate_dataset

# Import existing skills
from skills.delivery_risk import analyze_delivery_risk
from skills.schedule_conflict_check import check_schedule_conflict
from skills.quote_comparison_summary import handle_quote_comparison
from skills.sales_response_draft import handle_sales_response_draft
from skills.internal_action_summary import handle_internal_action_summary

class SkillRegistry:
    """
    Central registry for all agent skills.
    Uses score-based priority matching to resolve keyword collisions.
    """
    
    def __init__(self):
        self.skills = []
        self._register_builtins()
    
    def _register_builtins(self):
        """Register built-in skills with routing metadata."""
        
        # 1. Schedule Conflict Check
        # Default route for multi-order queries when no explicit intent is given.
        self.register({
            "name": "schedule-conflict-check",
            "intent": "schedule_conflict_check",
            "keywords": ["衝突", "conflict", "schedule", "overlap", "排程"],
            "exact_keywords": ["排程衝突", "schedule conflict"],
            "handler": self._handle_schedule_conflict,
            "requires_order_id": True,
            "triggers_on_multi_order": True,
            "priority": 1,  # Lower base priority; wins on multi-order fallback or explicit match
            "data_files": ["schedule.json", "work_orders.json", "orders.json"]
        })
        
        # 2. Delivery Risk Analysis
        self.register({
            "name": "delivery-risk-analysis",
            "intent": "delivery_risk_analysis",
            "keywords": ["準時", "出貨", "delivery", "ship", "risk", "交期"],
            "exact_keywords": ["交期風險", "delivery risk"],
            "handler": self._handle_delivery_risk,
            "requires_order_id": True,
            "triggers_on_multi_order": False,
            "priority": 2,
            "data_files": ["orders.json", "work_orders.json", "materials.json", "machines.json", "operators.json", "schedule.json"]
        })
        
        # 3. Quote Comparison Summary
        # Non-order-based, high specificity on commercial keywords
        self.register({
            "name": "quote-comparison-summary",
            "intent": "quote_comparison_summary",
            "keywords": ["報價", "quote", "supplier", "供應商", "price", "採購", "cost"],
            "exact_keywords": ["報價比較", "quote comparison", "cost comparison", "供應商比較"],
            "handler": handle_quote_comparison,
            "requires_order_id": False,
            "triggers_on_multi_order": False,
            "passes_query": True,
            "priority": 3,  # Higher priority for explicit commercial queries
            "data_files": ["quotes.json"]
        })

        # 4. Sales Response Draft
        # Customer-facing communication, requires order context
        self.register({
            "name": "sales-response-draft",
            "intent": "sales_response_draft",
            "keywords": ["回覆", "客戶", "sales", "reply", "draft", "email", "customer", "通知"],
            "exact_keywords": ["回覆客戶", "customer update", "sales reply", "client email"],
            "handler": handle_sales_response_draft,
            "requires_order_id": True,
            "triggers_on_multi_order": False,
            "passes_query": True,
            "priority": 4,  # High priority when communication intent is explicit
            "data_files": ["orders.json", "work_orders.json", "materials.json", "machines.json", "operators.json", "schedule.json"]
        })

        # 5. Internal Action Summary
        # Internal ops/PM coordination
        self.register({
            "name": "internal-action-summary",
            "intent": "internal_action_summary",
            "keywords": ["行動", "action", "follow up", "internal", "summary", "PM", "production", "escalate", "內部", "後續"],
            "exact_keywords": ["內部行動", "internal action", "PM action", "follow up", "escalate"],
            "handler": handle_internal_action_summary,
            "requires_order_id": True,
            "triggers_on_multi_order": False,
            "passes_query": True,
            "priority": 3,
            "data_files": ["orders.json", "work_orders.json", "materials.json", "machines.json", "operators.json", "schedule.json"]
        })
    
    def register(self, skill_config):
        """
        Register a new skill.
        
        Args:
            skill_config (dict): {
                "name": str,
                "intent": str,
                "keywords": list,         # Substring matches (weight: 2)
                "exact_keywords": list,   # Phrase/substring matches (weight: 5)
                "handler": callable,
                "requires_order_id": bool,
                "triggers_on_multi_order": bool,
                "priority": int,          # Tie-breaker & base score
                "data_files": list
            }
        """
        self.skills.append(skill_config)
    
    def match_skill(self, query, order_ids):
        """
        Find the best matching skill using score-based routing.
        
        Scoring rules:
        - exact_keywords match: +5 points
        - keywords match: +2 points
        - triggers_on_multi_order with >1 order: +3 points
        - requires_order_id with 0 orders: disqualified (-100)
        - Tie-breaker: priority (higher wins), then registration order.
        
        Returns:
            dict: Matched skill config, or None if no match.
        """
        query_lower = query.lower()
        candidates = []
        
        for idx, skill in enumerate(self.skills):
            score = 0
            
            # Exact keyword matches (high weight)
            for kw in skill.get("exact_keywords", []):
                if kw.lower() in query_lower:
                    score += 5
                    
            # Partial keyword matches (standard weight)
            for kw in skill.get("keywords", []):
                if kw.lower() in query_lower:
                    score += 2
                    
            # Multi-order boost
            if len(order_ids) > 1 and skill.get("triggers_on_multi_order"):
                score += 3
                
            # Base priority ONLY applies if there's at least one keyword match or explicit trigger
            if score > 0:
                score += skill.get("priority", 0)
                
            candidates.append((skill, score, idx))
            
        # Filter valid candidates (score > 0)
        valid = [(s, sc, i) for s, sc, i in candidates if sc > 0]
        
        if not valid:
            return None
            
        # Sort: highest score first, then highest priority, then earliest registration
        valid.sort(key=lambda x: (-x[1], -x[0].get("priority", 0), x[2]))
        return valid[0][0]
    
    def execute(self, skill_config, order_ids, data_dir, query=None):
        """
        Execute a matched skill.
        
        Returns:
            dict: Skill result or error.
        """
        handler = skill_config["handler"]
        if skill_config.get("passes_query"):
            return handler(order_ids, data_dir, query)
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
