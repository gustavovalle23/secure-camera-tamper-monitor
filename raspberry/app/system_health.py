import os
import platform
import shutil
import socket
import subprocess
import time

from app_state import camera, secure_log


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
                parts = handle.readline().strip().split()
        except OSError:
            return None
        if len(parts) < 6 or parts[0] != "cpu":
            return None
        values = [int(value) for value in parts[1:]]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        return idle, sum(values)

    def _loadavg_percent(self):
        try:
            load1, _, _ = os.getloadavg()
        except (AttributeError, OSError):
            return None
        cpu_count = os.cpu_count() or 1
        return min(100.0, (load1 / cpu_count) * 100)


cpu_sampler = CpuUsageSampler()


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
            values = {
                line.split(":", 1)[0]: int(line.split(":", 1)[1].strip().split()[0])
                for line in handle.readlines()
            }
    except OSError:
        return None

    total_kb = values.get("MemTotal")
    available_kb = values.get("MemAvailable")
    if total_kb is None or available_kb is None:
        return None
    used_kb = total_kb - available_kb
    return {"mem_total_mb": round(total_kb / 1024, 1), "mem_used_mb": round(used_kb / 1024, 1)}


def read_cpu_temp_c():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r", encoding="utf-8") as handle:
            return round(int(handle.read().strip()) / 1000, 1)
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
        return round(float(output.split("=", 1)[1].split("'", 1)[0]), 1)
    except ValueError:
        return None


def get_pi_health_payload():
    uptime_seconds = read_system_uptime_seconds()
    memory_stats = read_memory_stats_mb() or {}
    disk = shutil.disk_usage("/")
    camera_health = camera.get_health()
    return {
        "ok": True,
        "source": "pi.local",
        "hostname": socket.gethostname(),
        "ip": get_primary_ip(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "service_running": True,
        "captured_at_ms": int(time.time() * 1000),
        "boot_time_ms": int((time.time() - uptime_seconds) * 1000) if uptime_seconds is not None else None,
        "uptime_ms": int(uptime_seconds * 1000) if uptime_seconds is not None else None,
        "cpu_usage_pct": cpu_sampler.sample_percent(),
        "cpu_temp_c": read_cpu_temp_c(),
        "mem_used_mb": memory_stats.get("mem_used_mb"),
        "mem_total_mb": memory_stats.get("mem_total_mb"),
        "disk_free_gb": round(disk.free / (1024 ** 3), 2),
        "disk_total_gb": round(disk.total / (1024 ** 3), 2),
        "camera_online": camera_health["camera_online"],
    }


def get_camera_health_payload():
    payload = camera.get_health()
    payload["captured_at_ms"] = int(time.time() * 1000)
    return payload


def get_log_health_payload():
    payload = secure_log.get_health()
    payload["captured_at_ms"] = int(time.time() * 1000)
    return payload
