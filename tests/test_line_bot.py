import base64
import hashlib
import hmac
import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer
from unittest.mock import patch

from integrations.line_bot import (
    format_line_response,
    format_line_approval_list,
    format_line_approval_item_detail,
    format_line_approval_action_result,
    handle_line_message,
    handle_line_approval_command,
    send_line_reply,
    verify_line_signature,
)
from server import AgentHandler


class LineSignatureTest(unittest.TestCase):
    @patch("integrations.line_bot.get_config_value")
    def test_verify_signature_success(self, mock_get_config):
        mock_get_config.return_value = "test-secret"
        body = b'{"events":[]}'
        digest = hmac.new(b"test-secret", body, hashlib.sha256).digest()
        signature = base64.b64encode(digest).decode("utf-8")
        self.assertTrue(verify_line_signature(body, signature))

    @patch("integrations.line_bot.get_config_value")
    def test_verify_signature_disabled_without_secret(self, mock_get_config):
        mock_get_config.return_value = ""
        self.assertTrue(verify_line_signature(b"{}", ""))


class LineReplyTest(unittest.TestCase):
    @patch("integrations.line_bot.get_config_value")
    @patch("integrations.line_bot.urllib.request.urlopen")
    def test_send_line_reply_success(self, mock_urlopen, mock_get_config):
        mock_get_config.return_value = "token"
        mock_resp = unittest.mock.Mock()
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__ = lambda s: mock_resp
        mock_urlopen.return_value.__exit__ = lambda s, *a: None
        self.assertTrue(send_line_reply("reply-token", "hello"))

    @patch("integrations.line_bot.get_config_value")
    def test_send_line_reply_missing_token(self, mock_get_config):
        mock_get_config.return_value = ""
        self.assertFalse(send_line_reply("reply-token", "hello"))


class LineMessageTest(unittest.TestCase):
    @patch("integrations.line_bot.get_config_value")
    def test_handle_line_message_blocks_unauthorized(self, mock_get_config):
        mock_get_config.return_value = ["u-1"]
        result = handle_line_message({"user_id": "u-2", "content": "查詢 ORD-1"})
        self.assertEqual(result["status"], "error")
        self.assertIn("未經授權", result["message"])

    @patch("integrations.line_bot.route_query")
    @patch("integrations.line_bot.log_run")
    @patch("integrations.line_bot.set_data_source")
    @patch("integrations.line_bot.create_provider")
    @patch("integrations.line_bot.get_provider_name")
    @patch("integrations.line_bot.get_config_value")
    def test_handle_line_message_uses_sheets_in_lightweight_mode(self, mock_get_config, mock_provider_name, mock_create_provider, mock_set_data_source, mock_log_run, mock_route):
        values = {
            "line.allowed_user_ids": [],
            "line.default_data_source": "",
            "runtime.workspace_mode": "lightweight",
            "runtime.default_data_dir": "mock_data",
            "live_provider.circuit_breaker.failure_threshold": 0,
            "live_provider.circuit_breaker.recovery_seconds": 60,
        }
        mock_get_config.side_effect = lambda k, d=None, raw=False: values.get(k, d)
        mock_provider_name.return_value = "google_sheets"
        mock_create_provider.return_value = object()
        mock_route.return_value = {"status": "success", "skill": "test", "intent": "test_intent", "data": {"decision": "ok"}}

        result = handle_line_message({"user_id": "u-1", "content": "ORD-1001"})

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data_source"], "sheets")
        self.assertIn("資料來源：google_sheets", result["message"])
        self.assertEqual(mock_create_provider.call_args[0][0], "sheets")
        mock_set_data_source.assert_called_once()
        mock_route.assert_called_once()
        mock_log_run.assert_called_once()

    @patch("integrations.line_bot.route_query")
    @patch("integrations.line_bot.log_run")
    @patch("integrations.line_bot.set_data_source")
    @patch("integrations.line_bot.create_provider")
    @patch("integrations.line_bot.get_provider_name")
    @patch("integrations.line_bot.get_config_value")
    def test_handle_line_message_respects_explicit_line_data_source(self, mock_get_config, mock_provider_name, mock_create_provider, mock_set_data_source, mock_log_run, mock_route):
        values = {
            "line.allowed_user_ids": [],
            "line.default_data_source": "local",
            "runtime.workspace_mode": "lightweight",
            "runtime.default_data_dir": "mock_data",
            "live_provider.circuit_breaker.failure_threshold": 0,
            "live_provider.circuit_breaker.recovery_seconds": 60,
        }
        mock_get_config.side_effect = lambda k, d=None, raw=False: values.get(k, d)
        mock_provider_name.return_value = "local"
        mock_create_provider.return_value = object()
        mock_route.return_value = {"status": "success", "skill": "test", "intent": "test_intent", "data": {"decision": "ok"}}

        result = handle_line_message({"user_id": "u-1", "content": "ORD-1001"})
        self.assertEqual(result["data_source"], "local")
        self.assertIn("資料來源：local", result["message"])
        self.assertEqual(mock_create_provider.call_args[0][0], "local")
        mock_log_run.assert_called_once()

    def test_format_line_response_includes_explainability(self):
        text = format_line_response("測試", {"status": "error", "error_type": "rollout_gated", "message": "blocked", "reason": "capability disabled", "next_action": "enable it", "decision_state": "rollout_gated"})
        self.assertIn("原因", text)
        self.assertIn("下一步", text)
        self.assertIn("功能尚未開放", text)


class LineApprovalCommandTest(unittest.TestCase):
    def test_format_approval_list_empty(self):
        self.assertIn("目前沒有待核可項目", format_line_approval_list([]))

    def test_format_approval_item_detail_shows_replay(self):
        item = {
            "id": "approval-3",
            "operation": "config:reload",
            "status": "pending",
            "created_at": "2026-05-17T10:00:00Z",
            "details": {"endpoint": "/config/reload"},
            "request_preview": {
                "method": "POST",
                "path": "/config/reload",
                "body_summary": "config_path=prod.json",
                "replay_ready": True,
            },
        }
        output = format_line_approval_item_detail(item)
        self.assertIn("可重試：是", output)
        self.assertIn("操作提示", output)

    def test_format_approval_action_result_approved(self):
        item = {"request_preview": {"replay_ready": True, "method": "POST", "path": "/config/reload"}}
        result = {"id": "approval-3", "operation": "config:reload"}
        output = format_line_approval_action_result("approved", result, item=item)
        self.assertIn("支援重試：是", output)
        self.assertIn("不會自動執行", output)

    @patch("integrations.line_bot.get_config_value")
    def test_handle_line_approval_command_blocks_unauthorized(self, mock_get_config):
        mock_get_config.return_value = ["u-1"]
        result = handle_line_approval_command({"user_id": "u-2", "content": "approval list"})
        self.assertEqual(result["status"], "error")
        self.assertIn("未經授權", result["message"])

    @patch("integrations.line_bot.get_config_value")
    @patch("integrations.line_bot.list_pending")
    def test_handle_line_approval_command_lists_pending(self, mock_list, mock_get_config):
        mock_get_config.return_value = []
        mock_list.return_value = [{"id": "approval-1", "operation": "config:reload", "status": "pending", "risk_level": "medium", "created_at": "2026-05-17T10:00:00Z"}]
        result = handle_line_approval_command({"user_id": "u-1", "content": "approval list"})
        self.assertEqual(result["status"], "success")
        self.assertIn("approval-1", result["message"])

    @patch("integrations.line_bot.get_config_value")
    @patch("integrations.line_bot.get_item")
    @patch("integrations.line_bot.serialize_item_for_api")
    def test_handle_line_approval_command_detail(self, mock_serialize, mock_get_item, mock_get_config):
        mock_get_config.return_value = []
        mock_get_item.return_value = {"id": "approval-2"}
        mock_serialize.return_value = {"id": "approval-2", "operation": "policy:reload", "status": "pending", "created_at": "2026-05-17T10:00:00Z"}
        result = handle_line_approval_command({"user_id": "u-1", "content": "approval approval-2"})
        self.assertEqual(result["status"], "success")
        self.assertIn("approval-2", result["message"])

    @patch("integrations.line_bot.get_config_value")
    @patch("integrations.line_bot.approve_item")
    @patch("integrations.line_bot.get_item")
    @patch("integrations.line_bot.serialize_item_for_api")
    def test_handle_line_approval_command_approve(self, mock_serialize, mock_get_item, mock_approve, mock_get_config):
        mock_get_config.return_value = []
        mock_get_item.return_value = {"id": "approval-3"}
        mock_serialize.return_value = {"id": "approval-3", "request_preview": {"replay_ready": True}}
        mock_approve.return_value = {"id": "approval-3", "operation": "config:reload"}
        result = handle_line_approval_command({"user_id": "u-1", "content": "approve approval-3"})
        self.assertEqual(result["status"], "success")
        self.assertIn("已核可", result["message"])

    @patch("integrations.line_bot.get_config_value")
    @patch("integrations.line_bot.reject_item")
    def test_handle_line_approval_command_reject(self, mock_reject, mock_get_config):
        mock_get_config.return_value = []
        mock_reject.return_value = {"id": "approval-4", "operation": "policy:reload", "rejection_reason": "不需要"}
        result = handle_line_approval_command({"user_id": "u-1", "content": "reject approval-4 不需要"})
        self.assertEqual(result["status"], "success")
        self.assertIn("已退回", result["message"])


class LineWebhookServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("localhost", 0), AgentHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=1)

    @patch("server.send_line_reply")
    @patch("server.handle_line_message")
    @patch("server.verify_line_signature")
    def test_line_webhook_processes_text_event(self, mock_verify, mock_handle, mock_reply):
        mock_verify.return_value = True
        mock_handle.return_value = {"status": "success", "message": "ok"}
        mock_reply.return_value = True
        url = f"http://localhost:{self.port}/webhook/line"
        payload = {
            "events": [{
                "type": "message",
                "replyToken": "reply-1",
                "source": {"userId": "u-1"},
                "message": {"type": "text", "text": "ORD-1001"}
            }]
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "X-Line-Signature": "sig"}, method="POST")
        with urllib.request.urlopen(req) as response:
            body = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(body["processed"], 1)
            self.assertEqual(body["replies_sent"], 1)

    @patch("server.send_line_reply")
    @patch("server.handle_line_approval_command")
    @patch("server.verify_line_signature")
    def test_line_webhook_routes_approval_commands(self, mock_verify, mock_handle_approval, mock_reply):
        mock_verify.return_value = True
        mock_handle_approval.return_value = {"status": "success", "message": "approval-ok"}
        mock_reply.return_value = True
        url = f"http://localhost:{self.port}/webhook/line"
        payload = {
            "events": [{
                "type": "message",
                "replyToken": "reply-1",
                "source": {"userId": "u-1"},
                "message": {"type": "text", "text": "approval list"}
            }]
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "X-Line-Signature": "sig"}, method="POST")
        with urllib.request.urlopen(req) as response:
            body = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(body["processed"], 1)
            self.assertEqual(body["replies_sent"], 1)
        mock_handle_approval.assert_called_once()

    @patch("server.verify_line_signature")
    def test_line_webhook_rejects_invalid_signature(self, mock_verify):
        mock_verify.return_value = False
        url = f"http://localhost:{self.port}/webhook/line"
        data = json.dumps({"events": []}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "X-Line-Signature": "bad"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 401)

    def test_history_accepts_line_channel(self):
        url = f"http://localhost:{self.port}/history?channel=line"
        with urllib.request.urlopen(url) as response:
            body = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(body["filters"]["channel"], "line")
