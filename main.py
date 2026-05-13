import cv2
import os
import time
from datetime import datetime

SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), "static", "snapshots")
MOTION_MIN_AREA = 5000
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
COOLDOWN_SECONDS = 5

os.makedirs(SNAPSHOT_DIR, exist_ok=True)


class CameraSource:
    def __init__(self):
        self.camera = None

    def start(self):
        self.camera = cv2.VideoCapture(0)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        time.sleep(2)

    def read(self):
        ok, frame = self.camera.read()
        return ok, frame

    def stop(self):
        if self.camera is None:
            return

        self.camera.release()


def timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def save_snapshot(frame):
    filename = f"motion_{timestamp()}.jpg"
    path = os.path.join(SNAPSHOT_DIR, filename)
    cv2.imwrite(path, frame)
    return path


def preprocess(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (21, 21), 0)
    return blur


def detect_motion(previous_frame, current_frame):
    delta = cv2.absdiff(previous_frame, current_frame)
    threshold = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)[1]
    threshold = cv2.dilate(threshold, None, iterations=2)
    contours, _ = cv2.findContours(threshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    largest_area = 0

    for contour in contours:
        area = cv2.contourArea(contour)
        if area > largest_area:
            largest_area = area

    return largest_area >= MOTION_MIN_AREA, largest_area


def main():
    camera = CameraSource()
    camera.start()

    previous_processed = None
    last_motion_time = 0

    print("[CAMERA] motion detector started")

    try:
        while True:
            ok, frame = camera.read()

            if not ok or frame is None:
                print("[CAMERA] frame read failed")
                time.sleep(1)
                continue

            processed = preprocess(frame)

            if previous_processed is None:
                previous_processed = processed
                continue

            motion_detected, area = detect_motion(previous_processed, processed)
            now = time.time()

            if motion_detected and now - last_motion_time >= COOLDOWN_SECONDS:
                last_motion_time = now
                snapshot_path = save_snapshot(frame)
                print(f"[CAMERA] motion detected area={area} snapshot={snapshot_path}")

            previous_processed = processed
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("[CAMERA] stopping")

    finally:
        camera.stop()


if __name__ == "__main__":
    main()
