import json
import os
from datetime import datetime


def export_events(events, export_dir: str):
    os.makedirs(export_dir, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%SZ")
    path = os.path.join(export_dir, f"events_{timestamp}.json")

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(events, handle, indent=2)

    return path
