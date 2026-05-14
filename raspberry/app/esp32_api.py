def normalize_esp32_payload(payload: dict) -> dict:
    return {
        "device": payload.get("device", "esp32"),
        "uptime_ms": payload.get("uptime_ms"),
        "boot_count": payload.get("boot_count"),
        "counter": payload.get("counter"),
        "free_heap": payload.get("free_heap"),
        "min_free_heap": payload.get("min_free_heap"),
        "largest_free_block": payload.get("largest_free_block"),
        "rssi": payload.get("rssi"),
        "ip": payload.get("ip"),
        "firmware": payload.get("firmware"),
        "sdk_version": payload.get("sdk_version"),
        "chip_model": payload.get("chip_model"),
        "cpu_mhz": payload.get("cpu_mhz"),
        "wifi_channel": payload.get("wifi_channel"),
        "reset_reason": payload.get("reset_reason"),
        "hall_raw": payload.get("hall_raw"),
        "hall_supported": payload.get("hall_supported"),
    }


def normalize_esp32_event(payload: dict) -> dict:
    normalized = normalize_esp32_payload(payload)
    normalized["type"] = str(payload.get("type", "esp32_event"))
    normalized["severity"] = str(payload.get("severity", "info"))
    normalized["message"] = str(payload.get("message", normalized["type"].replace("_", " ")))
    return normalized
