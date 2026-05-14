import json
import mimetypes
import os
import platform
import posixpath
import signal
import shutil
import socket
import subprocess
import sys
import time
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


class CpuUsageSampler:
    def __init__(self):
        self._previous = None

    def sample_percent(self):
        stats = self._read_proc_stat()
        if stats is None:
            load = self._loadavg_percent()
            return round(load, 1) if load is not None else None

        if self._previous is None:
            self._previous = stats
            load = self._loadavg_percent()
            return round(load, 1) if load is not None else None

        previous_idle, previous_total = self._previous
        current_idle, current_total = stats
        self._previous = stats

        total_delta = current_total - previous_total
        idle_delta = current_idle - previous_idle

        if total_delta <= 0:
            return 0.0

        busy = 1 - (idle_delta / total_delta)
        return round(max(0.0, min(100.0, busy * 100)), 1)

    def _read_proc_stat(self):
        try:
            with open("/proc/stat", "r", encoding="utf-8") as handle:
                first_line = handle.readline().strip()
        except OSError:
            return None

        parts = first_line.split()
        if len(parts) < 6 or parts[0] != "cpu":
            return None

        values = [int(value) for value in parts[1:]]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values)
        return idle, total

    def _loadavg_percent(self):
        try:
            load1, _, _ = os.getloadavg()
        except (AttributeError, OSError):
            return None

        cpu_count = os.cpu_count() or 1
        return min(100.0, (load1 / cpu_count) * 100)


cpu_sampler = CpuUsageSampler()


def record_event(
    event_type: str,
    device: str,
    severity: str,
    message: str,
    snapshot=None,
    acknowledged=False,
):
    event = {
        "type": event_type,
        "severity": severity,
        "device": device,
        "message": message,
        "acknowledged": acknowledged,
    }
    if snapshot:
        event["snapshot"] = snapshot

    secure_entry = secure_log.append(event)
    database.insert_event(
        event_type=secure_entry["type"],
        source=secure_entry["device"],
        payload=secure_entry,
    )
    return {"event_id": secure_entry["id"], "secure_hash": secure_entry["hash"]}


def build_mega_heartbeat_message(payload: dict):
    counter = payload.get("counter")
    return f"counter={counter}" if counter is not None else "heartbeat received"


def build_esp32_heartbeat_message(payload: dict):
    parts = []
    if payload.get("counter") is not None:
        parts.append(f"counter={payload['counter']}")
    if payload.get("rssi") is not None:
        parts.append(f"rssi={payload['rssi']}")

    return " ".join(parts) if parts else "heartbeat received"


def normalize_event_limit(raw_value):
    if raw_value is None or raw_value == "":
        return None

    if raw_value.lower() == "all":
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


def summarize_snapshot_path(snapshot_path: str):
    return posixpath.basename(snapshot_path)


def build_snapshot_public_path(snapshot_name: str):
    return f"/static/snapshots/{snapshot_name}"


def resolve_snapshot_file(snapshot_name: str):
    safe_name = os.path.basename(snapshot_name)
    if safe_name != snapshot_name or safe_name in {"", ".", ".."}:
        return None

    path = os.path.join(SNAPSHOT_DIR, safe_name)
    if not os.path.isfile(path):
        return None

    return path


def normalize_snapshot_event(payload: dict):
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


def get_primary_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


def read_system_uptime_seconds():
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as handle:
            return float(handle.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def read_memory_stats_mb():
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return None

    values = {}
    for line in lines:
        key, raw_value = line.split(":", 1)
        values[key] = int(raw_value.strip().split()[0])

    total_kb = values.get("MemTotal")
    available_kb = values.get("MemAvailable")
    if total_kb is None or available_kb is None:
        return None

    used_kb = total_kb - available_kb
    return {
        "mem_total_mb": round(total_kb / 1024, 1),
        "mem_used_mb": round(used_kb / 1024, 1),
    }


def read_cpu_temp_c():
    thermal_path = "/sys/class/thermal/thermal_zone0/temp"
    try:
        with open(thermal_path, "r", encoding="utf-8") as handle:
            raw_value = handle.read().strip()
        return round(int(raw_value) / 1000, 1)
    except (OSError, ValueError):
        pass

    try:
        result = subprocess.run(
            ["vcgencmd", "measure_temp"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    output = result.stdout.strip()
    if "=" not in output:
        return None

    try:
        temp_text = output.split("=", 1)[1].split("'", 1)[0]
        return round(float(temp_text), 1)
    except ValueError:
        return None


def get_pi_health_payload():
    uptime_seconds = read_system_uptime_seconds()
    memory_stats = read_memory_stats_mb() or {}
    disk = shutil.disk_usage("/")
    cpu_temp = read_cpu_temp_c()
    cpu_usage = cpu_sampler.sample_percent()
    hostname = socket.gethostname()
    now_ms = int(time.time() * 1000)
    camera_health = camera.get_health()

    payload = {
        "ok": True,
        "source": "pi.local",
        "hostname": hostname,
        "ip": get_primary_ip(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "service_running": True,
        "captured_at_ms": now_ms,
        "boot_time_ms": int((time.time() - uptime_seconds) * 1000) if uptime_seconds is not None else None,
        "uptime_ms": int(uptime_seconds * 1000) if uptime_seconds is not None else None,
        "cpu_usage_pct": cpu_usage,
        "cpu_temp_c": cpu_temp,
        "mem_used_mb": memory_stats.get("mem_used_mb"),
        "mem_total_mb": memory_stats.get("mem_total_mb"),
        "disk_free_gb": round(disk.free / (1024 ** 3), 2),
        "disk_total_gb": round(disk.total / (1024 ** 3), 2),
        "camera_online": camera_health["camera_online"],
    }
    return payload


def get_camera_health_payload():
    payload = camera.get_health()
    payload["captured_at_ms"] = int(time.time() * 1000)
    return payload


def get_log_health_payload():
    payload = secure_log.get_health()
    payload["captured_at_ms"] = int(time.time() * 1000)
    return payload


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

        if parsed.path.startswith("/static/snapshots/"):
            snapshot_name = parsed.path.removeprefix("/static/snapshots/")
            snapshot_path = resolve_snapshot_file(snapshot_name)
            if snapshot_path is None:
                self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "snapshot_not_found"})
                return

            content_type, _ = mimetypes.guess_type(snapshot_path)
            self._send_file(
                snapshot_path,
                content_type or "application/octet-stream",
                os.path.basename(snapshot_path),
                as_attachment=False,
            )
            return

        if parsed.path == "/api/status":
            self._write_json(
                HTTPStatus.OK,
                {
                    "devices": database.fetch_device_status(),
                    "recent_events": get_recent_events(limit=20),
                },
            )
            return

        if parsed.path == "/api/health":
            self._write_json(HTTPStatus.OK, get_pi_health_payload())
            return

        if parsed.path == "/api/health/camera":
            self._write_json(HTTPStatus.OK, get_camera_health_payload())
            return

        if parsed.path == "/api/health/logs":
            self._write_json(HTTPStatus.OK, get_log_health_payload())
            return

        if parsed.path == "/api/events":
            query = parse_qs(parsed.query)
            limit = normalize_event_limit(query.get("limit", [None])[0])
            self._write_json(HTTPStatus.OK, get_recent_events(limit=limit))
            return

        if parsed.path == "/api/snapshots":
            query = parse_qs(parsed.query)
            limit = normalize_event_limit(query.get("limit", [None])[0])
            self._write_json(HTTPStatus.OK, get_recent_snapshots(limit=limit))
            return

        if parsed.path == "/api/export/events":
            events_payload = get_recent_events(limit=200)
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
                metadata = record_event(
                    event_type="esp32_heartbeat",
                    device=device,
                    severity="debug",
                    message=build_esp32_heartbeat_message(payload),
                )
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
                metadata = record_event(
                    event_type="mega_heartbeat",
                    device=device,
                    severity="debug",
                    message=build_mega_heartbeat_message(payload),
                )
                self._write_json(HTTPStatus.OK, {"ok": True, "device": device, **metadata})
                return
        except ValueError:
            return

        if parsed.path == "/api/camera/snapshot":
            payload = self._read_json_body()
            ok, frame = camera.read_frame()
            if not ok or frame is None:
                self._write_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"ok": False, "error": "camera_unavailable"},
                )
                return

            snapshot_event = normalize_snapshot_event(payload)
            snapshot_path = camera.save_snapshot(frame, prefix=snapshot_event["prefix"])
            snapshot_name = summarize_snapshot_path(snapshot_path)
            metadata = record_event(
                event_type=snapshot_event["type"],
                device="camera",
                severity=snapshot_event["severity"],
                message=snapshot_event["message"],
                snapshot=snapshot_name,
            )
            self._write_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "snapshot_path": snapshot_path,
                    "snapshot": snapshot_name,
                    "snapshot_url": build_snapshot_public_path(snapshot_name),
                    "type": snapshot_event["type"],
                    "message": snapshot_event["message"],
                    "motion_area": snapshot_event["motion_area"],
                    **metadata,
                },
            )
            return

        self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

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

    def _send_file(self, path: str, content_type: str, download_name: str, as_attachment: bool = True):
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
