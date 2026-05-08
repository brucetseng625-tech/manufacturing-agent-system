
import json
import os
import unittest
import threading
import time
import urllib.request
import urllib.error
from unittest.mock import patch, MagicMock
from http.server import HTTPServer

from server import AgentHandler, run_server

# Use a random port to avoid conflicts
PORT = 0 

class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("localhost", 0), AgentHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()
        time.sleep(0.5) # Wait for server to start

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()

    def test_health_check(self):
        url = f"http://localhost:{self.port}/health"
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(data["status"], "ok")

    @patch("server.route_query")
    def test_run_success(self, mock_route):
        mock_route.return_value = {
            "status": "success",
            "intent": "delivery_risk_analysis",
            "order_ids": ["ORD-1001"],
            "data": {"order_id": "ORD-1001", "decision": "can_ship"}
        }

        url = f"http://localhost:{self.port}/run"
        payload = json.dumps({"query": "ORD-1001 出貨", "data_dir": "mock_data"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["intent"], "delivery_risk_analysis")
            self.assertEqual(data["data"]["order_id"], "ORD-1001")
            # New fields check
            self.assertIsNone(data.get("asana_task"))
            self.assertIsNone(data.get("asana_posted"))

    @patch("server.route_query")
    def test_run_validation_error(self, mock_route):
        mock_route.return_value = {
            "status": "error",
            "type": "validation_failed",
            "details": ["Missing field"],
            "order_ids": ["ORD-BAD"]
        }

        url = f"http://localhost:{self.port}/run"
        payload = json.dumps({"query": "ORD-BAD 出貨", "data_dir": "mock_data"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            data = json.loads(e.read())
            self.assertEqual(e.code, 400)
            self.assertEqual(data["status"], "error")
            self.assertIn("Missing field", data["error"])
            self.assertIsNone(data.get("asana_posted"))

    @patch("server.post_comment")
    @patch("server.route_query")
    def test_run_asana_success_posted(self, mock_route, mock_post):
        """Success + Asana posted"""
        mock_route.return_value = {
            "status": "success",
            "intent": "delivery_risk_analysis",
            "order_ids": ["ORD-1001"],
            "data": {"order_id": "ORD-1001"}
        }
        mock_post.return_value = True
        
        url = f"http://localhost:{self.port}/run"
        payload = json.dumps({
            "query": "ORD-1001 出貨", 
            "data_dir": "mock_data",
            "asana_task": "12345"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read())
            self.assertEqual(data["asana_task"], "12345")
            self.assertTrue(data["asana_posted"])
            
        mock_post.assert_called_once()

    @patch("server.post_comment")
    @patch("server.route_query")
    def test_run_asana_success_failed(self, mock_route, mock_post):
        """Success + Asana failed (should return asana_posted=False but status=success)"""
        mock_route.return_value = {
            "status": "success",
            "intent": "delivery_risk_analysis",
            "order_ids": ["ORD-1001"],
            "data": {"order_id": "ORD-1001"}
        }
        mock_post.side_effect = Exception("API Error")
        
        url = f"http://localhost:{self.port}/run"
        payload = json.dumps({
            "query": "ORD-1001 出貨", 
            "data_dir": "mock_data",
            "asana_task": "12345"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["asana_task"], "12345")
            self.assertFalse(data["asana_posted"])

    @patch("server.post_comment")
    @patch("server.route_query")
    def test_run_asana_validation_error_posted(self, mock_route, mock_post):
        """Validation Error + Asana posted"""
        mock_route.return_value = {
            "status": "error",
            "type": "validation_failed",
            "details": ["Missing field"],
            "order_ids": ["ORD-BAD"]
        }
        mock_post.return_value = True

        url = f"http://localhost:{self.port}/run"
        payload = json.dumps({
            "query": "ORD-BAD 出貨", 
            "data_dir": "mock_data",
            "asana_task": "12345"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            data = json.loads(e.read())
            self.assertEqual(e.code, 400)
            self.assertEqual(data["asana_task"], "12345")
            self.assertTrue(data["asana_posted"])
            
        mock_post.assert_called_once()

    def test_run_invalid_json(self):
        url = f"http://localhost:{self.port}/run"
        payload = b"not json"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_run_missing_query(self):
        """POST /run without query field returns 400."""
        url = f"http://localhost:{self.port}/run"
        payload = json.dumps({}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_run_not_found(self):
        """POST to unknown path returns 404."""
        url = f"http://localhost:{self.port}/notfound"
        payload = b"{}"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)

    def test_get_not_found(self):
        """GET to unknown path returns 404."""
        url = f"http://localhost:{self.port}/notfound"
        try:
            urllib.request.urlopen(url)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)

    def test_get_skills(self):
        """GET /skills returns available skills and teams."""
        url = f"http://localhost:{self.port}/skills"
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertIn("total", data)
            self.assertIn("items", data)
            self.assertGreater(data["total"], 0)
            # Check at least one skill
            names = [item["name"] for item in data["items"]]
            self.assertIn("delivery-risk-analysis", names)
            # Check at least one team
            self.assertTrue(any("team:" in n for n in names))
            self.assertIn("team:recovery-planning", names)

    def test_get_skills_item_structure(self):
        """Each skill/team item has expected fields."""
        url = f"http://localhost:{self.port}/skills"
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read())
            # Check a skill item
            skill_item = next((i for i in data["items"] if i["type"] == "skill"), None)
            self.assertIsNotNone(skill_item)
            for key in ("name", "intent", "type", "requires_order_id", "keywords", "exact_keywords", "priority"):
                self.assertIn(key, skill_item)

            # Check a team item
            team_item = next((i for i in data["items"] if i["type"] == "team"), None)
            self.assertIsNotNone(team_item)
            self.assertIn("steps", team_item)
            self.assertTrue(isinstance(team_item["steps"], list))

    def test_get_schema(self):
        """GET /schema returns schema metadata."""
        url = f"http://localhost:{self.port}/schema"
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertIn("version", data)
            self.assertIn("top_level_shared_fields", data)
            self.assertIn("details_usage", data)
            self.assertIn("team_workflow_structure", data)
            # Verify key shared fields exist
            fields = data["top_level_shared_fields"]
            for key in ("skill", "decision", "confidence", "blockers", "details", "trace"):
                self.assertIn(key, fields)

    def test_get_history_default(self):
        """GET /history without params returns up to 10 runs."""
        url = f"http://localhost:{self.port}/history"
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertIn("total", data)
            self.assertIn("runs", data)
            self.assertIn("filters", data)
            self.assertEqual(data["filters"]["last"], 10)

    def test_get_history_invalid_last(self):
        """GET /history with invalid last parameter returns 400."""
        url = f"http://localhost:{self.port}/history?last=abc"
        try:
            urllib.request.urlopen(url)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
            data = json.loads(e.read())
            self.assertIn("message", data)
            self.assertEqual(data["error_type"], "invalid_parameter")

    def test_get_history_negative_last(self):
        """GET /history with negative last returns 400."""
        url = f"http://localhost:{self.port}/history?last=-1"
        try:
            urllib.request.urlopen(url)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_get_history_invalid_status(self):
        """GET /history with invalid status returns 400."""
        url = f"http://localhost:{self.port}/history?status=invalid"
        try:
            urllib.request.urlopen(url)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
            data = json.loads(e.read())
            self.assertIn("message", data)
            self.assertEqual(data["error_type"], "invalid_parameter")

    def test_get_history_invalid_channel(self):
        """GET /history with invalid channel returns 400."""
        url = f"http://localhost:{self.port}/history?channel=invalid"
        try:
            urllib.request.urlopen(url)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_get_history_valid_filters(self):
        """GET /history with valid filters returns 200."""
        url = f"http://localhost:{self.port}/history?last=5&status=success&channel=cli"
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(data["filters"]["last"], 5)
            self.assertEqual(data["filters"]["status"], "success")
            self.assertEqual(data["filters"]["channel"], "cli")

    # --- Failure-path tests ---

    def test_get_not_found_error_shape(self):
        """GET 404 returns consistent error shape."""
        url = f"http://localhost:{self.port}/notfound"
        try:
            urllib.request.urlopen(url)
        except urllib.error.HTTPError as e:
            data = json.loads(e.read())
            self.assertEqual(e.code, 404)
            self.assertEqual(data["status"], "error")
            self.assertEqual(data["error_type"], "not_found")
            self.assertIn("message", data)

    def test_run_error_response_shape(self):
        """POST /run error returns consistent error shape with error_type."""
        url = f"http://localhost:{self.port}/run"
        payload = json.dumps({"query": "no match at all"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            data = json.loads(e.read())
            self.assertIn("status", data)
            self.assertEqual(data["status"], "error")
            self.assertIn("error_type", data)
            self.assertIn("error", data)  # backward compat

    def test_run_skill_error_returns_500(self):
        """Skill errors return 500, not 400."""
        url = f"http://localhost:{self.port}/run"
        payload = json.dumps({"query": "ORD-9999 出貨"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            # skill_error for non-existent order should be 500
            self.assertEqual(e.code, 500)
            data = json.loads(e.read())
            self.assertIn("error_type", data)

    def test_run_missing_order_id_returns_400(self):
        """missing_order_id returns 400."""
        url = f"http://localhost:{self.port}/run"
        payload = json.dumps({"query": "準時出貨"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
            data = json.loads(e.read())
            self.assertEqual(data["error_type"], "missing_order_id")

    def test_run_unknown_intent_returns_400(self):
        """unknown_intent returns 400."""
        url = f"http://localhost:{self.port}/run"
        payload = json.dumps({"query": "今天天氣如何"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
            data = json.loads(e.read())
            self.assertEqual(data["error_type"], "unknown_intent")

    def test_run_validation_failed_returns_400(self):
        """validation_failed returns 400."""
        # Create temp dir with bad data to trigger validation error
        import tempfile
        with tempfile.TemporaryDirectory() as bad_dir:
            with open(os.path.join(bad_dir, "orders.csv"), "w") as f:
                f.write("order_id\nORD-BAD\n")
            url = f"http://localhost:{self.port}/run"
            payload = json.dumps({"query": "ORD-BAD 出貨", "data_dir": bad_dir}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            try:
                urllib.request.urlopen(req)
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 400)
                data = json.loads(e.read())
                self.assertEqual(data["error_type"], "validation_failed")

    def test_history_error_response_shape(self):
        """GET /history errors return consistent shape with error_type."""
        url = f"http://localhost:{self.port}/history?last=abc"
        try:
            urllib.request.urlopen(url)
        except urllib.error.HTTPError as e:
            data = json.loads(e.read())
            self.assertEqual(e.code, 400)
            self.assertEqual(data["status"], "error")
            self.assertEqual(data["error_type"], "invalid_parameter")
            self.assertIn("message", data)

    def test_post_not_found_error_shape(self):
        """POST 404 returns consistent error shape."""
        url = f"http://localhost:{self.port}/notfound"
        payload = b"{}"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            data = json.loads(e.read())
            self.assertEqual(e.code, 404)
            self.assertEqual(data["error_type"], "not_found")

    def test_dashboard_served_at_root(self):
        """GET / serves the dashboard HTML."""
        url = f"http://localhost:{self.port}/"
        with urllib.request.urlopen(url) as response:
            self.assertEqual(response.status, 200)
            content_type = response.headers.get("Content-Type", "")
            self.assertIn("text/html", content_type)
            html = response.read().decode("utf-8")
            self.assertIn("Manufacturing Agent Dashboard", html)

    def test_dashboard_served_at_dashboard_path(self):
        """GET /dashboard serves the dashboard HTML."""
        url = f"http://localhost:{self.port}/dashboard"
        with urllib.request.urlopen(url) as response:
            self.assertEqual(response.status, 200)
            html = response.read().decode("utf-8")
            self.assertIn("Skills & Teams", html)

    def test_static_file_not_found(self):
        """GET /static/nonexistent returns 404."""
        url = f"http://localhost:{self.port}/static/nonexistent.css"
        try:
            urllib.request.urlopen(url)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)
