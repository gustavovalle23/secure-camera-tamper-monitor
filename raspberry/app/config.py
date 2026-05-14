import os


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
