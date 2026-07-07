import json
import os
import unittest
import urllib.request
import urllib.error
import threading
import time
from http.server import HTTPServer

from server import AgentHandler
from knowledge_retriever import retrieve_knowledge
from config import get_config_value

class NewEnhancementsTest(unittest.TestCase):
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

    def test_rag_knowledge_retrieval(self):
        # Verify that retrieve_knowledge returns relevant segments for AGV sensors
        results = retrieve_knowledge("雷射感測器異常")
        self.assertTrue(len(results) > 0)
        # Verify that it finds manual_agv.txt
        sources = [r["source"] for r in results]
        self.assertIn("manual_agv.txt", sources)

    def test_get_config_current(self):
        url = f"http://localhost:{self.port}/config/current"
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertIn("llm", data)
            # Verify OpenAI key is masked if present
            if data["llm"].get("openai_api_key"):
                self.assertEqual(data["llm"]["openai_api_key"], "***REDACTED***")

    def test_post_config_update(self):
        url = f"http://localhost:{self.port}/config/update"
        payload = json.dumps({
            "llm": {
                "local_model": "qwen2.5:0.5b"
            }
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertTrue(data["success"])
            
        # Check that config gets loaded
        model = get_config_value("llm.local_model", raw=True)
        self.assertEqual(model, "qwen2.5:0.5b")

    def test_post_schedule_apply(self):
        url = f"http://localhost:{self.port}/ops/schedule/apply"
        req = urllib.request.Request(url, method="POST")
        
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertTrue(data["success"])
            self.assertIn("已成功將重排方案寫入資料庫", data["message"])
