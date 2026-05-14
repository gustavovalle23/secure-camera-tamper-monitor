#pragma once

#include <HTTPClient.h>
#include <Preferences.h>
#include <WiFi.h>
#include <esp_system.h>
#include <esp_timer.h>

#if __has_include(<esp_heap_caps.h>)
#include <esp_heap_caps.h>
#define HAS_HEAP_CAPS 1
#else
#define HAS_HEAP_CAPS 0
#endif

#if __has_include(<esp_wifi.h>)
#include <esp_wifi.h>
#define HAS_ESP_WIFI 1
#else
#define HAS_ESP_WIFI 0
#endif

#if defined(CONFIG_IDF_TARGET_ESP32)
#define HAS_HALL_SENSOR 1
#else
#define HAS_HALL_SENSOR 0
#endif

#include "Config.h"

class SecureCameraEsp32 {
 public:
  void setup();
  void loop();

 private:
  Preferences preferences_;
  PendingEvent pendingEvents_[MAX_PENDING_EVENTS];

  size_t pendingHead_ = 0;
  size_t pendingCount_ = 0;
  uint32_t bootCount_ = 0;
  uint32_t heartbeatCounter_ = 0;

  bool wifiWasConnected_ = false;
  bool weakSignalActive_ = false;
  bool lowHeapActive_ = false;
  bool hallAlertActive_ = false;
  String lastKnownIp_;
  String bootResetReason_;

  int hallBaseline_ = 0;
  bool hallBaselineReady_ = false;

  unsigned long lastHeartbeatAt_ = 0;
  unsigned long lastHealthCheckAt_ = 0;
  unsigned long lastWifiAttemptAt_ = 0;

  String baseUrl() const;
  String u64ToString(uint64_t value) const;
  String jsonEscape(const String &value) const;
  String resetReasonToString(esp_reset_reason_t reason) const;
  String chipModel() const;
  uint64_t uptimeMs() const;
  uint32_t largestFreeBlock() const;
  int wifiChannel() const;
  int currentHallRaw() const;

  void calibrateHallSensor();
  String buildCommonJsonFields() const;
  bool postJson(const char *path, const String &body) const;

  void queueEvent(const String &type, const String &severity, const String &message);
  bool postEventNow(const String &type, const String &severity, const String &message);
  void emitEvent(const String &type, const String &severity, const String &message);
  void flushQueuedEvents();
  void queueBootEvents();

  void connectWifiIfNeeded();
  void syncWifiTransitions();
  void sendHeartbeatIfDue();

  void checkSignalHealth();
  void checkHeapHealth();
  void checkHallSensor();
  void runHealthChecksIfDue();
};
