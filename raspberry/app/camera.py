import os
import threading
import time
from datetime import datetime

import cv2


FRAME_WIDTH = 640
FRAME_HEIGHT = 480
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))


class CameraService:
    def __init__(self, snapshot_dir: str):
        self.snapshot_dir = snapshot_dir
        self._camera = None
        self._lock = threading.Lock()
        self._last_frame_ms = None
        self._last_frame_shape = None
        self._frame_failures = 0
        self._successful_frames = 0
        self._fps_window_started_at = time.time()
        self._fps_window_frames = 0
        self._fps_estimate = 0.0
        self._last_error = None

    def start(self) -> None:
        with self._lock:
            if self._camera is not None:
                return

            camera = cv2.VideoCapture(CAMERA_INDEX)
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
            self._camera = camera
            time.sleep(1)
            if not camera.isOpened():
                self._last_error = "camera_open_failed"

    def stop(self) -> None:
        with self._lock:
            if self._camera is None:
                return

            self._camera.release()
            self._camera = None

    def read_frame(self):
        self.start()

        with self._lock:
            if self._camera is None:
                self._frame_failures += 1
                self._last_error = "camera_not_initialized"
                return False, None

            ok, frame = self._camera.read()
            now = time.time()

            if ok and frame is not None:
                self._last_frame_ms = int(now * 1000)
                self._last_frame_shape = frame.shape
                self._successful_frames += 1
                self._fps_window_frames += 1
                elapsed = now - self._fps_window_started_at
                if elapsed >= 1:
                    self._fps_estimate = self._fps_window_frames / elapsed
                    self._fps_window_started_at = now
                    self._fps_window_frames = 0
                self._last_error = None
            else:
                self._frame_failures += 1
                self._last_error = "frame_read_failed"

            return ok, frame

    def is_available(self):
        self.start()

        with self._lock:
            return self._camera is not None and self._camera.isOpened()

    def get_health(self):
        self.start()

        with self._lock:
            width = FRAME_WIDTH
            height = FRAME_HEIGHT
            if self._last_frame_shape is not None:
                height = int(self._last_frame_shape[0])
                width = int(self._last_frame_shape[1])
            elif self._camera is not None and self._camera.isOpened():
                width = int(self._camera.get(cv2.CAP_PROP_FRAME_WIDTH) or FRAME_WIDTH)
                height = int(self._camera.get(cv2.CAP_PROP_FRAME_HEIGHT) or FRAME_HEIGHT)

            return {
                "ok": True,
                "camera_online": self._camera is not None and self._camera.isOpened(),
                "configured_index": CAMERA_INDEX,
                "width": width,
                "height": height,
                "fps": round(self._fps_estimate, 1),
                "successful_frames": self._successful_frames,
                "frame_failures": self._frame_failures,
                "last_frame_ms": self._last_frame_ms,
                "last_error": self._last_error,
            }

    def encode_frame(self, frame):
        ok, encoded = cv2.imencode(".jpg", frame)
        if not ok:
            return None

        return encoded.tobytes()

    def mjpeg_stream(self):
        while True:
            ok, frame = self.read_frame()

            if not ok or frame is None:
                time.sleep(0.2)
                continue

            payload = self.encode_frame(frame)
            if payload is None:
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + payload + b"\r\n"
            )

    def save_snapshot(self, frame):
        os.makedirs(self.snapshot_dir, exist_ok=True)
        filename = f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        path = os.path.join(self.snapshot_dir, filename)
        cv2.imwrite(path, frame)
        return path
