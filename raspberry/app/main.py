import json
import os
import signal
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from camera import CameraService
from database import Database
from esp32_api import normalize_esp32_payload
from export import export_events
from mega_serial import normalize_mega_payload
from secure_log import SecureEventLog


HOST = os.getenv("RASPBERRY_HOST", "0.0.0.0")
PORT = int(os.getenv("RASPBERRY_PORT", "5000"))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
EXPORT_DIR = os.path.join(DATA_DIR, "exports")
STATIC_DIR = os.path.join(BASE_DIR, "static")
SNAPSHOT_DIR = os.path.join(STATIC_DIR, "snapshots")
DATABASE_PATH = os.path.join(DATA_DIR, "monitor.db")
SECURE_LOG_PATH = os.path.join(DATA_DIR, "secure_events.jsonl")


for path in (DATA_DIR, EXPORT_DIR, SNAPSHOT_DIR):
    os.makedirs(path, exist_ok=True)


database = Database(DATABASE_PATH)
database.init()
secure_log = SecureEventLog(SECURE_LOG_PATH)
camera = CameraService(SNAPSHOT_DIR)
httpd = None


def record_event(event_type: str, source: str, payload: dict):
    event_id = database.insert_event(event_type=event_type, source=source, payload=payload)
    secure_entry = secure_log.append(event_type=event_type, source=source, payload=payload)
    return {"event_id": event_id, "secure_hash": secure_entry["hash"]}


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "SecureCameraHTTP/1.0"

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/":
            self._write_json(
                HTTPStatus.OK,
                {
                    "service": "secure-camera-raspberry",
                    "role": "api-and-camera-stream",
                    "video_feed_url": "/video_feed",
                    "status_url": "/api/status",
                    "events_url": "/api/events",
                },
            )
            return

        if parsed.path == "/video_feed":
            self._stream_mjpeg()
            return

        if parsed.path == "/api/status":
            self._write_json(
                HTTPStatus.OK,
                {
                    "devices": database.fetch_device_status(),
                    "recent_events": database.fetch_recent_events(limit=20),
                },
            )
            return

        if parsed.path == "/api/events":
            query = parse_qs(parsed.query)
            limit = self._parse_limit(query.get("limit", ["50"])[0])
            self._write_json(HTTPStatus.OK, database.fetch_recent_events(limit=limit))
            return

        if parsed.path == "/api/export/events":
            events_payload = database.fetch_recent_events(limit=200)
            path = export_events(events_payload, EXPORT_DIR)
            self._send_file(path, "application/json", os.path.basename(path))
            return

        self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def do_POST(self):
        parsed = urlparse(self.path)

        try:
            if parsed.path == "/api/esp32/heartbeat":
                payload = normalize_esp32_payload(self._read_json_body())
                device = payload["device"]
                database.upsert_device_status(
                    device=device,
                    status="online",
                    uptime_ms=payload.get("uptime_ms"),
                    boot_count=payload.get("boot_count"),
                    meta=payload,
                )
                metadata = record_event("heartbeat", device, payload)
                self._write_json(HTTPStatus.OK, {"ok": True, "device": device, **metadata})
                return

            if parsed.path == "/api/mega/heartbeat":
                payload = normalize_mega_payload(self._read_json_body())
                device = payload["device"]
                database.upsert_device_status(
                    device=device,
                    status="online",
                    uptime_ms=payload.get("uptime_ms"),
                    boot_count=payload.get("boot_count"),
                    meta=payload,
                )
                metadata = record_event("heartbeat", device, payload)
                self._write_json(HTTPStatus.OK, {"ok": True, "device": device, **metadata})
                return
        except ValueError:
            return

        if parsed.path == "/api/camera/snapshot":
            ok, frame = camera.read_frame()
            if not ok or frame is None:
                self._write_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"ok": False, "error": "camera_unavailable"},
                )
                return

            snapshot_path = camera.save_snapshot(frame)
            payload = {"snapshot_path": snapshot_path}
            metadata = record_event("snapshot_saved", "camera", payload)
            self._write_json(HTTPStatus.OK, {"ok": True, **payload, **metadata})
            return

        self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def _parse_limit(self, value: str) -> int:
        try:
            limit = int(value)
        except ValueError:
            return 50

        return max(1, min(limit, 500))

    def _read_json_body(self):
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0

        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_json"})
            raise ValueError("invalid_json")

        if not isinstance(payload, dict):
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "json_object_required"})
            raise ValueError("json_object_required")

        return payload

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")

    def _write_json(self, status: HTTPStatus, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: str, content_type: str, download_name: str):
        with open(path, "rb") as handle:
            body = handle.read()

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _stream_mjpeg(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self._send_cors_headers()
        self.end_headers()

        try:
            for chunk in camera.mjpeg_stream():
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

    def log_message(self, format, *args):
        del format, args


class SecureCameraServer(ThreadingHTTPServer):
    daemon_threads = True


def shutdown_handler(signum, frame):
    del signum, frame

    if httpd is not None:
        httpd.shutdown()

    camera.stop()
    sys.exit(0)


signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)


if __name__ == "__main__":
    httpd = SecureCameraServer((HOST, PORT), RequestHandler)
    print(f"[HTTP] secure camera server listening on http://{HOST}:{PORT}")
    try:
        httpd.serve_forever()
    finally:
        camera.stop()
