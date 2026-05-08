
"""
Data Directory Monitor

Tracks the state of data directories (JSON/CSV files) using mtime-based
change detection. Provides metadata about what files exist and when they
were last modified, so that long-lived processes can detect when data
has been updated without restarting.

Architecture:
- scan_data_dir(): Returns a snapshot of all data files with mtimes
- has_changed(): Compares a directory's current state against a previous snapshot
- get_data_dir_metadata(): Returns structured metadata including file count,
  last modified time, and change detection status

Zero external dependencies: stdlib json, os, datetime, glob only.
"""
import os
import datetime
import glob


def _get_data_files(data_dir):
    """Get all JSON and CSV files in the data directory.

    Args:
        data_dir: Path to the data directory.

    Returns:
        List of (filename, filepath, mtime_iso) tuples.
    """
    files = []
    for ext in ("*.json", "*.csv"):
        pattern = os.path.join(data_dir, ext)
        for filepath in glob.glob(pattern):
            filename = os.path.basename(filepath)
            mtime = os.path.getmtime(filepath)
            mtime_iso = datetime.datetime.fromtimestamp(
                mtime, tz=datetime.timezone.utc
            ).isoformat()
            files.append((filename, filepath, mtime_iso))
    return sorted(files, key=lambda x: x[0])


def scan_data_dir(data_dir):
    """Scan a data directory and return a snapshot of its state.

    Args:
        data_dir: Path to the data directory.

    Returns:
        dict with snapshot data:
            - files: list of {name, path, mtime}
            - file_count: int
            - scanned_at: ISO timestamp
            - error: str or None
    """
    result = {
        "files": [],
        "file_count": 0,
        "scanned_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "error": None,
    }

    try:
        if not os.path.isdir(data_dir):
            result["error"] = f"Directory not found: {data_dir}"
            return result

        files = _get_data_files(data_dir)
        result["files"] = [
            {"name": f[0], "path": f[1], "mtime": f[2]} for f in files
        ]
        result["file_count"] = len(files)
    except Exception as e:
        result["error"] = str(e)

    return result


def has_changed(previous_snapshot, data_dir):
    """Check if a data directory has changed since a previous snapshot.

    Compares file names and mtimes. Returns True if any file was added,
    removed, or modified.

    Args:
        previous_snapshot: A dict returned by scan_data_dir().
        data_dir: Path to the data directory.

    Returns:
        bool: True if changes detected, False if unchanged.
    """
    if previous_snapshot is None:
        return True

    current = scan_data_dir(data_dir)
    if current["error"]:
        return True

    prev_files = previous_snapshot.get("files", [])
    curr_files = current.get("files", [])

    # Compare file count
    if len(prev_files) != len(curr_files):
        return True

    # Compare each file's mtime
    prev_by_name = {f["name"]: f["mtime"] for f in prev_files}
    for cf in curr_files:
        if cf["name"] not in prev_by_name:
            return True  # New file
        if cf["mtime"] != prev_by_name[cf["name"]]:
            return True  # Modified file

    return False


def get_data_dir_metadata(data_dir, previous_snapshot=None):
    """Get comprehensive data directory metadata.

    Args:
        data_dir: Path to the data directory.
        previous_snapshot: Optional previous snapshot for change detection.

    Returns:
        dict with metadata:
            - data_dir: str
            - file_count: int
            - files: list of file info
            - last_modified: str (most recent file mtime) or None
            - changed: bool (if previous_snapshot provided)
            - scanned_at: str
            - error: str or None
    """
    snapshot = scan_data_dir(data_dir)

    metadata = {
        "data_dir": data_dir,
        "file_count": snapshot["file_count"],
        "files": snapshot["files"],
        "last_modified": None,
        "changed": None,
        "scanned_at": snapshot["scanned_at"],
        "error": snapshot["error"],
    }

    if snapshot["files"]:
        metadata["last_modified"] = max(f["mtime"] for f in snapshot["files"])

    if previous_snapshot is not None:
        metadata["changed"] = has_changed(previous_snapshot, data_dir)

    return metadata
