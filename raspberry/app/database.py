import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime


def utc_now():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def init(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS device_status (
                    device TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    last_seen TEXT,
                    uptime_ms INTEGER,
                    boot_count INTEGER,
                    meta_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )

    def upsert_device_status(
        self,
        device: str,
        status: str,
        uptime_ms=None,
        boot_count=None,
        meta=None,
    ) -> None:
        payload = json.dumps(meta or {})
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO device_status (
                    device,
                    status,
                    last_seen,
                    uptime_ms,
                    boot_count,
                    meta_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(device) DO UPDATE SET
                    status = excluded.status,
                    last_seen = excluded.last_seen,
                    uptime_ms = excluded.uptime_ms,
                    boot_count = excluded.boot_count,
                    meta_json = excluded.meta_json
                """,
                (device, status, utc_now(), uptime_ms, boot_count, payload),
            )

    def insert_event(self, event_type: str, source: str, payload: dict) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO events (event_type, source, created_at, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (event_type, source, utc_now(), json.dumps(payload)),
            )
            return cursor.lastrowid

    def fetch_recent_events(self, limit: int = 50):
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, event_type, source, created_at, payload_json
                FROM events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            {
                "id": row["id"],
                "event_type": row["event_type"],
                "source": row["source"],
                "created_at": row["created_at"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def fetch_device_status(self):
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT device, status, last_seen, uptime_ms, boot_count, meta_json
                FROM device_status
                ORDER BY device ASC
                """
            ).fetchall()

        return {
            row["device"]: {
                "status": row["status"],
                "last_seen": row["last_seen"],
                "uptime_ms": row["uptime_ms"],
                "boot_count": row["boot_count"],
                "meta": json.loads(row["meta_json"]),
            }
            for row in rows
        }
