"""Environment-driven configuration with safe defaults.

Never hardcode secrets here - put them in .env (gitignored).
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


RTSP_PLACEHOLDER = "rtsp://username:password@192.168.1.100:554/stream1"
RTSP_STREAM_URL = os.getenv("RTSP_STREAM_URL", RTSP_PLACEHOLDER)
VIDEO_PATH = os.getenv("VIDEO_PATH", "theft.mp4")
STREAM_SOURCE = (
    RTSP_STREAM_URL
    if RTSP_STREAM_URL and RTSP_STREAM_URL.startswith("rtsp://") and RTSP_STREAM_URL != RTSP_PLACEHOLDER
    else VIDEO_PATH
)

MODEL_PATH = os.getenv("MODEL_PATH", "yolo11m-pose.pt")
MODEL_ENGINE = os.getenv("MODEL_ENGINE", "yolo11m-pose.engine")

MODEL_IMGSZ = int(os.getenv("MODEL_IMGSZ", "480"))
MODEL_CONF = float(os.getenv("MODEL_CONF", "0.25"))
FRAME_SKIP = int(os.getenv("FRAME_SKIP", "2"))
ESTIMATED_FPS = float(os.getenv("ESTIMATED_FPS", "15"))
SEC_TO_FAINT = int(os.getenv("SEC_TO_FAINT", "30"))
MSG_COOLDOWN = int(os.getenv("MSG_COOLDOWN", "30"))

PORT = int(os.getenv("PORT", "8000"))
DATABASE_PATH = os.getenv("DATABASE_PATH", "sentineliq.db")

DEFAULT_ADMIN_USER = os.getenv("DEFAULT_ADMIN_USER", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

EMERGENCY_NUMBER = os.getenv("EMERGENCY_NUMBER", "100")

# Default restricted zone (screen coordinates) seeding the first saved zone.
DEFAULT_ZONE = [
    [179, 501],
    [471, 707],
    [7, 715],
    [6, 530],
    [124, 483],
]