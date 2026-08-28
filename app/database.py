"""SQLite persistence: users, sessions, camera zones, and settings.

Single lightweight schema - no external DB required.
"""

import hashlib
import json
import os
import secrets
import threading
from typing import Optional

from sqlalchemy import create_engine, Column, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

import config

Base = declarative_base()
_engine = create_engine(
    f"sqlite:///{config.DATABASE_PATH}", connect_args={"check_same_thread": False}
)
_Session = sessionmaker(bind=_engine)
_lock = threading.RLock()

DEFAULT_SETTINGS = {
    "telegram_token": config.TELEGRAM_BOT_TOKEN,
    "telegram_chat_id": config.TELEGRAM_CHAT_ID,
    "audio_enabled": "1",
    "manual_armed": "1",
    "schedule_enabled": "0",
    "schedule_start": "22:00",
    "schedule_end": "06:00",
    "emergency_number": config.EMERGENCY_NUMBER,
    "stream_source_type": "video",
    "stream_source_value": config.VIDEO_PATH,
    "camera_name": "Lobby Camera",
    "model_conf": str(config.MODEL_CONF),
    "model_imgsz": str(config.MODEL_IMGSZ),
    "frame_skip": str(config.FRAME_SKIP),
    "faint_seconds": str(config.SEC_TO_FAINT),
    "item_detector": "1",
    "msg_cooldown": str(config.MSG_COOLDOWN),
    "model_file": "",
}

SETTING_KEYS = set(DEFAULT_SETTINGS.keys())


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)


class AuthSession(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    token = Column(String, unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User")


class Zone(Base):
    __tablename__ = "zones"

    id = Column(Integer, primary_key=True)
    name = Column(String, default="Restricted Zone")
    points = Column(Text, nullable=False)  # JSON list of [x, y]
    is_active = Column(Integer, default=1)


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(Text, default="")


class AlertRecord(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    created = Column(Float, nullable=False)
    event_type = Column(String, nullable=False)
    zone = Column(String, default="")
    camera = Column(String, default="")
    count = Column(Integer, default=0)
    items = Column(Text, default="[]")
    has_weapon = Column(Integer, default=0)
    image = Column(String, default="")


def _db():
    return _Session()


def init_db() -> None:
    with _lock:
        Base.metadata.create_all(_engine)
        seed()


def seed() -> None:
    s = _db()
    try:
        if not s.query(User).filter_by(username=config.DEFAULT_ADMIN_USER).first():
            s.add(
                User(
                    username=config.DEFAULT_ADMIN_USER,
                    password_hash=hash_password(config.DEFAULT_ADMIN_PASSWORD),
                )
            )
        if not s.query(Zone).first():
            s.add(Zone(name="Restricted Zone", points=json.dumps(config.DEFAULT_ZONE)))
        for key, value in DEFAULT_SETTINGS.items():
            if not s.query(Setting).filter_by(key=key).first():
                s.add(Setting(key=key, value=value))
        s.commit()
    finally:
        s.close()


# --- Authentication ---------------------------------------------------------


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 100_000
    ).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    calc = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 100_000
    ).hex()
    return secrets.compare_digest(calc, digest)


def create_user(username: str, password: str) -> Optional[User]:
    with _lock:
        s = _db()
        try:
            if s.query(User).filter_by(username=username).first():
                return None
            user = User(username=username, password_hash=hash_password(password))
            s.add(user)
            s.commit()
            return user
        finally:
            s.close()


def authenticate(username: str, password: str) -> Optional[User]:
    s = _db()
    try:
        user = s.query(User).filter_by(username=username).first()
        if user and verify_password(password, user.password_hash):
            return user
        return None
    finally:
        s.close()


def create_session(user_id: int) -> str:
    with _lock:
        s = _db()
        try:
            token = secrets.token_hex(32)
            s.add(AuthSession(token=token, user_id=user_id))
            s.commit()
            return token
        finally:
            s.close()


def get_user_by_token(token: str) -> Optional[User]:
    s = _db()
    try:
        session = s.query(AuthSession).filter_by(token=token).first()
        return session.user if session else None
    finally:
        s.close()


def delete_session(token: str) -> None:
    with _lock:
        s = _db()
        try:
            s.query(AuthSession).filter_by(token=token).delete()
            s.commit()
        finally:
            s.close()


# --- Settings ---------------------------------------------------------------


def get_setting(key: str, default: str = "") -> str:
    s = _db()
    try:
        row = s.query(Setting).filter_by(key=key).first()
        return row.value if row else default
    finally:
        s.close()


def set_setting(key: str, value: str) -> None:
    with _lock:
        s = _db()
        try:
            row = s.query(Setting).filter_by(key=key).first()
            if row:
                row.value = value
            else:
                s.add(Setting(key=key, value=value))
            s.commit()
        finally:
            s.close()


def get_settings() -> dict:
    out = dict(DEFAULT_SETTINGS)
    s = _db()
    try:
        for row in s.query(Setting).all():
            out[row.key] = row.value
    finally:
        s.close()
    return out


def settings_bool(key: str) -> bool:
    return get_setting(key, "0").strip().lower() in ("1", "true", "yes", "on")


# --- Zones ------------------------------------------------------------------


def get_active_zones() -> list:
    s = _db()
    try:
        rows = s.query(Zone).filter_by(is_active=1).all()
        out = []
        for row in rows:
            try:
                pts = json.loads(row.points)
            except json.JSONDecodeError:
                continue
            if isinstance(pts, list) and len(pts) >= 3:
                out.append({"id": row.id, "name": row.name, "points": pts})
        return out
    finally:
        s.close()


def save_zone(name: str, points: list, active: bool = True) -> int:
    with _lock:
        s = _db()
        try:
            zone = Zone(name=name, points=json.dumps(points), is_active=int(active))
            s.add(zone)
            s.flush()
            zone_id = zone.id
            s.commit()
            return zone_id
        finally:
            s.close()


def delete_zone(zone_id: int) -> None:
    with _lock:
        s = _db()
        try:
            s.query(Zone).filter_by(id=zone_id).delete()
            s.commit()
        finally:
            s.close()


def list_zones() -> list:
    s = _db()
    try:
        rows = s.query(Zone).all()
        return [
            {
                "id": row.id,
                "name": row.name,
                "points": json.loads(row.points) if row.points else [],
                "is_active": bool(row.is_active),
            }
            for row in rows
        ]
    finally:
        s.close()


# --- Alert records (evidence) -------------------------------------------------

def add_alert(
    created: float,
    event_type: str,
    zone: str,
    camera: str,
    count: int,
    items: list,
    has_weapon: bool,
    image: str,
) -> int:
    with _lock:
        s = _db()
        try:
            rec = AlertRecord(
                created=created,
                event_type=event_type,
                zone=zone,
                camera=camera,
                count=count,
                items=json.dumps(items),
                has_weapon=int(has_weapon),
                image=image,
            )
            s.add(rec)
            s.flush()
            rec_id = rec.id
            s.commit()
            return rec_id
        finally:
            s.close()


def get_alerts(limit: int = 20) -> list:
    s = _db()
    try:
        rows = s.query(AlertRecord).order_by(AlertRecord.created.desc()).limit(limit).all()
        out = []
        for r in rows:
            try:
                items = json.loads(r.items)
            except json.JSONDecodeError:
                items = []
            out.append(
                {
                    "id": r.id,
                    "created": r.created,
                    "event_type": r.event_type,
                    "zone": r.zone,
                    "camera": r.camera,
                    "count": r.count,
                    "items": items,
                    "has_weapon": bool(r.has_weapon),
                    "image": r.image,
                }
            )
        return out
    finally:
        s.close()


def reset_database() -> None:
    """Factory reset: wipe alerts, zones and settings, re-seeding defaults."""
    with _lock:
        s = _db()
        try:
            s.query(AlertRecord).delete()
            s.query(Zone).delete()
            s.query(Setting).delete()
            s.commit()
            for key, value in DEFAULT_SETTINGS.items():
                s.add(Setting(key=key, value=value))
            s.commit()
        finally:
            s.close()