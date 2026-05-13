import hashlib
import json
import os
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
                    last_hash = entry.get("hash", last_hash)
                except json.JSONDecodeError:
                    continue

        return last_hash

    def append(self, event_type: str, source: str, payload: dict):
        entry = {
            "created_at": utc_now(),
            "event_type": event_type,
            "source": source,
            "payload": payload,
            "previous_hash": self._last_hash,
        }
        digest_source = json.dumps(entry, sort_keys=True).encode("utf-8")
        entry["hash"] = hashlib.sha256(digest_source).hexdigest()

        with open(self.log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

        self._last_hash = entry["hash"]
        return entry
