"""Environment-driven configuration with safe defaults.

Never hardcode secrets here - put them in .env (gitignored).
"""

import os
import secrets

from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


RTSP_PLACEHOLDER = "rtsp://username:password@192.168.1.100:554/stream1"
RTSP_STREAM_URL = os.getenv("RTSP_STREAM_URL", RTSP_PLACEHOLDER)
VIDEO_PATH = os.getenv("VIDEO_PATH", "theft.mp4")
STREAM_SOURCE = (
    RTSP_STREAM_URL
    if RTSP_STREAM_URL and RTSP_STREAM_URL.startswith("rtsp://") and RTSP_STREAM_URL != RTSP_PLACEHOLDER
    else VIDEO_PATH
)

MODELS_DIR = os.getenv("MODELS_DIR", "")
MODEL_PATH = os.getenv("MODEL_PATH", "yolo11m-pose.pt")
MODEL_ENGINE = os.getenv("MODEL_ENGINE", "yolo11m-pose.engine")
if MODELS_DIR:
    MODEL_PATH = (
        MODEL_PATH if os.path.isabs(MODEL_PATH) else os.path.join(MODELS_DIR, MODEL_PATH)
    )
    MODEL_ENGINE = (
        MODEL_ENGINE if os.path.isabs(MODEL_ENGINE) else os.path.join(MODELS_DIR, MODEL_ENGINE)
    )

MODEL_IMGSZ = int(os.getenv("MODEL_IMGSZ", "480"))
MODEL_CONF = float(os.getenv("MODEL_CONF", "0.25"))
FRAME_SKIP = int(os.getenv("FRAME_SKIP", "2"))
ESTIMATED_FPS = float(os.getenv("ESTIMATED_FPS", "15"))
SEC_TO_FAINT = int(os.getenv("SEC_TO_FAINT", "30"))
MSG_COOLDOWN = int(os.getenv("MSG_COOLDOWN", "30"))

PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")

# Runtime environment: "dev" or "prod". Gates hardening defaults only.
APP_ENV = os.getenv("APP_ENV", "dev").strip().lower()

# Secret used to sign/verify session tokens at rest. Auto-generated per boot in
# dev; set a FIXED value in production so sessions survive restarts.
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    if APP_ENV == "prod":
        raise RuntimeError("[config] SECRET_KEY is required in production - set it in .env")

SESSION_MAX_AGE = int(os.getenv("SESSION_MAX_AGE", str(60 * 60 * 12)))  # 12h
COOKIE_SECURE = _get_bool("COOKIE_SECURE", APP_ENV == "prod")  # HTTPS-only cookie

# Set TRUSTED_PROXY=1 when running behind a reverse proxy so protocol/host is
# taken from X-Forwarded-* headers and forwarded IPs are accepted by uvicorn.
TRUSTED_PROXY = _get_bool("TRUSTED_PROXY", False)

# Comma-separated allowlist of Host headers; empty = accept any (local/dev).
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]

LOG_LEVEL = os.getenv("LOG_LEVEL", "info").strip().lower()

# Set RUN_ENGINE=0 for a "control-shell" deploy (Vercel/Render) that has no
# camera/GPU: the API, auth, zones, settings and evidence still work, and the
# live stream/snapshot return an offline placeholder.
RUN_ENGINE = _get_bool("RUN_ENGINE", True)

# Comma-separated list of allowed CORS origins (default: same-origin via proxy).
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "sentineliq.db"))

# Runtime data directories (uploaded videos + evidence images). Can be pointed
# at a mounted volume in production.
EVIDENCE_DIR = os.getenv(
    "EVIDENCE_DIR", os.path.join(BASE_DIR, "evidence")
)
MEDIA_DIR = os.getenv(
    "MEDIA_DIR", os.path.join(BASE_DIR, "media")
)

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