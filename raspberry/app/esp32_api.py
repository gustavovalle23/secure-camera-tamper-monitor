def normalize_esp32_payload(payload: dict) -> dict:
    return {
        "device": payload.get("device", "esp32"),
        "uptime_ms": payload.get("uptime_ms"),
        "boot_count": payload.get("boot_count"),
        "free_heap": payload.get("free_heap"),
        "rssi": payload.get("rssi"),
        "ip": payload.get("ip"),
    }
