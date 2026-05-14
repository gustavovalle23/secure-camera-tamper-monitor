import json
import mimetypes
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from app_state import camera, database
from config import EXPORT_DIR
from esp32_api import normalize_esp32_event, normalize_esp32_payload
from event_service import (
    build_esp32_heartbeat_message,
    build_mega_heartbeat_message,
    build_snapshot_public_path,
    get_recent_events,
    get_recent_snapshots,
    normalize_event_limit,
    normalize_snapshot_event,
    record_event,
    resolve_snapshot_file,
    summarize_snapshot_path,
)
from export import export_events
from mega_serial import normalize_mega_payload
from system_health import get_camera_health_payload, get_log_health_payload, get_pi_health_payload


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "SecureCameraHTTP/1.0"

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self._write_json(HTTPStatus.OK, self._root_payload())
        if parsed.path == "/video_feed":
            return self._stream_mjpeg(parse_qs(parsed.query))
        if parsed.path.startswith("/static/snapshots/"):
            return self._serve_snapshot(parsed.path.removeprefix("/static/snapshots/"))
        if parsed.path == "/api/status":
            return self._write_json(HTTPStatus.OK, self._status_payload())
        if parsed.path == "/api/health":
            return self._write_json(HTTPStatus.OK, get_pi_health_payload())
        if parsed.path == "/api/health/camera":
            return self._write_json(HTTPStatus.OK, get_camera_health_payload())
        if parsed.path == "/api/health/logs":
            return self._write_json(HTTPStatus.OK, get_log_health_payload())
        if parsed.path == "/api/events":
            return self._write_json(HTTPStatus.OK, get_recent_events(limit=self._query_limit(parsed.query)))
        if parsed.path == "/api/snapshots":
            return self._write_json(HTTPStatus.OK, get_recent_snapshots(limit=self._query_limit(parsed.query)))
        if parsed.path == "/api/export/events":
            return self._export_events()
        return self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/esp32/heartbeat":
                return self._handle_esp32_heartbeat()
            if parsed.path == "/api/esp32/event":
                return self._handle_esp32_event()
            if parsed.path == "/api/mega/heartbeat":
                return self._handle_mega_heartbeat()
        except ValueError:
            return
        if parsed.path == "/api/camera/snapshot":
            return self._handle_snapshot()
        return self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def log_message(self, format, *args):
        del format, args

    def _root_payload(self):
        return {
            "service": "secure-camera-raspberry",
            "role": "api-and-camera-stream",
            "video_feed_url": "/video_feed",
            "status_url": "/api/status",
            "events_url": "/api/events",
        }

    def _status_payload(self):
        return {"devices": database.fetch_device_status(), "recent_events": get_recent_events(limit=20)}

    def _query_limit(self, query_string):
        return normalize_event_limit(parse_qs(query_string).get("limit", [None])[0])

    def _serve_snapshot(self, snapshot_name):
        snapshot_path = resolve_snapshot_file(snapshot_name)
        if snapshot_path is None:
            return self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "snapshot_not_found"})
        content_type, _ = mimetypes.guess_type(snapshot_path)
        return self._send_file(snapshot_path, content_type or "application/octet-stream", os.path.basename(snapshot_path), as_attachment=False)

    def _export_events(self):
        path = export_events(get_recent_events(limit=200), EXPORT_DIR)
        return self._send_file(path, "application/json", os.path.basename(path))

    def _handle_esp32_heartbeat(self):
        payload = normalize_esp32_payload(self._read_json_body())
        self._upsert_device(payload["device"], payload)
        metadata = record_event("esp32_heartbeat", payload["device"], "debug", build_esp32_heartbeat_message(payload), meta=payload)
        return self._write_json(HTTPStatus.OK, {"ok": True, "device": payload["device"], **metadata})

    def _handle_esp32_event(self):
        payload = normalize_esp32_event(self._read_json_body())
        self._upsert_device(payload["device"], payload)
        metadata = record_event(payload["type"], payload["device"], payload["severity"], payload["message"], meta=payload)
        return self._write_json(HTTPStatus.OK, {"ok": True, "device": payload["device"], **metadata})

    def _handle_mega_heartbeat(self):
        payload = normalize_mega_payload(self._read_json_body())
        self._upsert_device(payload["device"], payload)
        metadata = record_event("mega_heartbeat", payload["device"], "debug", build_mega_heartbeat_message(payload))
        return self._write_json(HTTPStatus.OK, {"ok": True, "device": payload["device"], **metadata})

    def _handle_snapshot(self):
        payload = self._read_json_body()
        ok, frame = camera.read_frame()
        if not ok or frame is None:
            return self._write_json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": "camera_unavailable"})
        snapshot_event = normalize_snapshot_event(payload)
        snapshot_path = camera.save_snapshot(frame, prefix=snapshot_event["prefix"])
        snapshot_name = summarize_snapshot_path(snapshot_path)
        metadata = record_event(snapshot_event["type"], "camera", snapshot_event["severity"], snapshot_event["message"], snapshot=snapshot_name)
        return self._write_json(HTTPStatus.OK, {
            "ok": True,
            "snapshot_path": snapshot_path,
            "snapshot": snapshot_name,
            "snapshot_url": build_snapshot_public_path(snapshot_name),
            "type": snapshot_event["type"],
            "message": snapshot_event["message"],
            "motion_area": snapshot_event["motion_area"],
            **metadata,
        })

    def _upsert_device(self, device, payload):
        database.upsert_device_status(device=device, status="online", uptime_ms=payload.get("uptime_ms"), boot_count=payload.get("boot_count"), meta=payload)

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

    def _write_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type, download_name, as_attachment=True):
        with open(path, "rb") as handle:
            body = handle.read()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        disposition = "attachment" if as_attachment else "inline"
        self.send_header("Content-Disposition", f'{disposition}; filename="{download_name}"')
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _stream_mjpeg(self, query):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self._send_cors_headers()
        self.end_headers()
        zoom = query.get("zoom", [1.0])[0]
        focus_x = query.get("focus_x", [0.5])[0]
        focus_y = query.get("focus_y", [0.5])[0]
        try:
            for chunk in camera.mjpeg_stream(zoom=zoom, focus_x=focus_x, focus_y=focus_y):
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
class SecureCameraServer(ThreadingHTTPServer): daemon_threads = True
