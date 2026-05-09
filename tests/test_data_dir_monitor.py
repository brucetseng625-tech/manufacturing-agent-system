
import os
import tempfile
import json
import csv
import time
import unittest
import socket
import threading

from data_dir_monitor import scan_data_dir, has_changed, get_data_dir_metadata


class ScanDataDirTest(unittest.TestCase):
    """Tests for scan_data_dir."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_empty_directory(self):
        """Scanning an empty directory should return zero files."""
        result = scan_data_dir(self.tmpdir)
        self.assertEqual(result["file_count"], 0)
        self.assertEqual(len(result["files"]), 0)
        self.assertIsNone(result["error"])

    def test_scans_json_files(self):
        """Should detect JSON files."""
        with open(os.path.join(self.tmpdir, "orders.json"), "w") as f:
            json.dump([{"id": 1}], f)
        result = scan_data_dir(self.tmpdir)
        self.assertEqual(result["file_count"], 1)
        self.assertEqual(result["files"][0]["name"], "orders.json")

    def test_scans_csv_files(self):
        """Should detect CSV files."""
        with open(os.path.join(self.tmpdir, "data.csv"), "w") as f:
            f.write("a,b\n1,2\n")
        result = scan_data_dir(self.tmpdir)
        self.assertEqual(result["file_count"], 1)

    def test_scans_both_json_and_csv(self):
        """Should detect both JSON and CSV files."""
        with open(os.path.join(self.tmpdir, "a.json"), "w") as f:
            json.dump([], f)
        with open(os.path.join(self.tmpdir, "b.csv"), "w") as f:
            f.write("x\n1\n")
        result = scan_data_dir(self.tmpdir)
        self.assertEqual(result["file_count"], 2)

    def test_nonexistent_directory_returns_error(self):
        """Should report error for non-existent directory."""
        result = scan_data_dir("/nonexistent/path")
        self.assertIsNotNone(result["error"])

    def test_files_sorted_by_name(self):
        """Files should be sorted alphabetically by name."""
        for name in ["c.json", "a.json", "b.csv"]:
            with open(os.path.join(self.tmpdir, name), "w") as f:
                f.write("test")
        result = scan_data_dir(self.tmpdir)
        names = [f["name"] for f in result["files"]]
        self.assertEqual(names, ["a.json", "b.csv", "c.json"])


class HasChangedTest(unittest.TestCase):
    """Tests for has_changed."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_no_change_returns_false(self):
        """If no files changed, has_changed should return False."""
        with open(os.path.join(self.tmpdir, "a.json"), "w") as f:
            json.dump([], f)
        snapshot = scan_data_dir(self.tmpdir)
        time.sleep(0.05)  # Small delay
        self.assertFalse(has_changed(snapshot, self.tmpdir))

    def test_modified_file_returns_true(self):
        """If a file's mtime changes, has_changed should return True."""
        filepath = os.path.join(self.tmpdir, "a.json")
        with open(filepath, "w") as f:
            json.dump([], f)
        snapshot = scan_data_dir(self.tmpdir)

        # Modify the file
        time.sleep(0.1)
        with open(filepath, "w") as f:
            json.dump([1], f)

        self.assertTrue(has_changed(snapshot, self.tmpdir))

    def test_new_file_returns_true(self):
        """If a new file is added, has_changed should return True."""
        with open(os.path.join(self.tmpdir, "a.json"), "w") as f:
            json.dump([], f)
        snapshot = scan_data_dir(self.tmpdir)

        # Add new file
        with open(os.path.join(self.tmpdir, "b.json"), "w") as f:
            json.dump([], f)

        self.assertTrue(has_changed(snapshot, self.tmpdir))

    def test_removed_file_returns_true(self):
        """If a file is removed, has_changed should return True."""
        filepath = os.path.join(self.tmpdir, "a.json")
        with open(filepath, "w") as f:
            json.dump([], f)
        snapshot = scan_data_dir(self.tmpdir)

        # Remove file
        os.remove(filepath)

        self.assertTrue(has_changed(snapshot, self.tmpdir))

    def test_none_snapshot_returns_true(self):
        """If previous snapshot is None, should return True."""
        self.assertTrue(has_changed(None, self.tmpdir))


class GetDataDirMetadataTest(unittest.TestCase):
    """Tests for get_data_dir_metadata."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_metadata_structure(self):
        """Should return structured metadata."""
        with open(os.path.join(self.tmpdir, "a.json"), "w") as f:
            json.dump([], f)
        meta = get_data_dir_metadata(self.tmpdir)
        self.assertIn("data_dir", meta)
        self.assertIn("file_count", meta)
        self.assertIn("files", meta)
        self.assertIn("last_modified", meta)
        self.assertIn("scanned_at", meta)
        self.assertIn("error", meta)

    def test_last_modified_is_most_recent(self):
        """last_modified should be the max mtime."""
        with open(os.path.join(self.tmpdir, "a.json"), "w") as f:
            json.dump([], f)
        meta = get_data_dir_metadata(self.tmpdir)
        self.assertIsNotNone(meta["last_modified"])

    def test_change_detection_with_snapshot(self):
        """Should detect changes when given a previous snapshot."""
        with open(os.path.join(self.tmpdir, "a.json"), "w") as f:
            json.dump([], f)
        snapshot = scan_data_dir(self.tmpdir)

        # No change
        meta = get_data_dir_metadata(self.tmpdir, previous_snapshot=snapshot)
        self.assertFalse(meta["changed"])

        # Modify
        time.sleep(0.1)
        with open(os.path.join(self.tmpdir, "a.json"), "w") as f:
            json.dump([1], f)

        meta2 = get_data_dir_metadata(self.tmpdir, previous_snapshot=snapshot)
        self.assertTrue(meta2["changed"])


class DataDirStatusEndpointTest(unittest.TestCase):
    """Tests for the GET /data/status HTTP endpoint."""

    def _find_free_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def test_data_status_returns_file_list(self):
        """GET /data/status should return data directory metadata."""
        from server import create_server
        import urllib.request

        port = self._find_free_port()
        server = create_server(port=port, log_dir=tempfile.mkdtemp())
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        import time
        time.sleep(0.3)

        try:
            url = f"http://localhost:{port}/data/status"
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.assertIn("file_count", data)
                self.assertIn("files", data)
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=1)
