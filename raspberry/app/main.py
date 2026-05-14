import signal
import sys
from app_state import camera
from config import HOST, PORT
from request_handler import RequestHandler, SecureCameraServer

httpd = None


def shutdown_handler(signum, frame):
    del signum, frame
    if httpd is not None:
        httpd.shutdown()
    camera.stop()
    sys.exit(0)


signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)


if __name__ == "__main__":
    httpd = SecureCameraServer((HOST, PORT), RequestHandler)
    print(f"[HTTP] secure camera server listening on http://{HOST}:{PORT}")
    try:
        httpd.serve_forever()
    finally:
        camera.stop()
