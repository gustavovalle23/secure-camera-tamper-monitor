# ESP32 firmware

Arduino IDE sketch:

`secure_camera_esp32/secure_camera_esp32.ino`

Open that `.ino` file in the Arduino IDE, update the Wi-Fi and Raspberry Pi settings near the top of the file, then upload it to your ESP32 board.

What it reports:

* periodic heartbeats
* boot and reset reason events
* Wi-Fi connected and disconnected events
* weak Wi-Fi signal and recovery events
* low heap and recovery events
* IP address change events
* optional hall sensor anomaly events on classic ESP32 boards that support `hallRead()`

Raspberry endpoints used:

* `POST /api/esp32/heartbeat`
* `POST /api/esp32/event`
