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
    handle_line_message,
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
    @patch("integrations.line_bot.set_data_source")
    @patch("integrations.line_bot.create_provider")
    @patch("integrations.line_bot.get_provider_name")
    @patch("integrations.line_bot.get_config_value")
    def test_handle_line_message_uses_sheets_in_lightweight_mode(self, mock_get_config, mock_provider_name, mock_create_provider, mock_set_data_source, mock_route):
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

    @patch("integrations.line_bot.route_query")
    @patch("integrations.line_bot.set_data_source")
    @patch("integrations.line_bot.create_provider")
    @patch("integrations.line_bot.get_provider_name")
    @patch("integrations.line_bot.get_config_value")
    def test_handle_line_message_respects_explicit_line_data_source(self, mock_get_config, mock_provider_name, mock_create_provider, mock_set_data_source, mock_route):
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

    def test_format_line_response_includes_explainability(self):
        text = format_line_response("測試", {"status": "error", "error_type": "rollout_gated", "message": "blocked", "reason": "capability disabled", "next_action": "enable it", "decision_state": "rollout_gated"})
        self.assertIn("原因", text)
        self.assertIn("下一步", text)
        self.assertIn("功能尚未開放", text)


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
