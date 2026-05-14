#include "SecureCameraEsp32.h"

bool SecureCameraEsp32::postJson(const char *path, const String &body) const {
  if (WiFi.status() != WL_CONNECTED) return false;
  WiFiClient client;
  HTTPClient http;
  http.setTimeout(4000);
  if (!http.begin(client, baseUrl() + String(path))) return false;
  http.addHeader("Content-Type", "application/json");
  const int statusCode = http.POST(body);
  http.end();
  return statusCode >= 200 && statusCode < 300;
}

void SecureCameraEsp32::queueEvent(const String &type, const String &severity, const String &message) {
  if (pendingCount_ == MAX_PENDING_EVENTS) {
    pendingHead_ = (pendingHead_ + 1) % MAX_PENDING_EVENTS;
    pendingCount_--;
  }
  const size_t index = (pendingHead_ + pendingCount_) % MAX_PENDING_EVENTS;
  pendingEvents_[index] = {type, severity, message};
  pendingCount_++;
}

bool SecureCameraEsp32::postEventNow(const String &type, const String &severity, const String &message) {
  String body = "{";
  body += buildCommonJsonFields();
  body += ",\"type\":\"" + jsonEscape(type) + "\"";
  body += ",\"severity\":\"" + jsonEscape(severity) + "\"";
  body += ",\"message\":\"" + jsonEscape(message) + "\"}";
  return postJson("/api/esp32/event", body);
}

void SecureCameraEsp32::emitEvent(const String &type, const String &severity, const String &message) {
  if (!postEventNow(type, severity, message)) queueEvent(type, severity, message);
}

void SecureCameraEsp32::flushQueuedEvents() {
  while (pendingCount_ > 0 && WiFi.status() == WL_CONNECTED) {
    PendingEvent &event = pendingEvents_[pendingHead_];
    if (!postEventNow(event.type, event.severity, event.message)) return;
    pendingHead_ = (pendingHead_ + 1) % MAX_PENDING_EVENTS;
    pendingCount_--;
  }
}

void SecureCameraEsp32::queueBootEvents() {
  queueEvent("esp32_boot", "info", "boot_count=" + String(bootCount_) + " reset=" + bootResetReason_);
  if (bootResetReason_ == "brownout") {
    queueEvent("esp32_brownout_reset", "alert", "ESP32 restarted after brownout");
  } else if (bootResetReason_ == "panic") {
    queueEvent("esp32_panic_reset", "critical", "ESP32 restarted after panic");
  } else if (bootResetReason_ == "watchdog" || bootResetReason_ == "interrupt_watchdog" || bootResetReason_ == "task_watchdog") {
    queueEvent("esp32_watchdog_reset", "critical", "ESP32 restarted after watchdog reset");
  }
}

void SecureCameraEsp32::connectWifiIfNeeded() {
  if (WiFi.status() == WL_CONNECTED) return;
  const unsigned long now = millis();
  if (now - lastWifiAttemptAt_ < WIFI_RETRY_INTERVAL_MS) return;
  lastWifiAttemptAt_ = now;
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void SecureCameraEsp32::syncWifiTransitions() {
  const bool connected = WiFi.status() == WL_CONNECTED;
  const String currentIp = connected ? WiFi.localIP().toString() : String("");

  if (connected && !wifiWasConnected_) {
    wifiWasConnected_ = true;
    flushQueuedEvents();
    emitEvent("esp32_wifi_connected", "info", "WiFi connected ip=" + currentIp + " rssi=" + String(WiFi.RSSI()));
    if (lastKnownIp_.length() > 0 && lastKnownIp_ != currentIp) emitEvent("esp32_ip_changed", "info", "IP changed to " + currentIp);
    lastKnownIp_ = currentIp;
    return;
  }

  if (!connected && wifiWasConnected_) {
    wifiWasConnected_ = false;
    weakSignalActive_ = false;
    queueEvent("esp32_wifi_disconnected", "warning", "WiFi disconnected from access point");
    lastKnownIp_ = "";
    return;
  }

  if (connected && wifiWasConnected_ && currentIp != lastKnownIp_) {
    emitEvent("esp32_ip_changed", "info", "IP changed to " + currentIp);
    lastKnownIp_ = currentIp;
  }
}

void SecureCameraEsp32::sendHeartbeatIfDue() {
  const unsigned long now = millis();
  if (now - lastHeartbeatAt_ < HEARTBEAT_INTERVAL_MS) return;
  lastHeartbeatAt_ = now;
  if (WiFi.status() != WL_CONNECTED) return;

  heartbeatCounter_++;
  String body = "{";
  body += buildCommonJsonFields();
  body += ",\"counter\":" + String(heartbeatCounter_) + "}";
  postJson("/api/esp32/heartbeat", body);
}
