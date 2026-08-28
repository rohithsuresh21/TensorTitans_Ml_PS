"""Centralized configuration using environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


ENV = {
    "ENV": os.getenv("ENV", "development"),
    "BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", ""),
    "CHAT_ID": os.getenv("TELEGRAM_CHAT_ID", ""),
    "VIDEO_PATH": os.getenv("VIDEO_PATH", "theft.mp4"),
}

VIDEO_PATH = ENV["VIDEO_PATH"]
BOT_TOKEN = ENV["BOT_TOKEN"]
CHAT_ID = ENV["CHAT_ID"]

SEC_TO_FAINT = _get_int("SEC_TO_FAINT", 30)
FRAME_SKIP = _get_int("FRAME_SKIP", 2)
ESTIMATED_FPS = _get_float("ESTIMATED_FPS", 15)

MODEL_PATH = os.getenv("MODEL_PATH", "yolo11m-pose.pt")
MODEL_CONF = _get_float("MODEL_CONF", 0.25)
MODEL_IMGSZ = _get_int("MODEL_IMGSZ", 480)

MSG_COOLDOWN = _get_int("MSG_COOLDOWN", 30)

# Restricted zone polygon (screen coordinates)
ZONE_POLYGON = [
    (179, 501),
    (471, 707),
    (7, 715),
    (6, 530),
    (124, 483),
]

ALERT_SOUND = os.getenv("ALERT_SOUND", "winsound").lower()  # winsound, beep, none

if not BOT_TOKEN or not CHAT_ID:
    print(
        "WARNING: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in .env. "
        "Telegram alerts will be disabled."
    )