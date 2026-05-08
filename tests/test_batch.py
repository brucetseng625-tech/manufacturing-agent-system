
import os
import tempfile
import json
import unittest
import socket
import threading
import time

from orchestrator import batch_queries, route_query


class BatchQueriesTest(unittest.TestCase):
    """Tests for batch query processing."""

    def setUp(self):
        self.data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")

    def test_batch_queries_success(self):
        """Batch with valid queries should return success counts."""
        queries = [
            "ORD-1001 出貨風險分析",
            "ORD-1002 檢查排程衝突",
        ]
        result = batch_queries(queries, self.data_dir)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["success_count"], 2)
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(result["results"][0]["index"], 0)
        self.assertEqual(result["results"][1]["index"], 1)

    def test_batch_queries_mixed_results(self):
        """Batch with mixed success/error should count correctly."""
        queries = [
            "ORD-1001 出貨風險分析",
            "this is a completely unknown intent",
        ]
        result = batch_queries(queries, self.data_dir)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["success_count"], 1)
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(result["results"][0]["result"]["status"], "success")
        self.assertEqual(result["results"][1]["result"]["status"], "error")

    def test_batch_queries_empty_list(self):
        """Batch with empty list should return zero counts."""
        result = batch_queries([], self.data_dir)
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["success_count"], 0)
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(len(result["results"]), 0)

    def test_batch_queries_preserves_order(self):
        """Results should maintain the same order as input queries."""
        queries = [
            "ORD-1003 報價比較",
            "ORD-1001 出貨風險分析",
        ]
        result = batch_queries(queries, self.data_dir)
        self.assertIn("quote", result["results"][0]["result"].get("skill", ""))
        self.assertIn("delivery", result["results"][1]["result"].get("skill", ""))


class BatchEndpointTest(unittest.TestCase):
    """Tests for the POST /batch HTTP endpoint."""

    def setUp(self):
        self.data_dir = os.path.join(os.path.dirname(__file__), "..", "mock_data")

    def _find_free_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def test_batch_endpoint_returns_summary(self):
        """POST /batch should return batch summary and results."""
        from server import run_server
        import urllib.request

        port = self._find_free_port()

        def run_in_thread():
            os.environ["AGENT_LOG_DIR"] = tempfile.mkdtemp()
            run_server(port=port)

        server_thread = threading.Thread(target=run_in_thread, daemon=True)
        server_thread.start()
        time.sleep(0.3)

        try:
            url = f"http://localhost:{port}/batch"
            payload = json.dumps({
                "queries": ["ORD-1001 出貨風險分析", "ORD-1002 檢查排程衝突"],
                "data_dir": self.data_dir,
            }).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(resp.status, 200)
                self.assertIn("total", data)
                self.assertEqual(data["total"], 2)
                self.assertIn("success_count", data)
                self.assertIn("results", data)
                self.assertEqual(len(data["results"]), 2)
        finally:
            pass

    def test_batch_endpoint_missing_queries_returns_400(self):
        """POST /batch without queries list should return 400."""
        from server import run_server
        import urllib.request
        import urllib.error

        port = self._find_free_port()

        def run_in_thread():
            os.environ["AGENT_LOG_DIR"] = tempfile.mkdtemp()
            run_server(port=port)

        server_thread = threading.Thread(target=run_in_thread, daemon=True)
        server_thread.start()
        time.sleep(0.3)

        try:
            url = f"http://localhost:{port}/batch"
            payload = json.dumps({"data_dir": self.data_dir}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(req, timeout=5)
                self.fail("Expected HTTPError")
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 400)
        finally:
            pass
