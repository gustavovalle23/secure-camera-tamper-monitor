def normalize_mega_payload(payload: dict) -> dict:
    return {
        "device": payload.get("device", "mega2560"),
        "uptime_ms": payload.get("uptime_ms"),
        "boot_count": payload.get("boot_count"),
        "counter": payload.get("counter"),
        "port": payload.get("port"),
    }
