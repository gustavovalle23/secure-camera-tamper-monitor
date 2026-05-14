import os
import posixpath

from app_state import database, secure_log
from config import SNAPSHOT_DIR


def record_event(event_type, device, severity, message, snapshot=None, acknowledged=False, meta=None):
    event = {
        "type": event_type,
        "severity": severity,
        "device": device,
        "message": message,
        "acknowledged": acknowledged,
    }
    if snapshot:
        event["snapshot"] = snapshot
    if meta is not None:
        event["meta"] = meta

    secure_entry = secure_log.append(event)
    database.insert_event(
        event_type=secure_entry["type"],
        source=secure_entry["device"],
        payload=secure_entry,
    )
    return {"event_id": secure_entry["id"], "secure_hash": secure_entry["hash"]}


def build_mega_heartbeat_message(payload):
    counter = payload.get("counter")
    return f"counter={counter}" if counter is not None else "heartbeat received"


def build_esp32_heartbeat_message(payload):
    parts = []
    if payload.get("counter") is not None:
        parts.append(f"counter={payload['counter']}")
    if payload.get("rssi") is not None:
        parts.append(f"rssi={payload['rssi']}")
    if payload.get("free_heap") is not None:
        parts.append(f"heap={payload['free_heap']}")
    return " ".join(parts) if parts else "heartbeat received"


def normalize_event_limit(raw_value):
    if raw_value is None or raw_value == "" or raw_value.lower() == "all":
        return None
    try:
        limit = int(raw_value)
    except ValueError:
        return 50
    return max(1, min(limit, 5000))


def get_recent_events(limit=None):
    return secure_log.read_events(limit=limit)


def get_recent_snapshots(limit=None):
    return secure_log.read_snapshots(limit=limit)


def summarize_snapshot_path(snapshot_path):
    return posixpath.basename(snapshot_path)


def build_snapshot_public_path(snapshot_name):
    return f"/static/snapshots/{snapshot_name}"


def resolve_snapshot_file(snapshot_name):
    safe_name = os.path.basename(snapshot_name)
    if safe_name != snapshot_name or safe_name in {"", ".", ".."}:
        return None
    path = os.path.join(SNAPSHOT_DIR, safe_name)
    return path if os.path.isfile(path) else None


def normalize_snapshot_event(payload):
    event_type = str(payload.get("type") or "snapshot_saved")
    severity = str(payload.get("severity") or "info")
    message = payload.get("message")
    motion_area = payload.get("motion_area")

    if message is None and motion_area is not None:
        message = f"Motion area={motion_area}"
    if message is None:
        message = event_type.replace("_", " ")

    if event_type == "motion_detected":
        prefix = "motion"
    elif event_type.startswith("camera_tamper"):
        prefix = "tamper"
    else:
        prefix = "snapshot"

    return {
        "type": event_type,
        "severity": severity,
        "message": str(message),
        "motion_area": motion_area,
        "prefix": prefix,
    }
