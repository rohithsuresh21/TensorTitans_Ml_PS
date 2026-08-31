"""SentinelIQ FastAPI web server."""

import os
import shutil
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Request, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config
from app import database as db
from app.database import get_user_by_token
from app.engine import DetectionEngine, MEDIA_DIR, EVIDENCE_DIR
from app.telegram_bot import TelegramAlertBot

BASE_DIR = Path(__file__).resolve().parent

engine = DetectionEngine()
bot = TelegramAlertBot(engine=engine)
engine.alert_handler = bot.submit

# Frame shown by /api/snapshot and /api/stream when the CV engine is disabled
# or not running on this host (remote "control-shell" deployments).
OFFLINE_FRAME = str(BASE_DIR / "static" / "offline-frame.jpg")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    if config.RUN_ENGINE:
        engine.start()
        bot.start()
        loc = "LIVE ENGINE"
    else:
        loc = "REMOTE SHELL (no engine)"
    print(
        f"SentinelIQ running at http://{config.HOST}:{config.PORT}  "
        f"(user: {config.DEFAULT_ADMIN_USER}, env={config.APP_ENV}, mode={loc})"
    )
    yield
    engine.stop()
    bot.stop()


app = FastAPI(title="SentinelIQ", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

if config.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# --- security middleware ------------------------------------------------------


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    if config.ALLOWED_HOSTS:
        host = (request.headers.get("host") or "").split(":")[0].strip().lower()
        if host and host not in config.ALLOWED_HOSTS:
            return JSONResponse({"detail": "Invalid Host header"}, status_code=400)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-XSS-Protection", "0")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


# --- auth helpers ------------------------------------------------------------


def _session_token(request: Request) -> str:
    token = request.cookies.get("session", "")
    if not token:
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            token = header[7:]
    return token


def _current_user(request: Request):
    token = _session_token(request)
    if not token:
        return None
    return get_user_by_token(token)


def require_auth(request: Request):
    user = _current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def _authed(request: Request) -> bool:
    return _current_user(request) is not None


# --- pages -------------------------------------------------------------------


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str = ""):
    if _authed(request):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(
        request, "login.html", {"error": error}
    )


@app.post("/login")
async def login(request: Request):
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")
    user = db.authenticate(username, password)
    if not user:
        return RedirectResponse("/login?error=invalid", status_code=303)
    token = db.create_session(user.id)
    resp = RedirectResponse("/dashboard", status_code=303)
    resp.set_cookie(
        "session",
        token,
        httponly=True,
        samesite="lax",
        secure=config.COOKIE_SECURE,
        max_age=config.SESSION_MAX_AGE,
    )
    return resp


@app.post("/api/login")
async def api_login(request: Request):
    """JSON login for the static (Vercel) frontend; sets the session cookie."""
    body = await request.json()
    user = db.authenticate(body.get("username", ""), body.get("password", ""))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = db.create_session(user.id)
    resp = JSONResponse({"status": "ok", "user": user.username})
    resp.set_cookie(
        "session",
        token,
        httponly=True,
        samesite="lax",
        secure=config.COOKIE_SECURE,
        max_age=config.SESSION_MAX_AGE,
        path="/",
    )
    return resp


@app.post("/api/logout")
def api_logout(request: Request):
    token = _session_token(request)
    if token:
        db.delete_session(token)
    resp = JSONResponse({"status": "ok"})
    resp.delete_cookie("session", path="/")
    return resp


@app.get("/logout")
def logout(request: Request):
    token = _session_token(request)
    if token:
        db.delete_session(token)
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("session")
    return resp


@app.get("/", include_in_schema=False)
def index_redirect():
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    if not _authed(request):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "dashboard.html", {"active": "dashboard"})


@app.get("/zone-picker", response_class=HTMLResponse)
def picker_page(request: Request):
    if not _authed(request):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "picker.html", {"active": "picker"})


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    if not _authed(request):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "settings.html", {"active": "settings"})


# --- API ----------------------------------------------------------------------


@app.get("/api/status")
def api_status(request: Request):
    require_auth(request)
    status = engine.status()
    status["settings"] = db.get_settings()
    status["live"] = config.RUN_ENGINE and engine.is_running()
    return status


def _live_frame() -> Optional[bytes]:
    """Return the current annotated JPEG, or the offline banner when the CV
    engine is absent/stopped (remote shell deployment)."""
    if config.RUN_ENGINE and engine.is_running() and engine.get_snapshot() is not None:
        return engine.get_snapshot()
    if os.path.exists(OFFLINE_FRAME):
        with open(OFFLINE_FRAME, "rb") as fh:
            return fh.read()
    return None


@app.get("/api/snapshot")
def api_snapshot(request: Request):
    require_auth(request)
    frame = _live_frame()
    if frame is None:
        raise HTTPException(status_code=503, detail="No frame available")
    return Response(
        content=frame,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/stream")
def api_stream(request: Request):
    if not _authed(request):
        return Response(status_code=401)

    def generate():
        frame = _live_frame()
        while True:
            if frame is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )
            time.sleep(0.5)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/zones")
def api_zones(request: Request):
    require_auth(request)
    return db.list_zones()


@app.post("/api/zone")
async def api_save_zone(request: Request):
    require_auth(request)
    body = await request.json()
    points = body.get("points")
    name = body.get("name") or "Restricted Zone"
    if (
        not isinstance(points, list)
        or len(points) < 3
        or not all(isinstance(p, list) and len(p) == 2 for p in points)
    ):
        raise HTTPException(status_code=400, detail="points must be a list of [x, y]")
    if not all(isinstance(v, (int, float)) for p in points for v in p):
        raise HTTPException(status_code=400, detail="invalid coordinate values")
    zone_id = db.save_zone(name, [[float(x), float(y)] for x, y in points])
    return {"id": zone_id, "status": "saved"}


@app.delete("/api/zone/{zone_id}")
def api_delete_zone(zone_id: int, request: Request):
    require_auth(request)
    db.delete_zone(zone_id)
    return {"status": "deleted"}


@app.get("/api/settings")
def api_get_settings(request: Request):
    require_auth(request)
    return {
        key: db.get_setting(key, default)
        for key, default in db.DEFAULT_SETTINGS.items()
    }


@app.post("/api/settings")
async def api_update_settings(request: Request):
    require_auth(request)
    body = await request.json()
    for key, value in body.items():
        if key not in db.SETTING_KEYS:
            raise HTTPException(status_code=400, detail=f"unknown setting: {key}")
        db.set_setting(key, str(value))
    return {"status": "saved"}


@app.post("/api/arm")
async def api_arm(request: Request):
    require_auth(request)
    body = await request.json()
    db.set_setting("manual_armed", "1" if bool(body.get("armed", True)) else "0")
    return {"status": "ok", "armed": db.settings_bool("manual_armed")}


# --- stream source configuration ---------------------------------------------


@app.get("/api/source")
def api_source(request: Request):
    require_auth(request)
    return {
        "type": db.get_setting("stream_source_type", "video"),
        "value": db.get_setting("stream_source_value", ""),
        "camera_name": db.get_setting("camera_name", "camera"),
        "resolved": engine.active_source,
    }


@app.post("/api/source")
async def api_set_source(request: Request):
    require_auth(request)
    body = await request.json()
    stype = str(body.get("type", "video"))
    value = str(body.get("value", "")).strip()
    camera = str(body.get("camera_name", "")).strip()
    if stype not in ("rtsp", "video", "upload"):
        raise HTTPException(status_code=400, detail="type must be rtsp|video|upload")
    if stype == "rtsp" and not value.startswith("rtsp://"):
        raise HTTPException(status_code=400, detail="invalid RTSP URL")
    db.set_setting("stream_source_type", stype)
    db.set_setting("stream_source_value", value)
    if camera:
        db.set_setting("camera_name", camera)
    return {"status": "ok", **api_source(request)}


@app.post("/api/upload")
async def api_upload(request: Request, file: UploadFile = File(...)):
    require_auth(request)
    if not file.filename:
        raise HTTPException(status_code=400, detail="no file")
    ext = Path(file.filename).suffix.lower()
    if ext not in (".mp4", ".avi", ".mkv", ".mov", ".webm"):
        raise HTTPException(status_code=400, detail="unsupported video format")
    name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
    dest = Path(MEDIA_DIR) / name
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    db.set_setting("stream_source_type", "upload")
    db.set_setting("stream_source_value", name)
    return {"status": "ok", "file": name, "resolved": str(dest)}


# --- evidence ------------------------------------------------------------------


@app.get("/api/evidence")
def api_evidence(request: Request, limit: int = 20):
    require_auth(request)
    return db.get_alerts(limit=min(limit, 50))


@app.get("/api/evidence/{alert_id}/image")
def api_evidence_image(alert_id: int, request: Request):
    require_auth(request)
    rec = db.get_alerts(limit=1000)
    match = [r for r in rec if r["id"] == alert_id]
    if not match:
        raise HTTPException(status_code=404, detail="not found")
    path = Path(EVIDENCE_DIR) / match[0]["image"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="image missing")
    return FileResponse(str(path), media_type="image/jpeg")


@app.get("/api/models")
def api_models(request: Request):
    require_auth(request)
    roots = [BASE_DIR.parent]
    if config.MODELS_DIR:
        roots.append(Path(config.MODELS_DIR))
    names = set()
    for root in roots:
        for pat in ("*.pt", "*.engine"):
            names.update(f.name for f in Path(root).glob(pat) if f.is_file())
    names = sorted(n for n in names if "yolo" in n.lower())
    current = (db.get_setting("model_file") or "").strip()
    items = [{"name": "DEFAULT", "path": "", "is_default": True, "active": current == ""}]
    for n in names:
        items.append({"name": n, "path": str(Path(root) / n), "is_default": False, "active": current == n})
    return items


@app.post("/api/system/reset")
def api_system_reset(request: Request):
    require_auth(request)
    db.reset_database()
    return {"status": "ok", "message": "database cleared and re-seeded"}


@app.post("/api/alarm")
def api_alarm(request: Request):
    require_auth(request)
    engine.trigger_onsite_alarm()
    return {"status": "ok"}


@app.post("/api/dismiss")
def api_dismiss(request: Request):
    require_auth(request)
    engine.reset_alert()
    return {"status": "ok"}


@app.post("/api/viewer/heartbeat")
def api_viewer_heartbeat(request: Request):
    require_auth(request)
    engine.note_viewer()
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok", "time": time.time()}