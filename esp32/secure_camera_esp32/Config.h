#pragma once

#include <Arduino.h>

constexpr const char *WIFI_SSID = "YOUR_WIFI_SSID";
constexpr const char *WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
constexpr const char *PI_HOST = "192.168.1.50";
constexpr uint16_t PI_PORT = 5000;
constexpr const char *DEVICE_NAME = "esp32";
constexpr const char *FIRMWARE_VERSION = "0.1.0";

constexpr unsigned long HEARTBEAT_INTERVAL_MS = 5000;
constexpr unsigned long HEALTH_CHECK_INTERVAL_MS = 10000;
constexpr unsigned long WIFI_RETRY_INTERVAL_MS = 8000;

constexpr int WEAK_SIGNAL_DBM = -75;
constexpr int SIGNAL_RECOVERY_DBM = -67;
constexpr uint32_t LOW_HEAP_BYTES = 40000;
constexpr uint32_t HEAP_RECOVERY_BYTES = 55000;
constexpr int HALL_ALERT_DELTA = 120;
constexpr int HALL_RECOVERY_DELTA = 80;
constexpr size_t MAX_PENDING_EVENTS = 16;

struct PendingEvent {
  String type;
  String severity;
  String message;
};
