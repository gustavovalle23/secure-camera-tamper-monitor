import os
import signal
import sys

from flask import Flask, Response, jsonify, request, send_file

from camera import CameraService
from database import Database
from esp32_api import normalize_esp32_payload
from export import export_events
from mega_serial import normalize_mega_payload
from secure_log import SecureEventLog


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
EXPORT_DIR = os.path.join(DATA_DIR, "exports")
STATIC_DIR = os.path.join(BASE_DIR, "static")
SNAPSHOT_DIR = os.path.join(STATIC_DIR, "snapshots")
DATABASE_PATH = os.path.join(DATA_DIR, "monitor.db")
SECURE_LOG_PATH = os.path.join(DATA_DIR, "secure_events.jsonl")


for path in (DATA_DIR, EXPORT_DIR, SNAPSHOT_DIR):
    os.makedirs(path, exist_ok=True)


app = Flask(__name__, static_folder=STATIC_DIR)
database = Database(DATABASE_PATH)
database.init()
secure_log = SecureEventLog(SECURE_LOG_PATH)
camera = CameraService(SNAPSHOT_DIR)


def record_event(event_type: str, source: str, payload: dict):
    event_id = database.insert_event(event_type=event_type, source=source, payload=payload)
    secure_entry = secure_log.append(event_type=event_type, source=source, payload=payload)
    return {"event_id": event_id, "secure_hash": secure_entry["hash"]}


@app.get("/")
def index():
    return jsonify(
        {
            "service": "secure-camera-raspberry",
            "role": "api-and-camera-stream",
            "video_feed_url": "/video_feed",
            "status_url": "/api/status",
            "events_url": "/api/events",
        }
    )


@app.get("/video_feed")
def video_feed():
    return Response(
        camera.mjpeg_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/status")
def status():
    return jsonify(
        {
            "devices": database.fetch_device_status(),
            "recent_events": database.fetch_recent_events(limit=20),
        }
    )


@app.get("/api/events")
def events():
    limit = int(request.args.get("limit", "50"))
    return jsonify(database.fetch_recent_events(limit=limit))


@app.post("/api/esp32/heartbeat")
def esp32_heartbeat():
    payload = normalize_esp32_payload(request.get_json(force=True, silent=False) or {})
    device = payload["device"]
    database.upsert_device_status(
        device=device,
        status="online",
        uptime_ms=payload.get("uptime_ms"),
        boot_count=payload.get("boot_count"),
        meta=payload,
    )
    metadata = record_event("heartbeat", device, payload)
    return jsonify({"ok": True, "device": device, **metadata})


@app.post("/api/mega/heartbeat")
def mega_heartbeat():
    payload = normalize_mega_payload(request.get_json(force=True, silent=False) or {})
    device = payload["device"]
    database.upsert_device_status(
        device=device,
        status="online",
        uptime_ms=payload.get("uptime_ms"),
        boot_count=payload.get("boot_count"),
        meta=payload,
    )
    metadata = record_event("heartbeat", device, payload)
    return jsonify({"ok": True, "device": device, **metadata})


@app.post("/api/camera/snapshot")
def camera_snapshot():
    ok, frame = camera.read_frame()
    if not ok or frame is None:
        return jsonify({"ok": False, "error": "camera_unavailable"}), 503

    snapshot_path = camera.save_snapshot(frame)
    payload = {"snapshot_path": snapshot_path}
    metadata = record_event("snapshot_saved", "camera", payload)
    return jsonify({"ok": True, **payload, **metadata})


@app.get("/api/export/events")
def export_recent_events():
    events_payload = database.fetch_recent_events(limit=200)
    path = export_events(events_payload, EXPORT_DIR)
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))


def shutdown_handler(signum, frame):
    del signum, frame
    camera.stop()
    sys.exit(0)


signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
