"""LINE integration: webhook verification, lightweight Sheets-backed query handling, and approval-assisted replies.

This module provides a minimal direct LINE adapter for:
1. Verifying incoming webhook signatures when a channel secret is configured.
2. Routing text messages as safe read-only queries through the existing skills pipeline.
3. Defaulting lightweight mode traffic to the Google Sheets provider.
4. Replying with explainability-friendly LINE text messages.
5. Supporting minimal approval-assisted commands for pending queue management.
6. Logging all interactions to the existing audit chain with channel='line'.
"""

import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request

from audit_chain import append_audit_entry
from approval_queue import list_pending, get_item, approve_item, reject_item, serialize_item_for_api
from config import get_config_value, resolve_repo_path
from data_source import create_provider, get_provider_name, set_data_source
from orchestrator import extract_order_ids, route_query


def _normalize_allowed_users():
    allowed_users = get_config_value("line.allowed_user_ids", [])
    if isinstance(allowed_users, str):
        allowed_users = [item.strip() for item in allowed_users.split(",") if item.strip()]
    return allowed_users


def _resolve_line_data_source():
    explicit = get_config_value("line.default_data_source", "", raw=True)
    if explicit in ("local", "live", "auto", "sheets"):
        return explicit
    workspace_mode = get_config_value("runtime.workspace_mode", "erp")
    if workspace_mode == "lightweight":
        return "sheets"
    return get_config_value("runtime.default_data_source", "local")


def verify_line_signature(body_bytes, signature):
    """Verify LINE webhook signature when a channel secret is configured."""
    channel_secret = get_config_value("line.channel_secret", "")
    if not channel_secret:
        return True
    if not signature:
        return False
    digest = hmac.new(
        channel_secret.encode("utf-8"),
        body_bytes,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def _check_line_authorization(user_id):
    allowed_users = _normalize_allowed_users()
    if not allowed_users:
        return True
    return bool(user_id) and user_id in allowed_users


def format_line_response(query_text, result):
    """Format a query result or error for a LINE text reply."""
    if result.get("status") == "error":
        error_type = result.get("error_type", result.get("type", "unknown"))
        message = result.get("message", result.get("error", result.get("details", "未知錯誤")))
        if isinstance(message, list):
            message = "；".join(str(item) for item in message)
        lines = [f"❌ 查詢失敗（{error_type}）", str(message)]
        if result.get("reason"):
            lines.append(f"原因：{result['reason']}")
        if result.get("next_action"):
            lines.append(f"下一步：{result['next_action']}")
        if result.get("decision_state"):
            state_map = {
                "blocked": "已被規則阻擋",
                "pending_approval": "需要審批",
                "rollout_gated": "功能尚未開放",
            }
            lines.append(f"狀態：{state_map.get(result['decision_state'], result['decision_state'])}")
        return "\n".join(lines)[:5000]

    skill_name = result.get("skill", "N/A")
    intent = result.get("intent", "N/A")
    lines = ["✅ 查詢完成", f"技能：{skill_name} | 意圖：{intent}"]
    data = result.get("data", {})
    if isinstance(data, dict):
        if "order_id" in data:
            lines.append(f"訂單：{data['order_id']}")
        if "decision" in data:
            lines.append(f"決策：{data['decision']}")
        details = data.get("details", {})
        if isinstance(details, dict):
            if details.get("risk_level"):
                lines.append(f"風險等級：{details['risk_level']}")
            if details.get("expedite_option"):
                lines.append(f"加急方案：{details['expedite_option']}")
    if result.get("reason"):
        lines.append(f"原因：{result['reason']}")
    if result.get("next_action"):
        lines.append(f"下一步：{result['next_action']}")
    if result.get("data_source"):
        lines.append(f"資料來源：{result['data_source']}")
    return "\n".join(lines)[:5000]


def send_line_reply(reply_token, message_text):
    """Reply to a LINE message using the Messaging API."""
    channel_access_token = get_config_value("line.channel_access_token", "")
    if not channel_access_token or not reply_token or not message_text:
        return False

    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": message_text[:5000]}],
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.line.me/v2/bot/message/reply",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {channel_access_token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return False


def format_line_approval_list(items):
    if not items:
        return "📋 待核可項目\n目前沒有待核可項目。"
    lines = ["📋 待核可項目"]
    for item in items[:8]:
        item_id = item.get("id", "?")
        operation = item.get("operation", "unknown")
        status = item.get("status", "unknown")
        risk = item.get("risk_level", "unknown")
        created = item.get("created_at", "?")
        status_icon = {"pending": "⏳", "approved": "✅", "rejected": "❌", "expired": "⏰"}.get(status, "❔")
        risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴", "critical": "🚨"}.get(risk, "")
        lines.append(f"{status_icon} {item_id}｜{operation} {risk_icon}")
        lines.append(f"建立時間：{created}")
    if len(items) > 8:
        lines.append(f"... 還有 {len(items) - 8} 項未顯示")
    return "\n".join(lines)[:5000]


def format_line_approval_item_detail(item):
    if item is None:
        return "❌ 找不到該核可項目。"

    item_id = item.get("id", "?")
    operation = item.get("operation", "unknown")
    status = item.get("status", "unknown")
    created_at = item.get("created_at", "?")
    status_icon = {"pending": "⏳", "approved": "✅", "rejected": "❌", "expired": "⏰"}.get(status, "❔")

    lines = [
        f"{status_icon} 核可項目 {item_id}",
        f"操作：{operation}",
        f"狀態：{status}",
        f"建立時間：{created_at}",
    ]

    details = item.get("details", {})
    if details.get("endpoint"):
        lines.append(f"端點：{details['endpoint']}")

    preview = item.get("request_preview") or {}
    if preview:
        method = preview.get("method", "")
        path = preview.get("path", "")
        body_summary = preview.get("body_summary", "")
        replay_ready = preview.get("replay_ready", False)
        lines.append(f"原始請求：{method} {path}".strip())
        if body_summary:
            lines.append(f"內容摘要：{body_summary}")
        lines.append(f"可重試：{'是' if replay_ready else '否'}")

    retry_result = item.get("retry_result")
    if retry_result:
        success = retry_result.get("success")
        status_code = retry_result.get("status_code", "N/A")
        lines.append(f"重試結果：{'成功' if success else '失敗'}（HTTP {status_code}）")
    elif status == "approved" and preview.get("replay_ready"):
        lines.append("重試結果：尚未執行，需透過 approve-and-retry 觸發")

    if status == "pending":
        lines.append(f"操作提示：approve {item_id} 或 reject {item_id} 原因")

    return "\n".join(lines)[:5000]


def format_line_approval_action_result(action, result, item=None):
    if "error" in result:
        error = result["error"]
        if error == "approval_not_found":
            return f"❌ 找不到核可項目 {result.get('id', '?')}。"
        if error == "approval_already_resolved":
            status = result.get("status", "unknown")
            return f"⚠️ 此項目已處理（{status}），無法重複操作。"
        return f"❌ 操作失敗：{error}"

    item_id = result.get("id", "?")
    operation = result.get("operation", "unknown")
    if action == "approved":
        lines = [f"✅ 已核可 {item_id}", f"操作：{operation}"]
        preview = (item or {}).get("request_preview") or {}
        if preview.get("method") or preview.get("path"):
            lines.append(f"原始請求：{preview.get('method', '')} {preview.get('path', '')}".strip())
        if preview.get("replay_ready"):
            lines.append("支援重試：是（可透過 Dashboard 或 API approve-and-retry）")
            lines.append("下一步：核可已完成，但不會自動執行原始操作。")
        else:
            lines.append("支援重試：否（原始請求資訊不足）")
    else:
        lines = [f"❌ 已退回 {item_id}", f"操作：{operation}"]
        if result.get("rejection_reason"):
            lines.append(f"原因：{result['rejection_reason']}")
    return "\n".join(lines)[:5000]


def handle_line_approval_command(message_payload):
    user_id = message_payload.get("user_id", "")
    content = message_payload.get("content", "").strip()

    if not _check_line_authorization(user_id):
        return {
            "status": "error",
            "message": "❌ 未經授權的使用者。請聯繫管理員將您的 LINE User ID 加入允許清單。",
            "audit_id": None,
        }

    parts = content.split()
    if not parts:
        return {"status": "error", "message": "⚠️ 請輸入有效的核可指令。", "audit_id": None}

    command = parts[0].lower()
    operator = f"line:{user_id}"

    if command == "approval" and len(parts) >= 2 and parts[1].lower() == "list":
        status_filter = parts[2].lower() if len(parts) > 2 else "pending"
        valid = ("pending", "approved", "rejected", "expired")
        items = list_pending(status_filter=status_filter if status_filter in valid else None)
        message = format_line_approval_list(items)
        audit_entry = append_audit_entry(
            "line_approval_list",
            operator=operator,
            source_ip="line_webhook",
            details={"command": content, "status_filter": status_filter, "item_count": len(items)},
            result="success",
        )
        return {"status": "success", "message": message, "audit_id": audit_entry.get("id") if audit_entry else None}

    if command == "approval" and len(parts) == 2:
        item_id = parts[1]
        item = get_item(item_id)
        if item:
            item = serialize_item_for_api(item)
        message = format_line_approval_item_detail(item)
        audit_entry = append_audit_entry(
            "line_approval_detail",
            operator=operator,
            source_ip="line_webhook",
            details={"command": content, "item_id": item_id, "found": item is not None},
            result="success" if item else "not_found",
        )
        return {"status": "success", "message": message, "audit_id": audit_entry.get("id") if audit_entry else None}

    if command == "approve" and len(parts) >= 2:
        item_id = parts[1]
        item_before = get_item(item_id)
        if item_before:
            item_before = serialize_item_for_api(item_before)
        result = approve_item(item_id, approved_by=operator)
        message = format_line_approval_action_result("approved", result, item=item_before)
        audit_entry = append_audit_entry(
            "line_approval_approved",
            operator=operator,
            source_ip="line_webhook",
            details={"command": content, "item_id": item_id, "result": "error" if "error" in result else "success"},
            result="error" if "error" in result else "success",
        )
        return {"status": "success", "message": message, "audit_id": audit_entry.get("id") if audit_entry else None}

    if command == "reject" and len(parts) >= 2:
        item_id = parts[1]
        reason = " ".join(parts[2:]) if len(parts) > 2 else ""
        result = reject_item(item_id, reason=reason, rejected_by=operator)
        message = format_line_approval_action_result("rejected", result)
        audit_entry = append_audit_entry(
            "line_approval_rejected",
            operator=operator,
            source_ip="line_webhook",
            details={"command": content, "item_id": item_id, "reason": reason, "result": "error" if "error" in result else "success"},
            result="error" if "error" in result else "success",
        )
        return {"status": "success", "message": message, "audit_id": audit_entry.get("id") if audit_entry else None}

    return {
        "status": "error",
        "message": "⚠️ 未知的核可指令。支援：approval list、approval <id>、approve <id>、reject <id> [原因]",
        "audit_id": None,
    }


def handle_line_message(message_payload):
    """Route a LINE text message as a read-only query, defaulting to Sheets in lightweight mode."""
    user_id = message_payload.get("user_id", "")
    content = message_payload.get("content", "").strip()

    if not _check_line_authorization(user_id):
        return {
            "status": "error",
            "message": "❌ 未經授權的使用者。請聯繫管理員將您的 LINE User ID 加入允許清單。",
            "audit_id": None,
        }

    if not content:
        return {"status": "error", "message": "⚠️ 請輸入查詢內容。", "audit_id": None}

    data_source_mode = _resolve_line_data_source()
    order_ids = extract_order_ids(content)
    data_dir = resolve_repo_path(get_config_value("runtime.default_data_dir", "mock_data"))

    try:
        set_data_source(create_provider(
            data_source_mode,
            cb_threshold=get_config_value("live_provider.circuit_breaker.failure_threshold", 0, raw=True),
            cb_recovery=get_config_value("live_provider.circuit_breaker.recovery_seconds", 60, raw=True),
        ))
        result = route_query(content, data_dir)
    except Exception as exc:
        result = {"status": "error", "error_type": "route_error", "message": str(exc)}

    result.setdefault("data_source", get_provider_name())
    line_message = format_line_response(content, result)
    audit_entry = append_audit_entry(
        "line_query",
        operator=f"line:{user_id}",
        source_ip="line_webhook",
        details={
            "query": content,
            "order_ids": order_ids,
            "query_only": True,
            "data_source": data_source_mode,
            "result_status": result.get("status"),
        },
        result=result.get("status", "failed"),
    )
    return {
        "status": "success",
        "message": line_message,
        "audit_id": audit_entry.get("id") if audit_entry else None,
        "data_source": data_source_mode,
    }
