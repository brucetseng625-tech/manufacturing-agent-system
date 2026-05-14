"""Discord integration: notification sending and query-only message handling.

This module provides minimal Discord integration for:
1. Sending alert notifications to a Discord webhook.
2. Receiving Discord messages via a simple webhook receiver and routing
   them as read-only queries to the existing `/run` pipeline.

Security boundaries:
- Allowed Discord user IDs must be explicitly configured.
- Incoming queries are forced to dry_run=True (safe/read-only) by default.
- All interactions are logged to the existing audit chain with channel='discord'.
"""

import json
import os
import urllib.request
import urllib.error
from config import get_config_value
from audit_chain import append_audit_entry
from orchestrator import route_query, extract_order_ids


def send_discord_notification(alert_type, title, description, fields=None):
    """Send a structured notification to a Discord webhook.

    Args:
        alert_type: Type of alert (e.g., 'system_unhealthy').
        title: Title of the embed.
        description: Description text.
        fields: Optional list of dicts with 'name' and 'value' keys for embed fields.

    Returns:
        True if sent successfully, False otherwise.
    """
    webhook_url = get_config_value("discord.webhook_url", "")
    if not webhook_url:
        return False

    color_map = {
        "system_unhealthy": 0xEF4444,  # Red
        "circuit_breaker_open": 0xF59E0B,  # Yellow
        "degradation_detected": 0xF59E0B,  # Yellow
        "incident_report": 0x8B5CF6,  # Purple
    }
    color = color_map.get(alert_type, 0x3B82F6)  # Default Blue

    payload = {
        "embeds": [
            {
                "title": f"🏭 {title}",
                "description": description,
                "color": color,
                "fields": fields or [],
                "footer": {"text": "Manufacturing Agent System"},
            }
        ]
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 204
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return False


def format_explainable_response(query_text, result):
    """Format a query result or error into a Discord-friendly text block.

    Prioritizes P15-3 explainability fields (reason, next_action) if present.

    Args:
        query_text: The original user query.
        result: The result dict from route_query or an error dict.

    Returns:
        Formatted string ready for Discord message content.
    """
    if result.get("status") == "error":
        error_type = result.get("error_type", "unknown")
        msg = result.get("message", result.get("error", "未知錯誤"))
        response = f"❌ **查詢失敗** (`{error_type}`)\n\n📝 {msg}"

        # Append explainability fields
        if result.get("reason"):
            response += f"\n\n🔍 **原因**: {result['reason']}"
        if result.get("next_action"):
            response += f"\n\n👉 **下一步**: {result['next_action']}"
        if result.get("decision_state"):
            state_map = {
                "blocked": "🚫 已被規則阻擋",
                "pending_approval": "⏳ 需要審批",
                "rollout_gated": "🔒 功能尚未開放",
            }
            state_label = state_map.get(result["decision_state"], result["decision_state"])
            response += f"\n\n📊 **狀態**: {state_label}"
        return response

    # Success path
    skill_name = result.get("skill", "N/A")
    intent = result.get("intent", "N/A")
    response = f"✅ **查詢完成**\n🤖 技能: `{skill_name}` | 意圖: `{intent}`\n\n"

    # Extract key details from data
    data = result.get("data", {})
    if isinstance(data, dict):
        # Try to summarize common fields
        if "decision" in data:
            response += f"💡 **決策**: `{data['decision']}`\n"
        if "order_id" in data:
            response += f"📦 **訂單**: `{data['order_id']}`\n"
        if data.get("details"):
            details = data["details"]
            if "risk_level" in details:
                response += f"⚠️ **風險等級**: `{details['risk_level']}`\n"
            if "expedite_option" in details:
                response += f"🚀 **加急方案**: `{details['expedite_option']}`\n"

    # Always include reason/next_action if the backend provided them
    if result.get("reason"):
        response += f"\n🔍 **原因**: {result['reason']}"
    if result.get("next_action"):
        response += f"\n👉 **下一步**: {result['next_action']}"

    if len(response) > 2000:
        response = response[:1990] + "..."
    return response


def handle_discord_message(message_payload):
    """Process an incoming Discord message payload as a query.

    Args:
        message_payload: Dict containing 'content' (query text) and 'author_id'.

    Returns:
        Dict with 'status', 'message', and optionally 'audit_id'.
    """
    allowed_users = get_config_value("discord.allowed_user_ids", [])
    if isinstance(allowed_users, str):
        allowed_users = [u.strip() for u in allowed_users.split(",") if u.strip()]

    author_id = message_payload.get("author_id", "")
    content = message_payload.get("content", "").strip()

    if author_id and allowed_users and author_id not in allowed_users:
        return {
            "status": "error",
            "message": "❌ 未經授權的使用者。請聯繫管理員將您的 Discord ID 加入允許清單。",
            "audit_id": None,
        }

    if not content:
        return {"status": "error", "message": "⚠️ 請輸入查詢內容。", "audit_id": None}

    # Security: Force dry_run=True for Discord queries (read-only)
    dry_run = True
    order_ids = extract_order_ids(content)

    try:
        result = route_query(content, order_ids, dry_run=dry_run)
    except Exception as e:
        result = {"status": "error", "error_type": "route_error", "message": str(e)}

    discord_message = format_explainable_response(content, result)

    audit_entry = append_audit_entry(
        "discord_query",
        operator=f"discord:{author_id}",
        source_ip="discord_webhook",
        details={"query": content, "order_ids": order_ids, "dry_run": dry_run, "result_status": result.get("status")},
        result=result.get("status", "failed"),
    )

    return {"status": "success", "message": discord_message, "audit_id": audit_entry.get("id") if audit_entry else None}
