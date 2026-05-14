import os
import threading
import time
from datetime import datetime

import cv2


FRAME_WIDTH = int(os.getenv("CAMERA_FRAME_WIDTH", "1280"))
FRAME_HEIGHT = int(os.getenv("CAMERA_FRAME_HEIGHT", "720"))
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))
JPEG_QUALITY = int(os.getenv("CAMERA_JPEG_QUALITY", "95"))
MIN_ZOOM = 1.0
MAX_ZOOM = 4.0
MIN_FOCUS = 0.0
MAX_FOCUS = 1.0


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
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if not ok:
            return None

        return encoded.tobytes()

    def _normalize_zoom(self, zoom):
        try:
            zoom_value = float(zoom)
        except (TypeError, ValueError):
            return MIN_ZOOM

        if zoom_value < MIN_ZOOM:
            return MIN_ZOOM
        if zoom_value > MAX_ZOOM:
            return MAX_ZOOM
        return zoom_value

    def _apply_zoom(self, frame, zoom):
        zoom_value = self._normalize_zoom(zoom)
        if zoom_value <= MIN_ZOOM:
            return frame

        height, width = frame.shape[:2]
        crop_width = max(1, int(round(width / zoom_value)))
        crop_height = max(1, int(round(height / zoom_value)))
        x_start = max(0, (width - crop_width) // 2)
        y_start = max(0, (height - crop_height) // 2)
        cropped = frame[y_start:y_start + crop_height, x_start:x_start + crop_width]
        return cv2.resize(cropped, (width, height), interpolation=cv2.INTER_LANCZOS4)

    def _normalize_focus(self, value):
        try:
            focus_value = float(value)
        except (TypeError, ValueError):
            return 0.5

        if focus_value < MIN_FOCUS:
            return MIN_FOCUS
        if focus_value > MAX_FOCUS:
            return MAX_FOCUS
        return focus_value

    def _apply_viewport(self, frame, zoom, focus_x=0.5, focus_y=0.5):
        zoom_value = self._normalize_zoom(zoom)
        if zoom_value <= MIN_ZOOM:
            return frame

        focus_x_value = self._normalize_focus(focus_x)
        focus_y_value = self._normalize_focus(focus_y)
        height, width = frame.shape[:2]
        crop_width = max(1, int(round(width / zoom_value)))
        crop_height = max(1, int(round(height / zoom_value)))
        max_x_start = max(0, width - crop_width)
        max_y_start = max(0, height - crop_height)
        center_x = int(round(focus_x_value * width))
        center_y = int(round(focus_y_value * height))
        x_start = min(max(0, center_x - crop_width // 2), max_x_start)
        y_start = min(max(0, center_y - crop_height // 2), max_y_start)
        cropped = frame[y_start:y_start + crop_height, x_start:x_start + crop_width]
        return cv2.resize(cropped, (width, height), interpolation=cv2.INTER_LANCZOS4)

    def mjpeg_stream(self, zoom=1.0, focus_x=0.5, focus_y=0.5):
        zoom_value = self._normalize_zoom(zoom)
        focus_x_value = self._normalize_focus(focus_x)
        focus_y_value = self._normalize_focus(focus_y)
        while True:
            ok, frame = self.read_frame()

            if not ok or frame is None:
                time.sleep(0.2)
                continue

            payload = self.encode_frame(
                self._apply_viewport(
                    frame,
                    zoom_value,
                    focus_x=focus_x_value,
                    focus_y=focus_y_value,
                )
            )
            if payload is None:
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + payload + b"\r\n"
            )

    def save_snapshot(self, frame, prefix="snapshot"):
        os.makedirs(self.snapshot_dir, exist_ok=True)
        safe_prefix = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in prefix).strip("_")
        if not safe_prefix:
            safe_prefix = "snapshot"
        filename = f"{safe_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        path = os.path.join(self.snapshot_dir, filename)
        cv2.imwrite(path, frame)
        return path
