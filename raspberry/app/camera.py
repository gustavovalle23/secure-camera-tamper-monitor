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

    def start(self) -> None:
        with self._lock:
            if self._camera is not None:
                return

            camera = cv2.VideoCapture(CAMERA_INDEX)
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
            self._camera = camera
            time.sleep(1)

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
                return False, None

            ok, frame = self._camera.read()
            return ok, frame

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
