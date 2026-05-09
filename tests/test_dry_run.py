
import json
import os
import threading
import time
import unittest
import urllib.request
from http.server import HTTPServer


class DryRunSingleQueryTest(unittest.TestCase):
    """Tests for POST /run with dry_run=true."""

    @classmethod
    def setUpClass(cls):
        from server import AgentHandler
        cls.server = HTTPServer(("127.0.0.1", 0), AgentHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=1)

    def _post(self, payload):
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/run",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())

    def test_dry_run_returns_dry_run_status(self):
        """Dry run should return status='dry_run' and dry_run=true."""
        result = self._post({
            "query": "ORD-1001 能不能準時出？",
            "dry_run": True,
        })
        self.assertEqual(result["status"], "dry_run")
        self.assertTrue(result["dry_run"])

    def test_dry_run_extracts_order_ids(self):
        """Dry run should extract order IDs from the query."""
        result = self._post({
            "query": "ORD-1001 能不能準時出？",
            "dry_run": True,
        })
        self.assertIn("ORD-1001", result["order_ids"])

    def test_dry_run_shows_routing_decision(self):
        """Dry run should show matched intent and skill/team."""
        result = self._post({
            "query": "ORD-1001 能不能準時出？",
            "dry_run": True,
        })
        self.assertIsNotNone(result["intent"])
        self.assertIsNotNone(result["matched"])
        self.assertIsInstance(result["steps"], list)

    def test_dry_run_has_no_side_effects(self):
        """Dry run response should indicate no side effects."""
        result = self._post({
            "query": "ORD-1001 能不能準時出？",
            "dry_run": True,
        })
        self.assertIn("no side effects", result["message"].lower())

    def test_dry_run_includes_data_source(self):
        """Dry run should include the active data source."""
        result = self._post({
            "query": "ORD-1001 能不能準時出？",
            "dry_run": True,
        })
        self.assertIn("data_source", result)

    def test_dry_run_has_run_id(self):
        """Dry run should generate a run_id."""
        result = self._post({
            "query": "ORD-1001 能不能準時出？",
            "dry_run": True,
        })
        self.assertIn("run_id", result)
        self.assertTrue(result["run_id"].startswith("dry-run-"))

    def test_dry_run_returns_200(self):
        """Dry run should always return HTTP 200."""
        data = json.dumps({"query": "ORD-1001 能不能準時出？", "dry_run": True}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/run",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)

    def test_non_dry_run_still_works(self):
        """Normal (non-dry) run should still work as before."""
        result = self._post({
            "query": "ORD-1001 能不能準時出？",
        })
        # Normal run should not have dry_run=True
        self.assertNotEqual(result.get("status"), "dry_run")
        self.assertFalse(result.get("dry_run", False))


class DryRunBatchTest(unittest.TestCase):
    """Tests for POST /batch with dry_run=true."""

    @classmethod
    def setUpClass(cls):
        from server import AgentHandler
        cls.server = HTTPServer(("127.0.0.1", 0), AgentHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=1)

    def _post_batch(self, payload):
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/batch",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())

    def test_dry_run_batch_returns_dry_run_status(self):
        """Batch dry run should return status='dry_run'."""
        result = self._post_batch({
            "queries": [
                "ORD-1001 能不能準時出？",
                "ORD-1002 的交期風險",
            ],
            "dry_run": True,
        })
        self.assertEqual(result["status"], "dry_run")
        self.assertTrue(result["dry_run"])

    def test_dry_run_batch_returns_results_for_each_query(self):
        """Batch dry run should return routing for each query."""
        result = self._post_batch({
            "queries": [
                "ORD-1001 能不能準時出？",
                "ORD-1002 的交期風險",
            ],
            "dry_run": True,
        })
        self.assertEqual(result["total"], 2)
        self.assertEqual(len(result["results"]), 2)

    def test_dry_run_batch_shows_routing_per_query(self):
        """Each result in batch dry run should show routing."""
        result = self._post_batch({
            "queries": ["ORD-1001 能不能準時出？"],
            "dry_run": True,
        })
        r = result["results"][0]
        self.assertIn("query", r)
        self.assertIn("order_ids", r)
        self.assertIn("intent", r)
        self.assertIn("matched", r)
        self.assertIn("steps", r)

    def test_dry_run_batch_no_side_effects(self):
        """Batch dry run should indicate no side effects."""
        result = self._post_batch({
            "queries": ["ORD-1001 能不能準時出？"],
            "dry_run": True,
        })
        self.assertIn("no side effects", result["message"].lower())

    def test_non_dry_run_batch_still_works(self):
        """Normal batch should still work."""
        result = self._post_batch({
            "queries": ["ORD-1001 能不能準時出？"],
        })
        self.assertNotEqual(result.get("status"), "dry_run")


if __name__ == "__main__":
    unittest.main()
