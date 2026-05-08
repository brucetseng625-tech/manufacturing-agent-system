import json
import os
from data_loader import load_json_or_csv
from data_validator import validate_dataset
from skills.policy import get_policy

# Import existing skills
from skills.delivery_risk import analyze_delivery_risk
from skills.schedule_conflict_check import check_schedule_conflict
from skills.quote_comparison_summary import handle_quote_comparison
from skills.sales_response_draft import handle_sales_response_draft
from skills.internal_action_summary import handle_internal_action_summary
from skills.expedite_options import handle_expedite_options
from skills.material_shortage_recovery import handle_material_shortage_recovery
from skills.capacity_rebalance import handle_capacity_rebalance
from skills.supplier_followup_draft import handle_supplier_followup_draft

class SkillRegistry:
    """
    Central registry for all agent skills and teams.
    Uses score-based priority matching to resolve keyword collisions.
    """
    
    def __init__(self):
        self.skills = []
        self.teams = []
        self._register_builtins()
        self._register_teams()
    
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

        # 6. Expedite Options
        # Planning skill for at-risk orders — evaluates concrete recovery options
        self.register({
            "name": "expedite-options",
            "intent": "expedite_options",
            "keywords": ["加急", "expedite", "趕工", "overtime", "搶救", "recovery", "選項", "options", "方案"],
            "exact_keywords": ["加急方案", "expedite options", "趕工選項", "recovery plan"],
            "handler": handle_expedite_options,
            "requires_order_id": True,
            "triggers_on_multi_order": False,
            "passes_query": True,
            "priority": 5,  # Higher priority for explicit expedite intent
            "data_files": ["orders.json", "work_orders.json", "materials.json", "machines.json", "schedule.json"]
        })

        # 7. Material Shortage Recovery
        # Focused on material shortage scenarios — concrete sourcing strategies
        self.register({
            "name": "material-shortage-recovery",
            "intent": "material_shortage_recovery",
            "keywords": ["缺料", "shortage", "補貨", "material", "procurement", "採購", "物料", "supply"],
            "exact_keywords": ["缺料恢復", "material shortage", "補貨策略", "shortage recovery"],
            "handler": handle_material_shortage_recovery,
            "requires_order_id": True,
            "triggers_on_multi_order": False,
            "passes_query": True,
            "priority": 6,
            "data_files": ["orders.json", "materials.json", "work_orders.json"]
        })

        # 8. Capacity Rebalance
        # Multi-order capacity planning — machine load balancing and scheduling
        self.register({
            "name": "capacity-rebalance",
            "intent": "capacity_rebalance",
            "keywords": ["產能", "capacity", "rebalance", "機台", "負載", "load", "重分配", "排程優化"],
            "exact_keywords": ["產能重分配", "capacity rebalance", "機台負載平衡", "load balancing"],
            "handler": handle_capacity_rebalance,
            "requires_order_id": True,
            "triggers_on_multi_order": False,
            "passes_query": True,
            "priority": 7,
            "data_files": ["orders.json", "work_orders.json", "machines.json", "schedule.json"]
        })

        # 9. Supplier Follow-up Draft
        # Supplier-facing communication drafts for shortage/expedite/RFQ scenarios
        self.register({
            "name": "supplier-followup-draft",
            "intent": "supplier_followup_draft",
            "keywords": ["跟進", "followup", "follow-up", "信件", "draft", "procurement"],
            "exact_keywords": ["供應商跟進", "supplier followup", "follow-up draft", "採購跟進", "supplier inquiry"],
            "handler": handle_supplier_followup_draft,
            "requires_order_id": True,
            "triggers_on_multi_order": False,
            "passes_query": True,
            "priority": 8,
            "data_files": ["orders.json", "materials.json", "quotes.json"]
        })

    def _register_teams(self):
        """Register team workflows that chain multiple skills."""
        
        # 1. Comprehensive Order Analysis
        # Triggers on "全面分析", "comprehensive", "all reports", "完整報告"
        # Chain: delivery-risk -> sales-response-draft + internal-action-summary
        self.register_team({
            "name": "comprehensive-analysis",
            "intent": "comprehensive_analysis",
            "keywords": ["全面分析", "comprehensive", "all reports", "完整報告", "全方位"],
            "exact_keywords": ["comprehensive analysis", "完整報告", "全面分析"],
            "steps": [
                {"skill": "delivery-risk-analysis", "alias": "risk"},
                {"skill": "sales-response-draft", "alias": "sales"},
                {"skill": "internal-action-summary", "alias": "internal"},
            ],
            "requires_order_id": True,
            "priority": 10,
        })

        # 2. Risk Response Pack
        # Triggers on "風險應對", "risk response", "出貨應變", "delivery response"
        # Chain: delivery-risk -> sales-response-draft
        self.register_team({
            "name": "risk-response",
            "intent": "risk_response",
            "keywords": ["風險應對", "risk response", "出貨應變", "delivery response", "客戶應對"],
            "exact_keywords": ["風險應對", "risk response", "出貨應變"],
            "steps": [
                {"skill": "delivery-risk-analysis", "alias": "risk"},
                {"skill": "sales-response-draft", "alias": "sales"},
            ],
            "requires_order_id": True,
            "priority": 9,
        })

        # 3. Recovery Planning Pack
        # Triggers on explicit integrated recovery/planning requests
        # Chain: shortage recovery -> expedite -> capacity -> supplier follow-up
        self.register_team({
            "name": "recovery-planning",
            "intent": "recovery_planning",
            "keywords": ["恢復整合", "recovery coordination", "planning pack", "應變整合", "救援整合"],
            "exact_keywords": ["recovery planning", "恢復規劃包", "整合恢復方案", "recovery planning pack"],
            "steps": [
                {"skill": "material-shortage-recovery", "alias": "shortage"},
                {"skill": "expedite-options", "alias": "expedite"},
                {"skill": "capacity-rebalance", "alias": "capacity"},
                {"skill": "supplier-followup-draft", "alias": "supplier"},
            ],
            "requires_order_id": True,
            "priority": 11,
        })
        
    def register_team(self, team_config):
        """
        Register a new team workflow.
        Args:
            team_config (dict): {
                "name": str,
                "intent": str,
                "keywords": list,
                "exact_keywords": list,
                "steps": list of {"skill": str, "alias": str},
                "requires_order_id": bool,
                "priority": int,
            }
        """
        self.teams.append(team_config)
    
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
            policy = get_policy()
            routing = policy.get("routing", {})
            exact_w = routing.get("exact_keyword_weight", 5)
            kw_w = routing.get("keyword_weight", 2)
            multi_w = routing.get("multi_order_boost", 3)

            # Exact keyword matches (high weight)
            for kw in skill.get("exact_keywords", []):
                if kw.lower() in query_lower:
                    score += exact_w

            # Partial keyword matches (standard weight)
            for kw in skill.get("keywords", []):
                if kw.lower() in query_lower:
                    score += kw_w

            # Multi-order boost
            if len(order_ids) > 1 and skill.get("triggers_on_multi_order"):
                score += multi_w
                
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
    
    def match_team(self, query, order_ids):
        """
        Find the best matching team workflow using score-based routing.
        Follows the same scoring rules as match_skill but applies to teams.
        
        Returns:
            dict: Matched team config, or None if no match.
        """
        query_lower = query.lower()
        candidates = []
        
        for idx, team in enumerate(self.teams):
            score = 0
            policy = get_policy()
            routing = policy.get("routing", {})
            exact_w = routing.get("exact_keyword_weight", 5)
            kw_w = routing.get("keyword_weight", 2)

            # Exact keyword matches (high weight)
            for kw in team.get("exact_keywords", []):
                if kw.lower() in query_lower:
                    score += exact_w

            # Partial keyword matches (standard weight)
            for kw in team.get("keywords", []):
                if kw.lower() in query_lower:
                    score += kw_w
                    
            # Base priority ONLY applies if there's at least one keyword match
            if score > 0:
                score += team.get("priority", 0)
                
            candidates.append((team, score, idx))
            
        valid = [(t, sc, i) for t, sc, i in candidates if sc > 0]
        
        if not valid:
            return None
            
        valid.sort(key=lambda x: (-x[1], -x[0].get("priority", 0), x[2]))
        return valid[0][0]
    
    def execute_team(self, team_config, order_ids, data_dir, query=None):
        """
        Execute a team workflow by running steps in parallel.
        Results are assembled in the original step order for deterministic output.
        """
        import concurrent.futures
        
        steps = team_config.get("steps", [])
        # Pre-allocate results in step order
        results = {}
        trace = []
        success_count = 0
        failed_count = 0

        def _run_step(step, idx):
            """Execute a single team step. Returns (alias, result, trace_entry, success)."""
            skill_name = step["skill"]
            alias = step.get("alias", skill_name)
            
            # Find the skill in registry
            matched_skill = None
            for skill in self.skills:
                if skill["name"] == skill_name:
                    matched_skill = skill
                    break
            
            if matched_skill:
                try:
                    res = self.execute(matched_skill, order_ids, data_dir, query)
                    if "error" in res:
                        return alias, res, f"failed {skill_name}: {res['error']}", False
                    else:
                        return alias, res, f"executed {skill_name} via team workflow", True
                except Exception as e:
                    return alias, {"error": str(e)}, f"failed {skill_name}: {e}", False
            else:
                return alias, {"error": f"Skill {skill_name} not found"}, f"failed {skill_name}: Skill {skill_name} not found", False

        # Execute all steps in parallel using ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(steps)) as executor:
            # Submit all tasks, keeping track of original index for ordering
            future_to_idx = {executor.submit(_run_step, step, idx): idx for idx, step in enumerate(steps)}
            
            # Collect results as they complete
            completed = [None] * len(steps)
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    alias, result, trace_entry, success = future.result()
                    completed[idx] = (alias, result, trace_entry, success)
                except Exception as e:
                    # Fallback for unexpected executor errors
                    step = steps[idx]
                    alias = step.get("alias", step["skill"])
                    completed[idx] = (alias, {"error": str(e)}, f"failed {step['skill']}: {e}", False)

        # Assemble results in original step order
        for alias, result, trace_entry, success in completed:
            results[alias] = result
            trace.append(trace_entry)
            if success:
                success_count += 1
            else:
                failed_count += 1

        return {
            "team_name": team_config["name"],
            "intent": team_config["intent"],
            "results": results,
            "trace": trace,
            "order_id": order_ids[0] if order_ids else None,
            "summary": {
                "total_steps": len(steps),
                "success_count": success_count,
                "failed_count": failed_count,
                "partial_success": success_count > 0 and failed_count > 0,
                "parallel": True,
            },
        }
    
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
