#include "SecureCameraEsp32.h"

void SecureCameraEsp32::checkSignalHealth() {
  if (WiFi.status() != WL_CONNECTED) return;
  const int rssi = WiFi.RSSI();
  if (!weakSignalActive_ && rssi <= WEAK_SIGNAL_DBM) {
    weakSignalActive_ = true;
    emitEvent("esp32_wifi_weak_signal", "warning", "WiFi signal weak rssi=" + String(rssi));
  } else if (weakSignalActive_ && rssi >= SIGNAL_RECOVERY_DBM) {
    weakSignalActive_ = false;
    emitEvent("esp32_wifi_signal_restored", "info", "WiFi signal restored rssi=" + String(rssi));
  }
}

void SecureCameraEsp32::checkHeapHealth() {
  const uint32_t freeHeap = ESP.getFreeHeap();
  if (!lowHeapActive_ && freeHeap <= LOW_HEAP_BYTES) {
    lowHeapActive_ = true;
    emitEvent("esp32_heap_low", "warning", "Low heap free_heap=" + String(freeHeap));
  } else if (lowHeapActive_ && freeHeap >= HEAP_RECOVERY_BYTES) {
    lowHeapActive_ = false;
    emitEvent("esp32_heap_recovered", "info", "Heap recovered free_heap=" + String(freeHeap));
  }
}

void SecureCameraEsp32::checkHallSensor() {
#if HAS_HALL_SENSOR
  if (!hallBaselineReady_) return;
  const int raw = currentHallRaw();
  const int delta = abs(raw - hallBaseline_);
  if (!hallAlertActive_ && delta >= HALL_ALERT_DELTA) {
    hallAlertActive_ = true;
    emitEvent("esp32_hall_anomaly", "warning", "Hall delta=" + String(delta) + " raw=" + String(raw) + " baseline=" + String(hallBaseline_));
  } else if (hallAlertActive_ && delta <= HALL_RECOVERY_DELTA) {
    hallAlertActive_ = false;
    emitEvent("esp32_hall_restored", "info", "Hall stabilized raw=" + String(raw) + " baseline=" + String(hallBaseline_));
  }
#endif
}

void SecureCameraEsp32::runHealthChecksIfDue() {
  const unsigned long now = millis();
  if (now - lastHealthCheckAt_ < HEALTH_CHECK_INTERVAL_MS) return;
  lastHealthCheckAt_ = now;
  checkSignalHealth();
  checkHeapHealth();
  checkHallSensor();
}
