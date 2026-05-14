from camera import CameraService
from config import DATABASE_PATH, SECURE_LOG_PATH, SNAPSHOT_DIR
from database import Database
from secure_log import SecureEventLog


database = Database(DATABASE_PATH)
database.init()

secure_log = SecureEventLog(SECURE_LOG_PATH)
camera = CameraService(SNAPSHOT_DIR)
