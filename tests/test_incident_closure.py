"""Tests for incident_closure — operator-managed incident closure workflow."""

import json
import os
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from incident_closure import (
    get_closure,
    get_closure_summary,
    query_closures,
    reset_closures,
    upsert_closure,
)


class IncidentClosureModuleTest(unittest.TestCase):
    def setUp(self):
        reset_closures()

    def test_create_closure(self):
        result = upsert_closure("incident-1", "investigating", updated_by="alice")
        self.assertEqual(result["report_id"], "incident-1")
        self.assertEqual(result["status"], "investigating")
        self.assertEqual(result["updated_by"], "alice")

    def test_resolved_requires_note(self):
        result = upsert_closure("incident-1", "resolved")
        self.assertEqual(result["error"], "resolution_note_required")

    def test_invalid_transition_rejected(self):
        upsert_closure("incident-1", "open", updated_by="alice")
        upsert_closure("incident-1", "resolved", updated_by="alice", resolution_note="done")
        result = upsert_closure("incident-1", "investigating", updated_by="alice")
        self.assertEqual(result["error"], "invalid_transition")

    def test_update_links_and_history(self):
        upsert_closure("incident-1", "investigating", updated_by="alice")
        result = upsert_closure(
            "incident-1",
            "monitoring",
            updated_by="bob",
            linked_alert_ids=["alert-1"],
            linked_receipt_ids=["rcpt-1"],
        )
        self.assertEqual(result["status"], "monitoring")
        self.assertEqual(result["linked_alert_ids"], ["alert-1"])
        self.assertEqual(result["linked_receipt_ids"], ["rcpt-1"])
        self.assertEqual(len(result["history"]), 2)

    def test_query_and_summary(self):
        upsert_closure("incident-1", "investigating", updated_by="alice")
        upsert_closure("incident-2", "resolved", updated_by="bob", resolution_note="fixed")
        result = query_closures()
        self.assertEqual(result["total"], 2)
        self.assertIn("summary", result)
        self.assertEqual(result["summary"]["resolved_count"], 1)

    def test_get_closure(self):
        upsert_closure("incident-1", "monitoring", updated_by="alice")
        result = get_closure("incident-1")
        self.assertEqual(result["status"], "monitoring")


class IncidentClosureEndpointTest(unittest.TestCase):
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

    def setUp(self):
        reset_closures()

    def _get(self, path):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}")
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())

    def _post(self, path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else b""
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())

    def test_create_and_fetch_closure(self):
        status, created = self._post(
            "/incident/closures/incident-100",
            {"status": "investigating", "updated_by": "operator"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(created["status"], "investigating")

        status, fetched = self._get("/incident/closures/incident-100")
        self.assertEqual(status, 200)
        self.assertEqual(fetched["report_id"], "incident-100")

    def test_resolve_with_note(self):
        self._post("/incident/closures/incident-200", {"status": "investigating"})
        status, resolved = self._post(
            "/incident/closures/incident-200",
            {"status": "resolved", "resolution_note": "Recovered after provider fallback"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["resolution_note"], "Recovered after provider fallback")

    def test_invalid_transition_returns_409(self):
        self._post("/incident/closures/incident-300", {"status": "resolved", "resolution_note": "done"})
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/incident/closures/incident-300",
            data=json.dumps({"status": "investigating"}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 409)

    def test_list_closures(self):
        self._post("/incident/closures/incident-1", {"status": "investigating"})
        self._post("/incident/closures/incident-2", {"status": "resolved", "resolution_note": "fixed"})
        status, data = self._get("/incident/closures")
        self.assertEqual(status, 200)
        self.assertEqual(data["total"], 2)
        self.assertIn("closures", data)

    def test_reset_closures(self):
        self._post("/incident/closures/incident-1", {"status": "investigating"})
        status, body = self._post("/incident/closures/reset")
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])
        status, data = self._get("/incident/closures")
        self.assertEqual(data["total"], 0)


if __name__ == "__main__":
    unittest.main()
