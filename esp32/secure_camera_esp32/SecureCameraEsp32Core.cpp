#include "SecureCameraEsp32.h"

String SecureCameraEsp32::baseUrl() const {
  return "http://" + String(PI_HOST) + ":" + String(PI_PORT);
}

String SecureCameraEsp32::u64ToString(uint64_t value) const {
  char buffer[32];
  snprintf(buffer, sizeof(buffer), "%llu", static_cast<unsigned long long>(value));
  return String(buffer);
}

String SecureCameraEsp32::jsonEscape(const String &value) const {
  String out;
  out.reserve(value.length() + 8);
  for (size_t i = 0; i < value.length(); i++) {
    switch (value[i]) {
      case '\\': out += "\\\\"; break;
      case '"': out += "\\\""; break;
      case '\n': out += "\\n"; break;
      case '\r': out += "\\r"; break;
      case '\t': out += "\\t"; break;
      default: out += value[i]; break;
    }
  }
  return out;
}

String SecureCameraEsp32::resetReasonToString(esp_reset_reason_t reason) const {
  switch (reason) {
    case ESP_RST_POWERON: return "power_on";
    case ESP_RST_EXT: return "external_reset";
    case ESP_RST_SW: return "software_reset";
    case ESP_RST_PANIC: return "panic";
    case ESP_RST_INT_WDT: return "interrupt_watchdog";
    case ESP_RST_TASK_WDT: return "task_watchdog";
    case ESP_RST_WDT: return "watchdog";
    case ESP_RST_DEEPSLEEP: return "deep_sleep";
    case ESP_RST_BROWNOUT: return "brownout";
    case ESP_RST_SDIO: return "sdio";
    default: return "unknown";
  }
}

String SecureCameraEsp32::chipModel() const {
  return String(ESP.getChipModel());
}

uint64_t SecureCameraEsp32::uptimeMs() const {
  return static_cast<uint64_t>(esp_timer_get_time()) / 1000ULL;
}

uint32_t SecureCameraEsp32::largestFreeBlock() const {
#if HAS_HEAP_CAPS
  return heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
#else
  return 0;
#endif
}

int SecureCameraEsp32::wifiChannel() const {
#if HAS_ESP_WIFI
  if (WiFi.status() != WL_CONNECTED) return 0;
  uint8_t primary = 0;
  wifi_second_chan_t second = WIFI_SECOND_CHAN_NONE;
  if (esp_wifi_get_channel(&primary, &second) == ESP_OK) return static_cast<int>(primary);
#endif
  return 0;
}

int SecureCameraEsp32::currentHallRaw() const {
#if HAS_HALL_SENSOR
  return hallRead();
#else
  return 0;
#endif
}

void SecureCameraEsp32::calibrateHallSensor() {
#if HAS_HALL_SENSOR
  long total = 0;
  for (int i = 0; i < 32; i++) {
    total += currentHallRaw();
    delay(20);
  }
  hallBaseline_ = static_cast<int>(total / 32);
  hallBaselineReady_ = true;
#endif
}

String SecureCameraEsp32::buildCommonJsonFields() const {
  const bool connected = WiFi.status() == WL_CONNECTED;
  String json;
  json.reserve(512);
  json += "\"device\":\"" + jsonEscape(String(DEVICE_NAME)) + "\"";
  json += ",\"uptime_ms\":" + u64ToString(uptimeMs());
  json += ",\"boot_count\":" + String(bootCount_);
  json += ",\"free_heap\":" + String(ESP.getFreeHeap());
  json += ",\"min_free_heap\":" + String(ESP.getMinFreeHeap());
  json += ",\"largest_free_block\":" + String(largestFreeBlock());
  json += ",\"rssi\":" + String(connected ? WiFi.RSSI() : 0);
  json += ",\"ip\":\"" + jsonEscape(connected ? WiFi.localIP().toString() : String("")) + "\"";
  json += ",\"firmware\":\"" + jsonEscape(String(FIRMWARE_VERSION)) + "\"";
  json += ",\"sdk_version\":\"" + jsonEscape(String(ESP.getSdkVersion())) + "\"";
  json += ",\"chip_model\":\"" + jsonEscape(chipModel()) + "\"";
  json += ",\"cpu_mhz\":" + String(ESP.getCpuFreqMHz());
  json += ",\"wifi_channel\":" + String(wifiChannel());
  json += ",\"reset_reason\":\"" + jsonEscape(bootResetReason_) + "\"";
  json += ",\"hall_supported\":";
  json += (HAS_HALL_SENSOR ? "true" : "false");
  if (HAS_HALL_SENSOR && hallBaselineReady_) json += ",\"hall_raw\":" + String(currentHallRaw());
  return json;
}

void SecureCameraEsp32::setup() {
  Serial.begin(115200);
  delay(200);
  preferences_.begin("secure-cam", false);
  bootCount_ = preferences_.getUInt("boot_count", 0) + 1;
  preferences_.putUInt("boot_count", bootCount_);
  bootResetReason_ = resetReasonToString(esp_reset_reason());
  queueBootEvents();
  calibrateHallSensor();
  connectWifiIfNeeded();
}

void SecureCameraEsp32::loop() {
  connectWifiIfNeeded();
  syncWifiTransitions();
  flushQueuedEvents();
  sendHeartbeatIfDue();
  runHealthChecksIfDue();
  delay(100);
}
