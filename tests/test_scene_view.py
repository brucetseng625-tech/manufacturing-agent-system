"""Tests for P16-1 Read-Only Agent Team Scene View."""

import json
import os
import unittest


class SceneViewHTMLTest(unittest.TestCase):
    """Tests that dashboard HTML contains scene view elements."""

    def setUp(self):
        dashboard_path = os.path.join(
            os.path.dirname(__file__), "..", "static", "dashboard.html"
        )
        with open(dashboard_path, "r", encoding="utf-8") as f:
            self.html = f.read()

    def test_contains_scene_nav_item(self):
        """Dashboard must contain 場景視圖 nav item."""
        self.assertIn("場景視圖", self.html)
        self.assertIn('data-view="scene"', self.html)

    def test_contains_scene_view_section(self):
        """Dashboard must contain view-scene section."""
        self.assertIn('id="view-scene"', self.html)
        self.assertIn("scene-container", self.html)

    def test_contains_scene_floor(self):
        """Dashboard must have scene-floor grid overlay."""
        self.assertIn("scene-floor", self.html)

    def test_contains_scene_content_div(self):
        """Dashboard must have scene-content div for dynamic rendering."""
        self.assertIn('id="scene-content"', self.html)

    def test_contains_scene_inspector_div(self):
        """Dashboard must have scene-inspector div for detail panel."""
        self.assertIn('id="scene-inspector"', self.html)

    def test_contains_scene_workspace_dual_pane(self):
        """Scene view must provide dual-pane workspace shell."""
        self.assertIn("scene-workspace", self.html)
        self.assertIn("scene-sidepanel", self.html)
        self.assertIn("scene-workstage", self.html)

    def test_contains_scene_thread_and_context_panel(self):
        """Scene workspace must include thread and node context surfaces."""
        self.assertIn('id="scene-thread"', self.html)
        self.assertIn('id="scene-context-panel"', self.html)
        self.assertIn('id="scene-workspace-status"', self.html)
        self.assertIn("協作工作台", self.html)

    def test_contains_agent_catalog(self):
        """Scene view must define AGENT_CATALOG with 10 agents."""
        self.assertIn("AGENT_CATALOG", self.html)
        # Check key agents are present
        self.assertIn("製造主控", self.html)
        self.assertIn("交期分析", self.html)
        self.assertIn("排程檢查", self.html)
        self.assertIn("報價比較", self.html)
        self.assertIn("客戶回覆", self.html)

    def test_contains_zone_config(self):
        """Scene view must define ZONE_CONFIG with 5 zones."""
        self.assertIn("ZONE_CONFIG", self.html)
        self.assertIn("主控區", self.html)
        self.assertIn("風險評估區", self.html)
        self.assertIn("生產計畫區", self.html)

    def test_contains_render_scene_function(self):
        """Dashboard must have renderScene JavaScript function."""
        self.assertIn("async function renderScene()", self.html)

    def test_contains_show_agent_detail_function(self):
        """Dashboard must have showAgentDetail function for click inspection."""
        self.assertIn("function showAgentDetail(agentId)", self.html)

    def test_contains_scene_workspace_query_functions(self):
        """Scene workspace must support local query execution and focus handoff."""
        self.assertIn("executeSceneWorkspaceQuery", self.html)
        self.assertIn("renderSceneWorkspaceThread", self.html)
        self.assertIn("renderSceneWorkspaceStatus", self.html)
        self.assertIn("focusSceneAgentFromResponse", self.html)

    def test_contains_agent_node_css(self):
        """Dashboard must contain agent-node CSS styles."""
        self.assertIn(".agent-node", self.html)
        self.assertIn(".agent-row", self.html)
        self.assertIn(".zone-card", self.html)
        self.assertIn(".zone-card-header", self.html)

    def test_contains_status_badge_styles(self):
        """Dashboard must contain agent status badge styles."""
        self.assertIn("status-idle", self.html)
        self.assertIn("status-running", self.html)
        self.assertIn("status-blocked", self.html)
        self.assertIn("status-approval", self.html)

    def test_contains_pulse_animation(self):
        """Dashboard must contain pulse animation for active agents."""
        self.assertIn("pulse-running", self.html)
        self.assertIn("pulse-approval", self.html)
        self.assertIn("@keyframes pulse-green", self.html)

    def test_contains_status_labels_zh(self):
        """Dashboard must contain Traditional Chinese status labels."""
        self.assertIn("待機", self.html)
        self.assertIn("執行中", self.html)
        self.assertIn("待審批", self.html)

    def test_scene_fetches_approvals(self):
        """Scene view must fetch /approvals for pending state."""
        self.assertIn("'/approvals?status=pending", self.html)

    def test_scene_fetches_history(self):
        """Scene view must fetch /history for recent activity."""
        self.assertIn("'/history?last=50'", self.html)

    def test_scene_fetches_guardrails(self):
        """Scene view must fetch /guardrails for guard state."""
        self.assertIn("'/guardrails'", self.html)

    def test_scene_click_handler(self):
        """Agent nodes must have onclick handler for detail inspection."""
        self.assertIn("onclick=\"showAgentDetail(", self.html)

    def test_scene_inspector_detail_fields(self):
        """Inspector panel must display skill, status, approvals, and history."""
        self.assertIn("技能識別", self.html)
        self.assertIn("目前狀態", self.html)
        self.assertIn("待審批項目", self.html)
        self.assertIn("最近執行紀錄", self.html)

    def test_scene_is_read_only(self):
        """Scene view must not contain any mutation operations."""
        # Only check the scene-specific section (AGENT_CATALOG through showAgentDetail)
        scene_start = self.html.find("const AGENT_CATALOG")
        scene_end = self.html.find("// Timeline View")
        if scene_start == -1 or scene_end == -1:
            self.fail("Could not find scene view section")
        scene_section = self.html[scene_start:scene_end]
        # Scene should NOT have approve/reject/execute within its own code
        self.assertNotIn("doApprove", scene_section)
        self.assertNotIn("doReject", scene_section)
        self.assertNotIn("doSelectProvider", scene_section)

    def test_scene_nav_triggers_render(self):
        """Clicking scene nav must trigger renderScene()."""
        self.assertIn("if (view === 'scene') renderScene()", self.html)

    def test_scene_fetches_incident_report(self):
        """Scene view must fetch /incident/report for incident state."""
        self.assertIn("'/incident/report'", self.html)

    def test_scene_fetches_automation_receipts(self):
        """Scene view must fetch /automation/receipts for receipt signals."""
        self.assertIn("'/automation/receipts", self.html)

    def test_scene_fetches_timeline(self):
        """Scene view must fetch /timeline for event projection."""
        self.assertIn("'/timeline?last=30'", self.html)

    def test_scene_fetches_alerts(self):
        """Scene view must fetch /alerts for firing alerts."""
        self.assertIn("'/alerts?status=firing'", self.html)

    def test_scene_has_event_badges(self):
        """Scene must render event badges on agent nodes."""
        self.assertIn("agent-event-badges", self.html)
        self.assertIn("evt-approval", self.html)
        self.assertIn("evt-blocked", self.html)
        self.assertIn("evt-incident", self.html)
        self.assertIn("evt-receipt", self.html)
        self.assertIn("evt-alert", self.html)

    def test_scene_has_legend(self):
        """Scene must include a legend explaining status and event markers."""
        self.assertIn("scene-legend", self.html)
        self.assertIn("狀態與事件說明", self.html)

    def test_detail_panel_has_explainability(self):
        """Detail panel must show reason/next_action (P15-3 integration)."""
        self.assertIn("si-reason-block", self.html)
        self.assertIn("si-next-action", self.html)
        self.assertIn("目前無阻擋說明", self.html)

    def test_detail_panel_has_section_dividers(self):
        """Detail panel must use si-section for organized information blocks."""
        self.assertIn("si-section", self.html)
        self.assertIn("待審批項目", self.html)
        self.assertIn("最近執行紀錄", self.html)

    def test_detail_panel_shows_receipts(self):
        """Detail panel must display automation receipts."""
        self.assertIn("自動化執行紀錄", self.html)
        self.assertIn("relatedReceipts", self.html)

    def test_detail_panel_shows_timeline(self):
        """Detail panel must display related timeline events."""
        self.assertIn("相關時間軸事件", self.html)
        self.assertIn("relatedTimeline", self.html)

    def test_detail_panel_shows_incident(self):
        """Detail panel must display incident report summary when relevant."""
        self.assertIn("事故報告摘要", self.html)
        self.assertIn("incident_summary", self.html)

    def test_detail_panel_derives_reason(self):
        """Detail panel must derive reason from approval or errors."""
        self.assertIn("recentHistory.filter", self.html)
        self.assertIn("error_type", self.html)
