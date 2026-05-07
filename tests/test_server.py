
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

    @patch("server.post_comment")
    @patch("server.route_query")
    def test_run_with_asana_integration(self, mock_route, mock_post):
        mock_route.return_value = {
            "status": "success",
            "intent": "delivery_risk_analysis",
            "order_ids": ["ORD-1001"],
            "data": {"order_id": "ORD-1001"}
        }
        
        url = f"http://localhost:{self.port}/run"
        payload = json.dumps({
            "query": "ORD-1001 出貨", 
            "data_dir": "mock_data",
            "asana_task": "12345"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        
        with urllib.request.urlopen(req):
            pass
            
        mock_post.assert_called_once()
        self.assertIn("12345", str(mock_post.call_args))

    def test_run_invalid_json(self):
        url = f"http://localhost:{self.port}/run"
        payload = b"not json"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
