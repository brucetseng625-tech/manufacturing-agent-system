"""Discord integration: notification sending, query-only message handling, and approval-assisted flow.

This module provides minimal Discord integration for:
1. Sending alert notifications to a Discord webhook.
2. Receiving Discord messages via a simple webhook receiver and routing
   them as read-only queries to the existing `/run` pipeline.
3. Approval-assisted flow: listing pending approvals, approving, and rejecting
   items from Discord while staying within existing security boundaries.

Security boundaries:
- Allowed Discord user IDs must be explicitly configured.
- Incoming queries are forced to dry_run=True (safe/read-only) by default.
- Approval actions require the Discord user ID to be in the allowlist.
- All interactions are logged to the existing audit chain with channel='discord'.
"""

import json
import os
import urllib.request
import urllib.error
from config import get_config_value
from audit_chain import append_audit_entry
from orchestrator import route_query, extract_order_ids
from approval_queue import list_pending, approve_item, reject_item, get_item, serialize_item_for_api


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


# ─── P17-3: Approval-Assisted Flow ──────────────────────────────────────────

def format_approval_list(items):
    """Format a list of approval items for Discord display.

    Args:
        items: List of approval item dicts from list_pending().

    Returns:
        Formatted string for Discord message content.
    """
    if not items:
        return "📋 **待審批項目**\n\n目前沒有待審批項目。"

    lines = ["📋 **待審批項目**\n"]
    for item in items[:10]:  # Max 10 for Discord readability
        op = item.get("operation", "unknown")
        item_id = item.get("id", "?")
        status = item.get("status", "unknown")
        created = item.get("created_at", "?")

        status_emoji = {"pending": "⏳", "approved": "✅", "rejected": "❌", "expired": "⏰"}.get(status, "❓")
        risk = item.get("risk_level", "unknown")
        risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(risk, "")

        details = item.get("details", {})
        endpoint = details.get("endpoint", "")
        preview = ""
        if endpoint:
            preview = f" → `{endpoint}`"

        lines.append(f"{status_emoji} `{item_id}` — **{op}**{risk_emoji}{preview}")
        lines.append(f"   建立時間: {created}")

    if len(items) > 10:
        lines.append(f"\n... 還有 {len(items) - 10} 筆項目未顯示")

    return "\n".join(lines)


def format_approval_item_detail(item):
    """Format a single approval item with full detail for Discord.

    Args:
        item: Approval item dict from get_item().

    Returns:
        Formatted string for Discord message content.
    """
    if item is None:
        return "❌ 找不到該審批項目。"

    item_id = item.get("id", "?")
    operation = item.get("operation", "unknown")
    status = item.get("status", "unknown")
    created_at = item.get("created_at", "?")
    source_ip = item.get("source_ip", "unknown")

    status_emoji = {"pending": "⏳", "approved": "✅", "rejected": "❌", "expired": "⏰"}.get(status, "❓")

    response = f"{status_emoji} **審批項目 `{item_id}`**\n\n"
    response += f"🏷️ **操作**: `{operation}`\n"
    response += f"📊 **狀態**: {status}\n"
    response += f"🕐 **建立時間**: {created_at}\n"
    response += f"🌐 **來源**: {source_ip}\n"

    details = item.get("details", {})
    if details.get("endpoint"):
        response += f"🔗 **端點**: `{details['endpoint']}`\n"
    if details.get("guardrail"):
        response += f"🛡️ **Guardrail**: `{details['guardrail']}`\n"

    original_request = item.get("original_request")
    if original_request:
        method = original_request.get("method", "?")
        path = original_request.get("path", "?")
        response += f"\n📝 **原始請求**: `{method} {path}`\n"

        body = original_request.get("body")
        if isinstance(body, dict):
            keys = ", ".join(sorted(body.keys()))[:80]
            response += f"   欄位: `{keys}`\n"

    if status == "approved":
        response += f"\n✅ **已審批** by: {item.get('approved_by', '?')}\n"
        if item.get("approved_at"):
            response += f"   時間: {item['approved_at']}\n"
    elif status == "rejected":
        response += f"\n❌ **已拒絕** by: {item.get('rejected_by', '?')}\n"
        if item.get("rejection_reason"):
            response += f"   原因: {item['rejection_reason']}\n"

    if status == "pending":
        response += f"\n💡 **操作提示**: 回覆 `approve {item_id}` 或 `reject {item_id} <原因>`\n"

    return response


def format_approval_action_result(action, result):
    """Format the result of an approval action for Discord.

    Args:
        action: "approved" or "rejected"
        result: Result dict from approve_item() or reject_item()

    Returns:
        Formatted string for Discord message content.
    """
    if "error" in result:
        error = result["error"]
        if error == "approval_not_found":
            return f"❌ 找不到審批項目 `{result.get('id', '?')}`。"
        elif error == "approval_already_resolved":
            status = result.get("status", "unknown")
            status_text = {"approved": "已審批", "rejected": "已拒絕", "expired": "已過期"}.get(status, status)
            return f"⚠️ 此審批項目已處理（{status_text}），無法重複操作。"
        else:
            return f"❌ 操作失敗: `{error}`"

    item_id = result.get("id", "?")
    operation = result.get("operation", "unknown")

    if action == "approved":
        response = f"✅ **已審批** `{item_id}`\n\n"
        response += f"🏷️ 操作: `{operation}`\n"
        response += f"👉 **下一步**: 原始請求可透過 approve-and-retry 重新執行"
    else:
        reason = result.get("rejection_reason", "")
        response = f"❌ **已拒絕** `{item_id}`\n\n"
        response += f"🏷️ 操作: `{operation}`\n"
        if reason:
            response += f"📝 原因: {reason}"

    return response


def _check_discord_authorization(author_id):
    """Check if a Discord user is authorized for approval actions.

    Args:
        author_id: Discord user ID string.

    Returns:
        True if authorized, False otherwise.
    """
    allowed_users = get_config_value("discord.allowed_user_ids", [])
    if isinstance(allowed_users, str):
        allowed_users = [u.strip() for u in allowed_users.split(",") if u.strip()]
    if allowed_users and author_id not in allowed_users:
        return False
    return True


def handle_discord_approval_command(message_payload):
    """Handle Discord approval commands: list, approve, reject.

    Supported commands:
    - `approval list` — List pending approval items
    - `approval list <status>` — List items by status (pending/approved/rejected)
    - `approval <id>` — Show detail for a specific approval item
    - `approve <id>` — Approve a pending item
    - `reject <id>` — Reject a pending item
    - `reject <id> <reason>` — Reject with a reason

    Args:
        message_payload: Dict containing 'content' and 'author_id'.

    Returns:
        Dict with 'status', 'message', and optionally 'audit_id'.
    """
    author_id = message_payload.get("author_id", "")
    content = message_payload.get("content", "").strip()

    if not _check_discord_authorization(author_id):
        return {
            "status": "error",
            "message": "❌ 未經授權的使用者。請聯繫管理員將您的 Discord ID 加入允許清單。",
            "audit_id": None,
        }

    parts = content.split()
    if not parts:
        return {"status": "error", "message": "⚠️ 請輸入有效的審批指令。", "audit_id": None}

    command = parts[0].lower()

    # ── approval list ──
    if command == "approval" and len(parts) >= 2 and parts[1].lower() == "list":
        status_filter = parts[2].lower() if len(parts) > 2 else "pending"
        items = list_pending(status_filter=status_filter if status_filter in ("pending", "approved", "rejected", "expired") else None)

        formatted = format_approval_list(items)

        audit_entry = append_audit_entry(
            "discord_approval_list",
            operator=f"discord:{author_id}",
            source_ip="discord_webhook",
            details={"command": content, "status_filter": status_filter, "item_count": len(items)},
            result="success",
        )

        return {"status": "success", "message": formatted, "audit_id": audit_entry.get("id") if audit_entry else None}

    # ── approval <id> (detail) ──
    if command == "approval" and len(parts) == 2:
        item_id = parts[1]
        item = get_item(item_id)
        if item:
            item = serialize_item_for_api(item)

        formatted = format_approval_item_detail(item)

        audit_entry = append_audit_entry(
            "discord_approval_detail",
            operator=f"discord:{author_id}",
            source_ip="discord_webhook",
            details={"command": content, "item_id": item_id, "found": item is not None},
            result="success" if item else "not_found",
        )

        return {"status": "success", "message": formatted, "audit_id": audit_entry.get("id") if audit_entry else None}

    # ── approve <id> ──
    if command == "approve" and len(parts) >= 2:
        item_id = parts[1]
        approved_by = f"discord:{author_id}"

        result = approve_item(item_id, approved_by=approved_by)

        formatted = format_approval_action_result("approved", result)

        audit_entry = append_audit_entry(
            "discord_approval_approved",
            operator=approved_by,
            source_ip="discord_webhook",
            details={"command": content, "item_id": item_id, "result": "error" if "error" in result else "success"},
            result="error" if "error" in result else "success",
        )

        return {"status": "success", "message": formatted, "audit_id": audit_entry.get("id") if audit_entry else None}

    # ── reject <id> [reason] ──
    if command == "reject" and len(parts) >= 2:
        item_id = parts[1]
        reason = " ".join(parts[2:]) if len(parts) > 2 else ""
        rejected_by = f"discord:{author_id}"

        result = reject_item(item_id, reason=reason, rejected_by=rejected_by)

        formatted = format_approval_action_result("rejected", result)

        audit_entry = append_audit_entry(
            "discord_approval_rejected",
            operator=rejected_by,
            source_ip="discord_webhook",
            details={"command": content, "item_id": item_id, "reason": reason, "result": "error" if "error" in result else "success"},
            result="error" if "error" in result else "success",
        )

        return {"status": "success", "message": formatted, "audit_id": audit_entry.get("id") if audit_entry else None}

    return {"status": "error", "message": "⚠️ 未知的審批指令。支援: `approval list`, `approval <id>`, `approve <id>`, `reject <id> [原因]`", "audit_id": None}
