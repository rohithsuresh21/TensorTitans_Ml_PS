"""Computer-vision detection pipeline with TensorRT-first inference.

Runs in a background thread: captures frames from RTSP (or a local video/upload),
performs YOLO pose inference gated by armed/schedule state, annotates, caches the
latest frame, and pushes alert events with evidence (snapshot + carried-item scan)
to an injected handler.
"""

import json
import os
import sys
import threading
import time
from datetime import datetime
from typing import Callable, Optional

import cv2
import numpy as np
import supervision as sv
from ultralytics import YOLO

import config
from app import database as db

AlertHandler = Callable[["AlertEvent"], None]

# COCO classes considered "carried items / potential threats".
ITEM_CLASS_IDS = {24, 25, 26, 27, 28, 39, 41, 43, 63, 67, 76}  # backpack..cellphone, knife
WEAPON_CLASSES = {43, 76, 34, 36, 38}  # knife, scissors, bat, skateboard, tennis racket

ITEM_DETECTOR = "yolo11n.pt"
BEEP_INTERVAL = 1.2  # seconds between sustained in-zone beeps
VIEWER_WINDOW = 6.0  # viewer considered active while heartbeat within this window
EVIDENCE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "evidence")
MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media")


class AlertEvent:
    def __init__(self, event_type: str, jpeg: bytes, counts: dict, zone_name: str, items: list, has_weapon: bool):
        self.event_type = event_type
        self.jpeg = jpeg
        self.counts = counts
        self.zone_name = zone_name
        self.items = items
        self.has_weapon = has_weapon


def _s(path: str) -> str:
    return os.path.normpath(path)


class DetectionEngine:
    def __init__(self):
        self.model = None
        self.item_model = None
        self.device = "cpu"
        self.model_file = ""
        self.alert_handler: Optional[AlertHandler] = None

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self.latest_jpeg: Optional[bytes] = None
        self.latest_jpeg_frame_id = 0
        self.frame_counter = 0

        self.zones: list = []
        self.active_source = ""
        self._reload_ts = 0.0
        self._settings_ts = 0.0
        self._settings: dict = {}

        self.faint_timer: dict[tuple, int] = {}
        self.last_alert_time = 0.0
        self._inside_zone = False  # Telegram fires only on new entry (no spam)
        self.last_events: list = []
        self.alarm_stop = threading.Event()
        self._fps_window: list = []
        self._last_beep = 0.0
        self._viewer_ts = 0.0  # last dashboard heartbeat

        os.makedirs(EVIDENCE_DIR, exist_ok=True)
        os.makedirs(MEDIA_DIR, exist_ok=True)

    # --- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        self._load_model()
        self._settings = db.get_settings()
        self.active_source = self._resolve_source()
        self._thread = threading.Thread(target=self._pipeline, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.alarm_stop.set()
        if self._thread:
            self._thread.join(timeout=4)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # --- model loading ------------------------------------------------------

    def _load_model(self, path: Optional[str] = None) -> None:
        try:
            import torch

            self.device = "0" if torch.cuda.is_available() else "cpu"
            if self.device == "0":
                print(f"[engine] CUDA GPU: {torch.cuda.get_device_name(0)}")
        except Exception:
            self.device = "cpu"

        # Explicit path (model switcher) or prefer TensorRT engine, fall back to .pt.
        candidates = [path] if path else [config.MODEL_ENGINE, config.MODEL_PATH]
        for candidate in candidates:
            if not candidate or not os.path.exists(candidate):
                continue
            try:
                self.model = YOLO(candidate, task="pose"
                                  if candidate.endswith(".engine") and "pose" in candidate else None)
                self.model_file = candidate
                print(f"[engine] pose model loaded: {candidate} (device={self.device})")
                return
            except Exception as exc:
                print(f"[engine] failed to load {candidate}: {exc}")
                continue
        print("[engine] no pose model found. Set MODEL_PATH/MODEL_ENGINE.")

    def _ensure_item_model(self) -> Optional[YOLO]:
        if self.item_model is None:
            try:
                self.item_model = YOLO(ITEM_DETECTOR)
                print(f"[engine] item detector loaded: {ITEM_DETECTOR}")
            except Exception as exc:
                print(f"[engine] item detector unavailable: {exc}")
                self.item_model = None
        return self.item_model

    # --- source resolution ---------------------------------------------------

    def _resolve_source(self) -> str:
        stype = self._settings.get("stream_source_type", "video")
        value = self._settings.get("stream_source_value", "").strip()
        if stype == "rtsp":
            return value if value.startswith("rtsp://") else config.RTSP_STREAM_URL
        if stype == "upload":
            path = _s(os.path.join(MEDIA_DIR, os.path.basename(value))) if value else ""
            return path if os.path.exists(path) else config.VIDEO_PATH
        return _s(value) if os.path.exists(value) else config.VIDEO_PATH

    # --- state reload -------------------------------------------------------

    def _reload(self) -> None:
        now = time.time()
        if now - self._settings_ts > 2.0:
            self._settings = db.get_settings()
            self._settings_ts = now
        if now - self._reload_ts > 3.0:
            self.zones = db.get_active_zones()
            self._reload_ts = now

        # Model switcher: reload when the selected file changes.
        wanted = (self._settings.get("model_file") or "").strip()
        if wanted and os.path.exists(wanted) and wanted != self.model_file:
            print(f"[engine] pose model switched: {self.model_file} -> {wanted}")
            self._load_model(wanted)

        source = self._resolve_source()
        if source != self.active_source:
            print(f"[engine] stream source changed: {self.active_source} -> {source}")
            self.active_source = source
            return True
        return False

    def is_armed(self) -> bool:
        if not self._settings or not self._settings_ts:
            self._settings = db.get_settings()
            self._settings_ts = time.time()
        if db.settings_bool("manual_armed"):
            return True
        if db.settings_bool("schedule_enabled"):
            return self._in_schedule(
                self._settings.get("schedule_start", "22:00"),
                self._settings.get("schedule_end", "06:00"),
            )
        return False

    @staticmethod
    def _in_schedule(start: str, end: str) -> bool:
        def to_min(t: str) -> int:
            try:
                hh, mm = t.split(":")
                return int(hh) * 60 + int(mm)
            except (ValueError, AttributeError):
                return 0

        now = time.localtime()
        cur = now.tm_hour * 60 + now.tm_min
        s, e = to_min(start), to_min(end)
        if s == e:
            return True
        return (cur >= s) if s < e else (cur >= s or cur < e)

    # --- pipeline ------------------------------------------------------------

    def _pipeline(self) -> None:
        while not self._stop.is_set():
            cap = cv2.VideoCapture(self.active_source)
            if not cap.isOpened():
                print(f"[engine] cannot open stream: {self.active_source}")
                self._stop.wait(5.0)
                continue

            loop_start = time.time()
            while not self._stop.is_set():
                ret, frame = cap.read()
                if not ret:
                    break
                self.frame_counter += 1
                self._fps_window.append(time.time())
                if len(self._fps_window) > 60:
                    self._fps_window.pop(0)

                self._cache_raw_jpeg(frame)

                changed = self._reload()
                if changed:
                    break
                if not self.is_armed():
                    time.sleep(0.01)
                    continue

                skip = int(self._settings.get("frame_skip", config.FRAME_SKIP) or 1)
                if self.frame_counter % skip != 0:
                    continue
                if self.model is None:
                    continue

                self._process(frame)
            cap.release()
            if self.frame_counter and time.time() - loop_start < 2.0:  # file ended -> relaunch
                self._stop.wait(0.5)
            else:
                self._stop.wait(2.5)

    def _cache_raw_jpeg(self, frame: np.ndarray) -> None:
        if self.latest_jpeg is None:
            with self._lock:
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if ok:
                    self.latest_jpeg = buf.tobytes()
                    self.latest_jpeg_frame_id = self.frame_counter

    def _frame_skip(self) -> int:
        try:
            return int(self._settings.get("frame_skip", config.FRAME_SKIP))
        except (TypeError, ValueError):
            return config.FRAME_SKIP

    def _imgsz(self) -> int:
        try:
            return int(self._settings.get("model_imgsz", config.MODEL_IMGSZ))
        except (TypeError, ValueError):
            return config.MODEL_IMGSZ

    def _conf(self) -> float:
        try:
            return float(self._settings.get("model_conf", config.MODEL_CONF))
        except (TypeError, ValueError):
            return config.MODEL_CONF

    def _faint_frames(self) -> int:
        try:
            return int(float(self._settings.get("faint_seconds", config.SEC_TO_FAINT)) * config.ESTIMATED_FPS)
        except (TypeError, ValueError):
            return config.SEC_TO_FAINT * config.ESTIMATED_FPS

    # --- per-frame processing -------------------------------------------------

    def _process(self, frame: np.ndarray) -> None:
        try:
            results = self.model(
                frame,
                imgsz=self._imgsz(),
                conf=self._conf(),
                verbose=False,
                device=self.device,
            )[0]
        except Exception as exc:
            print(f"[engine] inference error: {exc}")
            return

        detections = sv.Detections.from_ultralytics(results)

        intruder_count = 0
        zone_name = ""
        inside = None
        if self.zones:
            primary = self.zones[0]
            polygon = np.array(primary["points"], dtype=np.int32)
            zone = sv.PolygonZone(
                polygon=polygon, triggering_anchors=[sv.Position.BOTTOM_CENTER]
            )
            inside = zone.trigger(detections=detections)
            intruder_count = int(np.sum(inside))
            zone_name = primary.get("name", "")

        hands_up_total = 0
        faint_total = 0
        annot = frame.copy()

        zone_overlay = np.zeros_like(annot)
        for z in self.zones:
            pts = np.array(z["points"], dtype=np.int32)
            cv2.polylines(annot, [pts], True, (255, 255, 255), 2)
            cv2.fillPoly(zone_overlay, [pts], (0, 180, 0))
        annot = cv2.addWeighted(annot, 1.0, zone_overlay, 0.18, 0)

        intruder_boxes = []
        for i in range(len(results.boxes)):
            coords = results.boxes.xyxy[i].cpu().numpy().astype(int).flatten()
            if len(coords) != 4:
                continue
            x1, y1, x2, y2 = coords
            w, h = x2 - x1, y2 - y1

            cls_id = int(results.boxes.cls[i].cpu().numpy())
            cls_name = self.model.names[cls_id]
            conf = results.boxes.conf[i].cpu().numpy()

            is_intruder = inside is not None and inside[i] and cls_name == "person"
            border = (0, 0, 255) if is_intruder else (0, 255, 0)
            cv2.rectangle(annot, (x1, y1), (x2, y2), border, 2)
            label = f"{cls_name} {int(conf * 100)}%"
            cv2.putText(annot, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, border, 2)
            if is_intruder:
                intruder_boxes.append((x1, y1, x2, y2))

            if results.keypoints is not None and cls_name == "person":
                kpts = results.keypoints.xy[i].cpu().numpy()
                if len(kpts) > 0:
                    l_wrist, r_wrist = kpts[9][1], kpts[10][1]
                    l_shldr, r_shldr = kpts[5][1], kpts[6][1]
                    if (0 < l_wrist < l_shldr + 15) or (0 < r_wrist < r_shldr + 15):
                        hands_up_total += 1
                        cv2.putText(annot, "HANDS UP", (x1, y1 - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)

                    nose_y = kpts[0][1]
                    hip_y = (kpts[11][1] + kpts[12][1]) / 2
                    track = (x1, y1, x2, y2)
                    if (w / (h + 1e-6) > 1.1) or (nose_y > hip_y and nose_y > 0):
                        self.faint_timer[track] = self.faint_timer.get(track, 0) + 1
                        if self.faint_timer[track] > self._faint_frames():
                            if is_intruder:
                                faint_total += 1
                            cv2.putText(annot, "CRITICAL: FAINTED", (x1, y1 - 40), cv2.FONT_HERSHEY_DUPLEX, 0.8, (0, 0, 255), 3)
                        else:
                            seconds = int(self.faint_timer[track] / config.ESTIMATED_FPS)
                            cv2.putText(annot, f"Down: {seconds}s", (x1, y2 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 165, 0), 2)
                    else:
                        self.faint_timer[track] = 0

                    for pt in kpts:
                        px, py = int(pt[0]), int(pt[1])
                        if px > 0 and py > 0:
                            cv2.circle(annot, (px, py), 3, (255, 0, 255), -1)

        camera = self._settings.get("camera_name", "camera")
        cv2.putText(annot, f"INTRUDER(S): {intruder_count}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(annot, f"HANDS UP: {hands_up_total}", (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.putText(annot, f"FAINTS: {faint_total}", (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        with self._lock:
            ok, buf = cv2.imencode(".jpg", annot, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                self.latest_jpeg = buf.tobytes()
                self.latest_jpeg_frame_id = self.frame_counter

        counts = {"intruders": intruder_count, "hands_up": hands_up_total, "faints": faint_total}
        # Evidence uses the RAW frame so a clear intruder face is kept (no overlay).
        self._maybe_alert(counts, zone_name, frame, intruder_boxes)

    # --- alerts, evidence & sound --------------------------------------------

    def _maybe_alert(self, counts: dict, zone_name: str, frame: np.ndarray, intruder_boxes: list) -> None:
        alert_hit = counts["intruders"] > 0  # zone-gated only

        # Sustained beep while someone is inside the zone - but only while the
        # dashboard is open (viewer heartbeat), so nothing beeps headless.
        if db.settings_bool("audio_enabled") and alert_hit and self.viewer_active:
            now = time.time()
            if now - self._last_beep >= BEEP_INTERVAL:
                self._last_beep = now
                self._beep_once()

        if not alert_hit:
            self._inside_zone = False
            return

        # Send Telegram + save evidence only once per intrusion episode
        # (rising edge), so a person staying inside the zone doesn't spam chat.
        now = time.time()
        entry = not self._inside_zone
        self._inside_zone = True
        if not entry:
            return

        cooldown = self._msg_cooldown()
        if now - self.last_alert_time <= cooldown:
            return
        self.last_alert_time = now

        items, has_weapon = [], False
        if db.settings_bool("item_detector") and (intruder_boxes or counts["faints"] > 0):
            items, has_weapon = self._scan_items(frame, intruder_boxes)

        event_type = "MEDICAL EMERGENCY" if counts["faints"] > 0 else "ZONE BREACH"
        event = AlertEvent(event_type, self.latest_jpeg or b"", counts, zone_name, items, has_weapon)
        self.last_events.insert(0, {"type": event_type, "time": now, **counts})
        self.last_events = self.last_events[:30]

        evidence_file = self._save_evidence(event_type, zone_name, frame, counts, items, has_weapon)

        if self.alert_handler:
            try:
                self.alert_handler(event)
            except Exception as exc:
                print(f"[engine] alert handler error: {exc}")

    def _scan_items(self, frame: np.ndarray, boxes: list) -> tuple:
        model = self._ensure_item_model()
        if model is None:
            return [], False
        items: list = []
        seen = set()
        for (x1, y1, x2, y2) in boxes:
            x1 = max(0, x1 - 15)
            y1 = max(0, y1 - 15)
            crop = frame[y1:y2 + 15, x1:x2 + 15]
            if crop.size == 0:
                continue
            try:
                r = model.predict(crop, imgsz=384, conf=0.25, verbose=False, device=self.device)[0]
            except Exception:
                continue
            for b in r.boxes:
                cid = int(b.cls[0].cpu().numpy())
                if cid not in ITEM_CLASS_IDS:
                    continue
                name = model.names[cid]
                if name not in seen:
                    seen.add(name)
                    items.append(name)
        weapon = any(name in {"knife", "scissors", "baseball bat"} for name in items)
        return items, weapon

    def _save_evidence(self, event_type: str, zone: str, frame: np.ndarray, counts: dict, items: list, has_weapon: bool) -> str:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{stamp}_{event_type.lower().replace(' ', '_')}.jpg"
        path = os.path.join(EVIDENCE_DIR, fname)
        cv2.imwrite(path, frame)
        camera = self._settings.get("camera_name", "camera")
        db.add_alert(
            created=time.time(),
            event_type=event_type,
            zone=zone,
            camera=camera,
            count=int(counts["intruders"]) + int(counts["faints"]),
            items=items,
            has_weapon=has_weapon,
            image=fname,
        )
        return fname

    def _msg_cooldown(self) -> int:
        try:
            return int(self._settings.get("msg_cooldown", config.MSG_COOLDOWN))
        except (TypeError, ValueError):
            return config.MSG_COOLDOWN

    def reset_alert(self) -> None:
        """Clear the alert cooldown (used by the HIL 'false alarm' dismissal)."""
        self.last_alert_time = 0.0
        print("[engine] alert cooldown cleared (dismissed via HIL)")

    def note_viewer(self) -> None:
        """Dashboard sends a heartbeat; presence is required for the local beep."""
        self._viewer_ts = time.time()

    @property
    def viewer_active(self) -> bool:
        return time.time() - self._viewer_ts < VIEWER_WINDOW

    def trigger_onsite_alarm(self, duration: float = 8.0) -> None:
        threading.Thread(target=self._alarm_loop, args=(duration,), daemon=True).start()

    def _alarm_loop(self, duration: float) -> None:
        self.alarm_stop.clear()
        end = time.time() + duration
        while time.time() < end and not self.alarm_stop.is_set():
            self._beep_once()
            time.sleep(0.4)

    def _beep_once(self) -> None:
        try:
            import winsound

            winsound.Beep(1000, 100)
            return
        except ImportError:
            pass
        if sys.platform.startswith("linux"):
            os.system("printf '\\a'")
        elif sys.platform == "darwin":
            sys.stdout.write("\a")

    # --- public getters -------------------------------------------------------

    def get_snapshot(self) -> Optional[bytes]:
        with self._lock:
            if self.latest_jpeg is not None:
                return self.latest_jpeg
        return self._fetch_still()

    def _fetch_still(self) -> Optional[bytes]:
        cap = cv2.VideoCapture(self.active_source or config.VIDEO_PATH)
        if not cap.isOpened():
            return None
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return None
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return buf.tobytes() if ok else None

    def fps(self) -> float:
        if len(self._fps_window) < 2:
            return 0.0
        return (len(self._fps_window) - 1) / max(1e-6, self._fps_window[-1] - self._fps_window[0])

    def status(self) -> dict:
        return {
            "armed": self.is_armed(),
            "model": self.model_file or "none",
            "device": self.device,
            "running": self.is_running(),
            "fps": round(self.fps(), 1),
            "source": self.active_source,
            "camera": self._settings.get("camera_name", "camera"),
            "frame_id": self.latest_jpeg_frame_id,
            "zones": len(self.zones),
            "events": list(self.last_events),
            "schedule": {
                "enabled": db.settings_bool("schedule_enabled"),
                "start": self._settings.get("schedule_start", "22:00"),
                "end": self._settings.get("schedule_end", "06:00"),
            },
        }