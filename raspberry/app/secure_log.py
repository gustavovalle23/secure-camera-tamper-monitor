import hashlib
import json
import os
import re
from datetime import timezone
from datetime import datetime


def utc_now():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class SecureEventLog:
    def __init__(self, log_path: str):
        self.log_path = log_path
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        self._last_hash = self._read_last_hash()

    def _read_last_hash(self):
        if not os.path.exists(self.log_path):
            return "GENESIS"

        last_hash = "GENESIS"
        with open(self.log_path, "r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue

                try:
                    entry = json.loads(line)
                    last_hash = self._entry_hash(entry) or last_hash
                except json.JSONDecodeError:
                    continue

        return last_hash

    def append(self, event: dict):
        entry = self._build_event_entry(event)

        with open(self.log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

        self._last_hash = entry["hash"]
        return entry

    def read_events(self, limit=None):
        if not os.path.exists(self.log_path):
            return []

        events = []
        previous_hash = "GENESIS"

        with open(self.log_path, "r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue

                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    previous_hash = "INVALID"
                    continue

                normalized = self._normalize_event_entry(
                    entry=entry,
                    line_number=line_number,
                    previous_hash=previous_hash,
                )
                events.append(normalized)
                previous_hash = self._entry_hash(entry) or previous_hash

        events.reverse()
        if limit is None:
            return events

        return events[:limit]

    def read_snapshots(self, limit=None):
        snapshots = []
        for event in self.read_events(limit=None):
            snapshot_name = event.get("snapshot")
            if not snapshot_name:
                continue

            snapshots.append(
                {
                    "filename": snapshot_name,
                    "path": f"/static/snapshots/{snapshot_name}",
                    "ts": event["ts"],
                    "eventId": event["id"],
                    "type": event["type"],
                    "motionArea": self._extract_motion_area(event.get("message", "")),
                    "message": event.get("message", ""),
                }
            )

        if limit is None:
            return snapshots

        return snapshots[:limit]

    def get_health(self):
        if not os.path.exists(self.log_path):
            return {
                "ok": True,
                "file_exists": False,
                "integrity_valid": None,
                "entry_count": 0,
                "file_size_bytes": 0,
                "last_write_ms": None,
            }

        entry_count = 0
        previous_hash = "GENESIS"
        integrity_valid = True

        with open(self.log_path, "r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue

                entry_count += 1
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    integrity_valid = False
                    continue

                expected_previous = self._entry_prev_hash(entry)
                current_hash = self._entry_hash(entry)
                recalculated_hash = self._calculate_hash(entry)

                if expected_previous != previous_hash or current_hash != recalculated_hash:
                    integrity_valid = False

                previous_hash = current_hash or previous_hash

        file_stats = os.stat(self.log_path)
        return {
            "ok": True,
            "file_exists": True,
            "integrity_valid": integrity_valid,
            "entry_count": entry_count,
            "file_size_bytes": file_stats.st_size,
            "last_write_ms": int(file_stats.st_mtime * 1000),
        }

    def _build_event_entry(self, event: dict):
        timestamp = event.get("ts") or utc_now()
        event_id = event.get("id") or self._generate_event_id(timestamp)
        previous_hash = self._last_hash

        entry = {
            "id": event_id,
            "ts": timestamp,
            "type": event["type"],
            "severity": event["severity"],
            "device": event["device"],
            "message": event["message"],
            "prevHash": previous_hash,
            "acknowledged": bool(event.get("acknowledged", False)),
        }

        if event.get("snapshot"):
            entry["snapshot"] = event["snapshot"]
        if event.get("meta") is not None:
            entry["meta"] = event["meta"]

        entry["hash"] = self._calculate_hash(entry)
        return entry

    def _generate_event_id(self, timestamp: str):
        epoch_ms = self._iso_to_epoch_ms(timestamp)
        suffix_source = f"{timestamp}:{self._last_hash}".encode("utf-8")
        suffix = int(hashlib.sha256(suffix_source).hexdigest()[:4], 16) % 10000
        return f"evt_{epoch_ms}_{suffix:04d}"

    def _normalize_event_entry(self, entry: dict, line_number: int, previous_hash: str):
        if self._is_modern_entry(entry):
            expected_previous = entry.get("prevHash", "GENESIS")
            current_hash = entry.get("hash")
            normalized = {
                "id": entry.get("id") or self._fallback_event_id(entry.get("ts"), line_number),
                "ts": entry.get("ts") or utc_now(),
                "type": entry.get("type", "unknown"),
                "severity": entry.get("severity", "info"),
                "device": entry.get("device", "unknown"),
                "message": entry.get("message", ""),
                "prevHash": self._display_hash(expected_previous),
                "hash": self._display_hash(current_hash),
                "acknowledged": bool(entry.get("acknowledged", False)),
            }
            if entry.get("snapshot"):
                normalized["snapshot"] = entry["snapshot"]
            if entry.get("meta") is not None:
                normalized["meta"] = entry["meta"]
            normalized["valid"] = (
                expected_previous == previous_hash
                and current_hash == self._calculate_hash(entry)
            )
            return normalized

        payload = entry.get("payload") or {}
        event_type = self._normalize_legacy_type(entry.get("event_type"), payload, entry.get("source"))
        severity = self._normalize_legacy_severity(event_type, payload)
        message = self._normalize_legacy_message(event_type, payload)
        snapshot = self._normalize_legacy_snapshot(payload)
        expected_previous = entry.get("previous_hash", "GENESIS")
        current_hash = entry.get("hash")
        timestamp = entry.get("created_at") or utc_now()

        normalized = {
            "id": payload.get("id") or self._fallback_event_id(timestamp, line_number),
            "ts": timestamp,
            "type": event_type,
            "severity": severity,
            "device": payload.get("device") or entry.get("source") or "unknown",
            "message": message,
            "prevHash": self._display_hash(expected_previous),
            "hash": self._display_hash(current_hash),
            "acknowledged": bool(payload.get("acknowledged", False)),
            "valid": (
                expected_previous == previous_hash
                and current_hash == self._calculate_hash(entry)
            ),
        }
        if snapshot:
            normalized["snapshot"] = snapshot
        return normalized

    def _is_modern_entry(self, entry: dict):
        return "prevHash" in entry and "type" in entry and "ts" in entry

    def _entry_hash(self, entry: dict):
        return entry.get("hash")

    def _entry_prev_hash(self, entry: dict):
        return entry.get("prevHash", entry.get("previous_hash", "GENESIS"))

    def _calculate_hash(self, entry: dict):
        if self._is_modern_entry(entry):
            reconstructed = {
                "id": entry.get("id"),
                "ts": entry.get("ts"),
                "type": entry.get("type"),
                "severity": entry.get("severity"),
                "device": entry.get("device"),
                "message": entry.get("message"),
                "prevHash": entry.get("prevHash"),
                "acknowledged": bool(entry.get("acknowledged", False)),
            }
            if entry.get("snapshot"):
                reconstructed["snapshot"] = entry.get("snapshot")
            if entry.get("meta") is not None:
                reconstructed["meta"] = entry.get("meta")
        else:
            reconstructed = {
                "created_at": entry.get("created_at"),
                "event_type": entry.get("event_type"),
                "source": entry.get("source"),
                "payload": entry.get("payload"),
                "previous_hash": entry.get("previous_hash"),
            }

        digest_source = json.dumps(reconstructed, sort_keys=True).encode("utf-8")
        digest = hashlib.sha256(digest_source).hexdigest()
        if self._is_modern_entry(entry):
            return digest[:12]
        return digest

    def _fallback_event_id(self, timestamp: str, line_number: int):
        epoch_ms = self._iso_to_epoch_ms(timestamp)
        return f"evt_{epoch_ms}_{line_number:04d}"

    def _iso_to_epoch_ms(self, value: str):
        try:
            normalized = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            return 0

    def _normalize_legacy_type(self, event_type: str, payload: dict, source: str):
        if payload.get("type"):
            return payload["type"]

        if event_type == "heartbeat":
            device = payload.get("device") or source or "device"
            if device == "mega2560":
                return "mega_heartbeat"
            if device == "esp32":
                return "esp32_heartbeat"
            return f"{device}_heartbeat"

        return event_type or "unknown"

    def _normalize_legacy_severity(self, event_type: str, payload: dict):
        if payload.get("severity"):
            return payload["severity"]

        if "heartbeat" in event_type:
            return "debug"
        if "tamper" in event_type:
            return "critical"
        if "motion" in event_type:
            return "alert"
        if "offline" in event_type:
            return "warning"
        return "info"

    def _normalize_legacy_message(self, event_type: str, payload: dict):
        if payload.get("message"):
            return payload["message"]

        if event_type == "mega_heartbeat":
            counter = payload.get("counter")
            return f"counter={counter}" if counter is not None else "heartbeat received"

        if event_type == "esp32_heartbeat":
            parts = []
            if payload.get("counter") is not None:
                parts.append(f"counter={payload['counter']}")
            if payload.get("rssi") is not None:
                parts.append(f"rssi={payload['rssi']}")
            return " ".join(parts) if parts else "heartbeat received"

        snapshot = self._normalize_legacy_snapshot(payload)
        if snapshot:
            return snapshot

        return event_type.replace("_", " ")

    def _normalize_legacy_snapshot(self, payload: dict):
        snapshot = payload.get("snapshot")
        if snapshot:
            return snapshot

        snapshot_path = payload.get("snapshot_path")
        if snapshot_path:
            return os.path.basename(snapshot_path)

        return None

    def _display_hash(self, value):
        if not value:
            return value
        if value == "GENESIS":
            return value
        return str(value)[:12]

    def _extract_motion_area(self, message: str):
        match = re.search(r"motion area=(\d+)", message, flags=re.IGNORECASE)
        if not match:
            return None
        return int(match.group(1))
