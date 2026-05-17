"""LINE integration: webhook verification, lightweight Sheets-backed query handling, and reply delivery.

This module provides a minimal direct LINE adapter for:
1. Verifying incoming webhook signatures when a channel secret is configured.
2. Routing text messages as safe read-only queries through the existing skills pipeline.
3. Defaulting lightweight mode traffic to the Google Sheets provider.
4. Replying with explainability-friendly LINE text messages.
5. Logging all interactions to the existing audit chain with channel='line'.
"""

import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request

from audit_chain import append_audit_entry
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
