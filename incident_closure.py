"""Incident closure workflow for operator-managed incident resolution.

Tracks operator updates for incident report snapshots so teams can move an
incident through explicit closure states with notes and linked references.
"""

import threading
import time

from audit_chain import append_audit_entry

VALID_STATUSES = {"open", "investigating", "monitoring", "resolved"}
ALLOWED_TRANSITIONS = {
    "open": {"investigating", "monitoring", "resolved"},
    "investigating": {"monitoring", "resolved"},
    "monitoring": {"investigating", "resolved"},
    "resolved": set(),
}

_lock = threading.Lock()
_records = {}


def _timestamp():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _normalize_list(values):
    if values is None:
        return []
    if not isinstance(values, list):
        return []
    result = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            result.append(text)
    return result


def _copy_record(record):
    return {
        "report_id": record["report_id"],
        "status": record["status"],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "updated_by": record["updated_by"],
        "resolved_at": record.get("resolved_at"),
        "resolution_note": record.get("resolution_note", ""),
        "linked_alert_ids": list(record.get("linked_alert_ids", [])),
        "linked_receipt_ids": list(record.get("linked_receipt_ids", [])),
        "history": [dict(entry) for entry in record.get("history", [])],
    }


def get_closure(report_id):
    """Return a single incident closure record by report ID."""
    with _lock:
        record = _records.get(report_id)
        return _copy_record(record) if record else None


def query_closures(status=None, limit=20, offset=0):
    """Query incident closure records, newest first."""
    with _lock:
        records = [_copy_record(record) for record in _records.values()]

    records.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    if status:
        records = [record for record in records if record.get("status") == status]

    total = len(records)
    page = records[offset: offset + limit]
    return {
        "closures": page,
        "total": total,
        "summary": get_closure_summary(records),
    }


def get_closure_summary(records=None):
    """Return aggregate closure statistics."""
    if records is None:
        with _lock:
            records = [_copy_record(record) for record in _records.values()]

    by_status = {}
    resolved_count = 0
    active_count = 0
    for record in records:
        status = record.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        if status == "resolved":
            resolved_count += 1
        else:
            active_count += 1

    return {
        "total": len(records),
        "active_count": active_count,
        "resolved_count": resolved_count,
        "by_status": by_status,
    }


def upsert_closure(report_id, status, updated_by="operator", resolution_note=None,
                   linked_alert_ids=None, linked_receipt_ids=None):
    """Create or update an incident closure record."""
    report_id = str(report_id or "").strip()
    if not report_id:
        return {"error": "invalid_report_id"}

    status = str(status or "").strip()
    if status not in VALID_STATUSES:
        return {"error": "invalid_status", "status": status}

    resolution_note = (resolution_note or "").strip()
    linked_alert_ids = _normalize_list(linked_alert_ids)
    linked_receipt_ids = _normalize_list(linked_receipt_ids)
    now = _timestamp()

    with _lock:
        existing = _records.get(report_id)
        if existing is None:
            if status == "resolved" and not resolution_note:
                return {"error": "resolution_note_required", "status": status}

            record = {
                "report_id": report_id,
                "status": status,
                "created_at": now,
                "updated_at": now,
                "updated_by": updated_by or "operator",
                "resolved_at": now if status == "resolved" else None,
                "resolution_note": resolution_note,
                "linked_alert_ids": linked_alert_ids,
                "linked_receipt_ids": linked_receipt_ids,
                "history": [{
                    "from_status": None,
                    "to_status": status,
                    "updated_by": updated_by or "operator",
                    "resolution_note": resolution_note,
                    "timestamp": now,
                }],
            }
            _records[report_id] = record
        else:
            current_status = existing["status"]
            if status != current_status and status not in ALLOWED_TRANSITIONS.get(current_status, set()):
                return {
                    "error": "invalid_transition",
                    "from_status": current_status,
                    "to_status": status,
                }

            if status == "resolved" and not resolution_note and not existing.get("resolution_note"):
                return {"error": "resolution_note_required", "status": status}

            existing["status"] = status
            existing["updated_at"] = now
            existing["updated_by"] = updated_by or "operator"
            if resolution_note:
                existing["resolution_note"] = resolution_note
            if linked_alert_ids:
                existing["linked_alert_ids"] = linked_alert_ids
            if linked_receipt_ids:
                existing["linked_receipt_ids"] = linked_receipt_ids
            if status == "resolved":
                existing["resolved_at"] = now
            elif status != "resolved":
                existing["resolved_at"] = None

            existing["history"].append({
                "from_status": current_status,
                "to_status": status,
                "updated_by": updated_by or "operator",
                "resolution_note": resolution_note,
                "timestamp": now,
            })
            record = existing

    append_audit_entry(
        action="incident:closure_update",
        operator=updated_by or "operator",
        source_ip="127.0.0.1",
        details={
            "report_id": report_id,
            "status": status,
            "linked_alert_ids": linked_alert_ids,
            "linked_receipt_ids": linked_receipt_ids,
        },
        result="success",
    )
    return _copy_record(record)


def reset_closures():
    """Clear all closure records."""
    with _lock:
        _records.clear()

    append_audit_entry(
        action="incident:closure_reset",
        operator="api",
        source_ip="127.0.0.1",
        details={"operation": "reset_closures"},
        result="success",
    )
