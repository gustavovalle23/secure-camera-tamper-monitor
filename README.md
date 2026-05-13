**Secure Camera Tamper Monitor**

## Main idea

The Raspberry Pi watches the camera feed and monitors the ESP32 and Arduino Mega. The system detects:

* Motion in front of the camera
* Camera obstruction
* Camera disconnection
* ESP32 offline
* ESP32 reboot
* Weak ESP32 Wi-Fi signal
* Mega offline
* Mega reboot
* Pi reboot
* Log tampering
* Failed dashboard login attempts

The Arduino Mega sends a heartbeat to the Raspberry Pi over USB serial and displays system status on the LCD 1602.

The ESP32 sends a heartbeat to the Raspberry Pi over Wi-Fi.

The Raspberry Pi stores secure logs, serves a local dashboard, and triggers alerts.

---

# High-level architecture

```text
                    ┌────────────────────────┐
                    │   Browser Dashboard    │
                    │  Phone / Laptop / LAN  │
                    └───────────▲────────────┘
                                │
                                │ HTTP/HTTPS + login
                                │
┌──────────────┐        ┌───────┴────────────┐
│ Pi Camera    │───────▶│    Raspberry Pi    │
└──────────────┘        │                    │
                        │ - Camera detection │
┌──────────────┐        │ - Tamper detection │
│ ESP32        │───────▶│ - Secure logs      │
│ Wi-Fi node   │ HTTP   │ - Dashboard        │
└──────────────┘        │ - Alerts           │
                        │ - Health monitor   │
┌──────────────┐        │                    │
│ Mega 2560    │◀──────▶│ - Serial control   │
│ + LCD 1602   │ USB    └────────────────────┘
└──────────────┘
```

---

# Device responsibilities

## 1. Raspberry Pi

The Raspberry Pi is the main controller.

It handles:

* Camera access
* Motion detection
* Camera obstruction detection
* Camera offline detection
* ESP32 heartbeat endpoint
* Mega serial communication
* Local web dashboard
* Event logging
* Log integrity checks
* Alerting
* Health status
* Arm/disarm state

The Pi is the “server” of the system.

---

## 2. Camera

The camera is used for two main things:

### A. Motion detection

The Pi compares camera frames to detect movement.

Example events:

```text
motion_detected
snapshot_saved
motion_ended
```

This does not require AI at first. You can use OpenCV frame difference.

Later, you can upgrade to:

* Person detection
* Vehicle detection
* Face blurring
* Object tracking
* Edge AI with TensorFlow Lite

### B. Camera tamper detection

The Pi checks whether the camera is being interfered with.

Camera tamper examples:

| Tamper type          | Detection method            |
| -------------------- | --------------------------- |
| Camera unplugged     | Frame read fails            |
| Camera covered       | Frame becomes very dark     |
| Camera blinded       | Frame becomes very bright   |
| Lens blocked/blurred | Image sharpness drops       |
| Camera frozen        | Same frame repeats too long |

This is one of the strongest parts of the project because you do not need extra sensors to detect basic camera tampering.

---

## 3. ESP32

The ESP32 acts as a **wireless integrity node**.

It does not need sensors. Its job is to prove that a remote wireless device is alive and connected.

It sends heartbeat messages to the Pi every few seconds.

Example ESP32 heartbeat:

```json
{
  "device": "esp32",
  "uptime_ms": 185000,
  "boot_count": 3,
  "free_heap": 192000,
  "rssi": -52
}
```

The Raspberry Pi can detect:

| Event                       | Meaning                         |
| --------------------------- | ------------------------------- |
| ESP32 heartbeat received    | ESP32 online                    |
| No heartbeat for 15 seconds | ESP32 offline                   |
| Uptime resets               | ESP32 rebooted                  |
| RSSI drops sharply          | Possible movement/interference  |
| Malformed heartbeat         | Possible bad firmware or attack |
| Wrong device token          | Unauthorized device attempt     |

The ESP32 gives you experience with:

* Wi-Fi device monitoring
* HTTP or MQTT communication
* Device identity
* Health reporting
* Heartbeat timeout logic
* Wireless reliability

---

## 4. Arduino Mega 2560

The Mega acts as a **wired hardware status controller**.

It connects to the Pi through USB serial.

Its job is to:

* Send heartbeat messages to the Pi
* Receive system state from the Pi
* Display that state on the LCD 1602
* Show alarm/armed/offline status
* Blink onboard LED depending on status
* Report Mega uptime
* Report if it rebooted

Example Mega heartbeat:

```json
{
  "device": "mega2560",
  "uptime_ms": 92000,
  "counter": 46
}
```

The Pi detects:

| Event                   | Meaning                       |
| ----------------------- | ----------------------------- |
| Mega heartbeat received | Mega online                   |
| No serial heartbeat     | Mega offline                  |
| Uptime reset            | Mega rebooted                 |
| Counter reset           | Mega rebooted or serial issue |
| Invalid serial data     | Communication error           |

---

## 5. LCD 1602

The LCD becomes your **local hardware status screen**.

It can show system status even if you are not looking at the web dashboard.

Because it is a 16x2 display, you need short rotating messages.

Example screens:

```text
ARMED   CAM:OK
E:OK M:OK LOG:OK
```

```text
MOTION DETECTED
SNAPSHOT SAVED
```

```text
CAMERA TAMPER
REASON: DARK
```

```text
ESP32 OFFLINE
LAST: 28s AGO
```

```text
MEGA ONLINE
UP: 00:14:22
```

```text
LOG INTEGRITY
STATUS: OK
```

The Pi sends status messages to the Mega, and the Mega displays them on the LCD.

---

# Important design choice

The LCD should not make decisions.

The Mega should not be the main security brain.

The Raspberry Pi should decide the global state, then tell the Mega what to display.

That makes the architecture clean:

```text
Pi decides.
Mega displays.
ESP32 reports.
Camera observes.
```

---

# Full feature list

## Camera features

* Live frame capture
* Motion detection
* Snapshot on motion
* Camera offline detection
* Camera obstruction detection
* Brightness monitoring
* Blur/sharpness monitoring
* Frozen-frame detection
* Camera health status

## ESP32 features

* Wi-Fi heartbeat
* Uptime reporting
* Free memory reporting
* RSSI reporting
* Boot count reporting
* Offline detection
* Reboot detection
* Optional onboard LED status

## Mega 2560 features

* USB serial heartbeat
* Uptime reporting
* Counter reporting
* Reboot detection
* Receives status from Pi
* Displays status on LCD
* Onboard LED alarm/status indication

## LCD 1602 features

* Shows armed/disarmed state
* Shows camera status
* Shows ESP32 status
* Shows Mega status
* Shows log integrity
* Shows motion alerts
* Shows tamper alerts
* Shows offline warnings
* Rotates through status screens

## Raspberry Pi dashboard features

Pages:

```text
/
Dashboard

/events
Event timeline

/health
Device health

/settings
Arm/disarm and config

/api/status
JSON status

/api/esp32/heartbeat
ESP32 heartbeat endpoint
```

Dashboard should show:

* System armed/disarmed
* Latest camera image
* Last motion event
* Camera status
* ESP32 status
* Mega status
* Log integrity
* Recent alerts
* Pi uptime
* CPU temperature
* Disk usage

## Logging features

Use JSONL logs.

Each line is one event.

Example:

```json
{
  "timestamp": "2026-05-13T21:30:12",
  "source": "camera",
  "event": "motion_detected",
  "details": {
    "motion_score": 1842,
    "snapshot": "snapshots/2026-05-13_21-30-12.jpg"
  },
  "previous_hash": "abc123...",
  "hash": "def456..."
}
```

Events to log:

* System started
* System armed
* System disarmed
* Motion detected
* Camera offline
* Camera restored
* Camera obstruction detected
* ESP32 heartbeat received
* ESP32 offline
* ESP32 restored
* ESP32 reboot detected
* Mega heartbeat received
* Mega offline
* Mega restored
* Mega reboot detected
* Dashboard login success
* Dashboard login failure
* Alert sent
* Log integrity failure

## Security features

* Dashboard login
* Password stored as hash, not plain text
* SSH key-only login on Pi
* Firewall enabled on Pi
* ESP32 shared token or signed heartbeat
* Logs hash-chained
* Secrets stored in `.env`, not GitHub
* HTTPS for dashboard later
* Rate limiting for login later
* Systemd service auto-start
* Health checks
* Safe defaults after reboot

---

# How the system behaves

## Normal state

```text
System armed.
Camera online.
ESP32 online.
Mega online.
Logs OK.
No recent motion.
```

LCD could show:

```text
ARMED   CAM:OK
ESP:OK MEGA:OK
```

Dashboard could show:

```text
Status: Armed
Camera: Online
ESP32: Online, RSSI -51 dBm
Mega: Online, uptime 00:07:42
Logs: Integrity OK
Last event: heartbeat
```

---

## Motion event

When someone moves in front of the camera:

```text
Camera detects frame difference.
Pi saves snapshot.
Pi logs motion_detected.
Pi updates dashboard.
Pi sends LCD alert to Mega.
Pi sends optional email/Telegram/Discord alert.
```

LCD:

```text
MOTION DETECTED
SNAPSHOT SAVED
```

Log:

```json
{
  "source": "camera",
  "event": "motion_detected",
  "details": {
    "snapshot": "snapshots/motion_001.jpg"
  }
}
```

---

## Camera covered

When someone covers the camera with a hand:

```text
Frame brightness becomes very low.
Pi classifies camera as obstructed.
Pi logs camera_tamper.
Pi updates dashboard.
Pi sends LCD alert.
```

LCD:

```text
CAMERA TAMPER
TOO DARK
```

Dashboard:

```text
Camera: Obstructed
Reason: Too dark
Last good frame: 14 seconds ago
```

---

## ESP32 unplugged or powered off

```text
Pi stops receiving ESP32 heartbeat.
After timeout, Pi marks ESP32 offline.
Pi logs esp32_offline.
Pi sends LCD warning.
```

LCD:

```text
ESP32 OFFLINE
LAST 22s AGO
```

Health page:

```text
ESP32: Offline
Last heartbeat: 22 seconds ago
Last RSSI: -53 dBm
Last uptime: 00:04:31
```

---

## ESP32 reset

```text
ESP32 heartbeat returns with smaller uptime.
Pi detects uptime reset.
Pi logs esp32_reboot_detected.
Pi updates dashboard.
```

LCD:

```text
ESP32 REBOOTED
CHECK NODE
```

---

## Mega unplugged

```text
Pi serial connection fails or heartbeat stops.
Pi marks Mega offline.
Pi logs mega_offline.
Dashboard shows Mega offline.
```

LCD obviously cannot update if the Mega is unplugged, which is fine.

Dashboard:

```text
Mega 2560: Offline
Last heartbeat: 18 seconds ago
```

---

## Mega reset

```text
Mega heartbeat returns with uptime near zero.
Pi detects Mega reboot.
Pi logs mega_reboot_detected.
Pi sends current system state back to Mega.
LCD resumes showing status.
```

---

## Log tampering

If someone edits the log file:

```text
Pi verifies hash chain.
Hash mismatch is detected.
Pi logs integrity failure to a new log file or alert channel.
Dashboard shows log integrity warning.
LCD shows warning.
```

LCD:

```text
LOG WARNING
CHECK FILES
```

---

# Wiring

## Raspberry Pi

| Connection         | Use                               |
| ------------------ | --------------------------------- |
| Camera port or USB | Camera                            |
| USB cable to Mega  | Serial communication              |
| Wi-Fi/Ethernet     | Dashboard and ESP32 communication |
| Power              | Stable Pi power supply            |

## Mega 2560 to LCD 1602

There are two common LCD 1602 types.

### Option A: LCD 1602 with I2C backpack

This is easier and recommended.

Connections:

| LCD I2C Pin | Mega 2560 Pin |
| ----------- | ------------- |
| GND         | GND           |
| VCC         | 5V            |
| SDA         | SDA pin 20    |
| SCL         | SCL pin 21    |

Libraries:

```text
LiquidCrystal_I2C
```

### Option B: LCD 1602 without I2C backpack

Uses more wires.

Typical wiring:

| LCD Pin | Mega Pin                 |
| ------- | ------------------------ |
| VSS     | GND                      |
| VDD     | 5V                       |
| VO      | Potentiometer middle pin |
| RS      | D7                       |
| RW      | GND                      |
| E       | D8                       |
| D4      | D9                       |
| D5      | D10                      |
| D6      | D11                      |
| D7      | D12                      |
| A       | 5V through resistor      |
| K       | GND                      |

Libraries:

```text
LiquidCrystal
```

If your LCD has only 4 pins, it is I2C.
If it has 16 pins, it is probably parallel unless it has a backpack attached.

---

# Communication protocols

## ESP32 to Pi

Use HTTP first because it is simple.

ESP32 sends:

```http
POST /api/esp32/heartbeat
```

Body:

```json
{
  "device": "esp32",
  "token": "shared_secret_here",
  "uptime_ms": 120000,
  "free_heap": 192344,
  "rssi": -49
}
```

Pi replies:

```json
{
  "ok": true,
  "armed": true,
  "status": "normal"
}
```

Later, you can upgrade to MQTT.

## Mega to Pi

Mega sends JSON over serial every 2 seconds:

```json
{"device":"mega2560","uptime_ms":124000,"counter":62}
```

Pi sends display commands to Mega:

```json
{"cmd":"display","line1":"ARMED   CAM:OK","line2":"ESP:OK MEGA:OK"}
```

Pi sends alarm/status command:

```json
{"cmd":"status","armed":true,"alarm":false}
```

Mega displays the received message.

---

# Recommended build phases

## Phase 1: Mega + LCD local display

Goal:

```text
Mega shows system boot message and heartbeat count.
```

LCD:

```text
SEC MONITOR
MEGA BOOTING
```

Then:

```text
MEGA ONLINE
COUNT: 00042
```

You learn:

* LCD wiring
* Arduino display code
* Timing with `millis()`
* Serial JSON output

---

## Phase 2: Pi reads Mega heartbeat

Goal:

```text
Pi receives Mega heartbeat over USB serial.
```

Pi should print:

```text
Mega online, uptime 123000 ms, counter 61
```

Then unplug the Mega and confirm:

```text
Mega offline
```

You learn:

* `pyserial`
* Serial parsing
* Timeouts
* Device health states

---

## Phase 3: Pi sends LCD status to Mega

Goal:

```text
Pi sends dashboard status to the LCD.
```

Example:

```json
{"cmd":"display","line1":"PI CONNECTED","line2":"CAM WAITING"}
```

LCD:

```text
PI CONNECTED
CAM WAITING
```

You learn:

* Two-way serial communication
* Command parsing
* Display state

---

## Phase 4: Camera motion detection

Goal:

```text
Pi detects motion and saves snapshots.
```

Events:

```text
motion_detected
snapshot_saved
```

LCD:

```text
MOTION DETECTED
SNAPSHOT SAVED
```

You learn:

* OpenCV
* Frame differencing
* Image saving
* Event generation

---

## Phase 5: Camera tamper detection

Goal:

```text
Pi detects if camera is blocked, blinded, or disconnected.
```

Tamper conditions:

```text
brightness < threshold → too dark
brightness > threshold → too bright
sharpness < threshold → too blurry/covered
frame read failure → camera offline
```

LCD:

```text
CAMERA TAMPER
TOO DARK
```

You learn:

* Image metrics
* Health monitoring
* False positive tuning

---

## Phase 6: ESP32 heartbeat

Goal:

```text
ESP32 sends heartbeat to Pi over Wi-Fi.
```

Pi shows:

```text
ESP32 online
RSSI: -52 dBm
Uptime: 00:02:31
```

LCD rotates:

```text
ESP32 ONLINE
RSSI: -52
```

You learn:

* ESP32 Wi-Fi
* HTTP POST
* Device token
* Wireless health monitoring

---

## Phase 7: Dashboard

Goal:

Build the web dashboard.

Pages:

```text
/
Main dashboard

/events
Recent events

/health
System health

/settings
Arm/disarm
```

Main dashboard:

```text
SECURE CAMERA TAMPER MONITOR

System: Armed
Camera: Online
ESP32: Online
Mega: Online
Logs: OK

Last event: motion_detected
Last snapshot: View image
```

---

## Phase 8: Secure logs

Goal:

Every event is written to a tamper-evident log.

Use hash chaining:

```text
hash = SHA256(previous_hash + event_data)
```

If an old log line is edited, verification fails.

This is a great security feature for your portfolio.

---

## Phase 9: Alerts

Start with dashboard alerts.

Then add one external alert method:

* Telegram bot
* Discord webhook
* Email

Example alert:

```text
ALERT: Camera tamper detected.
Reason: too_dark
Time: 2026-05-13 21:44:02
System: Armed
```

---

# Repo structure

```text
secure-camera-tamper-monitor/
├── README.md
├── docs/
│   ├── architecture.md
│   ├── wiring.md
│   ├── threat-model.md
│   ├── test-report.md
│   ├── security-checklist.md
│   └── demo-video-plan.md
├── pi/
│   ├── app/
│   │   ├── main.py
│   │   ├── camera.py
│   │   ├── mega_serial.py
│   │   ├── esp32_api.py
│   │   ├── secure_log.py
│   │   ├── health.py
│   │   ├── alerts.py
│   │   └── config.py
│   ├── templates/
│   │   ├── dashboard.html
│   │   ├── events.html
│   │   └── health.html
│   ├── static/
│   │   └── snapshots/
│   ├── requirements.txt
│   └── systemd/
│       └── secure-camera-monitor.service
├── mega2560/
│   └── mega_lcd_console/
│       └── mega_lcd_console.ino
├── esp32/
│   └── esp32_heartbeat/
│       └── esp32_heartbeat.ino
└── diagrams/
    └── architecture.png
```

---

# Specific features by difficulty

## Beginner features

Build these first:

* Mega LCD boot screen
* Mega heartbeat over serial
* Pi reads Mega heartbeat
* Camera frame capture
* Motion detection
* Snapshot saving
* Simple dashboard

## Intermediate features

Then add:

* ESP32 Wi-Fi heartbeat
* Device offline detection
* Camera obstruction detection
* LCD rotating status messages
* Arm/disarm mode
* Event timeline
* Health page

## Advanced features

Add later:

* Dashboard login
* HTTPS
* Encrypted logs
* Hash-chain log verification
* Telegram/Discord/email alerts
* systemd auto-start
* SSH hardening
* AI person detection
* Signed ESP32 heartbeat
* Watchdog timers
* Exportable incident report

---

# What counts as “tamper” in this project

Since you do not have physical tamper switches, tamper is defined as **loss of trust in a device or sensor**.

Tamper events:

| Event                 | Why it matters                        |
| --------------------- | ------------------------------------- |
| Camera covered        | Someone may be hiding activity        |
| Camera disconnected   | Monitoring disabled                   |
| Camera frozen         | Feed may be broken or spoofed         |
| ESP32 offline         | Wireless node disabled                |
| ESP32 rebooted        | Device may have lost power            |
| Mega offline          | Hardware console/control disconnected |
| Mega rebooted         | Wired node reset                      |
| Logs modified         | Evidence integrity compromised        |
| Wrong dashboard login | Possible access attempt               |

This is a good security mindset: defensive systems do not only detect intruders, they also detect when the monitoring system itself becomes unreliable.

---

# Final demo scenario

For your demo video:

1. Show the hardware:

   * Pi
   * camera
   * ESP32
   * Mega
   * LCD 1602

2. Show the LCD booting:

```text
SEC MONITOR
BOOTING...
```

3. Show the dashboard:

```text
System armed
Camera online
ESP32 online
Mega online
Logs OK
```

4. Move in front of the camera.

Expected:

```text
Motion detected
Snapshot saved
Event logged
LCD updates
```

5. Cover the camera.

Expected:

```text
Camera tamper: too dark
Alert generated
LCD warning
```

6. Reset the ESP32.

Expected:

```text
ESP32 reboot detected
Health page updates
```

7. Unplug the ESP32.

Expected:

```text
ESP32 offline
LCD warning
```

8. Reset the Mega.

Expected:

```text
Mega reboot detected
Pi resends display state
```

9. Edit the log file manually.

Expected:

```text
Log integrity failure
Dashboard warning
```

10. Show GitHub docs:

* Threat model
* Test report
* Security checklist

---

# Why this project is valuable

This project teaches real defensive-tech concepts:

* Embedded systems
* Secure device monitoring
* Camera-based detection
* Edge computing
* Hardware/software integration
* Device health monitoring
* Tamper-evident logs
* Local dashboard design
* Incident alerting
* System reliability
* Threat modeling
* Test documentation

