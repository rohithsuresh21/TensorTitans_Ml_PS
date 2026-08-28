"""Hackathon AI Security Pro - real-time security & medical emergency monitor."""

import os
import sys
import time
from typing import Dict, List

import cv2
import numpy as np
import supervision as sv
import requests
from ultralytics import YOLO

import config

VIDEO_PATH = config.VIDEO_PATH
FRAME_SKIP = config.FRAME_SKIP
ESTIMATED_FPS = config.ESTIMATED_FPS
FAINT_THRESHOLD_FRAMES = int(config.SEC_TO_FAINT * ESTIMATED_FPS)
MSG_COOLDOWN = config.MSG_COOLDOWN
ALERT_SOUND = config.ALERT_SOUND

last_msg_time = 0.0
faint_timer: Dict[int, int] = {}

WINDOW_NAME = "Hackathon AI Security Pro"


def beep_alarm() -> None:
    """Play an audible alert (Windows winsound / beep, or fallback for other OS)."""
    if ALERT_SOUND == "winsound":
        try:
            import winsound  # built-in on Windows only

            winsound.Beep(1000, 100)
            return
        except ImportError:
            pass
    if sys.platform == "darwin":
        sys.stdout.write("\a")
    elif sys.platform.startswith("linux"):
        os.system("printf '\\a'")


def send_telegram(message: str) -> None:
    """Send an alert to Telegram. Fails silently if tokens are missing or request errors."""
    if not config.BOT_TOKEN or not config.CHAT_ID:
        return
    url = (
        f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage"
        f"?chat_id={config.CHAT_ID}&text={message}"
    )
    try:
        requests.get(url, timeout=0.5)
    except requests.RequestException:
        pass


def draw_skeleton(frame: np.ndarray, keypoints) -> None:
    """Draw pose keypoints on the frame."""
    for pt in keypoints:
        px, py = int(pt[0]), int(pt[1])
        if px > 0 and py > 0:
            cv2.circle(frame, (px, py), 3, (255, 0, 255), -1)


def validate_env() -> bool:
    if not VIDEO_PATH or not os.path.exists(VIDEO_PATH):
        print(f"ERROR: video not found at {VIDEO_PATH!r}. Set VIDEO_PATH in .env")
        return False
    if not os.path.exists(config.MODEL_PATH):
        print(
            f"ERROR: YOLO model not found at {config.MODEL_PATH!r}. "
            "Download it or set MODEL_PATH in .env"
        )
        return False
    return True


def main() -> None:
    global last_msg_time

    if not validate_env():
        sys.exit(1)

    model = YOLO(config.MODEL_PATH)
    polygon = np.array(config.ZONE_POLYGON, dtype=np.int32)
    zone = sv.PolygonZone(
        polygon=polygon, triggering_anchors=[sv.Position.BOTTOM_CENTER]
    )
    zone_annotator = sv.PolygonZoneAnnotator(zone=zone, color=sv.Color.GREEN)

    cap = cv2.VideoCapture(VIDEO_PATH)
    frame_count = 0
    annotated_frame = None

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        if frame_count % FRAME_SKIP != 0 and annotated_frame is not None:
            cv2.imshow(WINDOW_NAME, annotated_frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
            continue

        results = model(
            frame, imgsz=config.MODEL_IMGSZ, conf=config.MODEL_CONF, verbose=False
        )[0]
        detections = sv.Detections.from_ultralytics(results)

        intruder_count = int(np.sum(zone.trigger(detections=detections)))
        hands_up_total = 0
        faint_total = 0

        annotated_frame = frame.copy()
        annotated_frame = zone_annotator.annotate(scene=annotated_frame)

        for i in range(len(results.boxes)):
            coords = results.boxes.xyxy[i].cpu().numpy().astype(int).flatten()
            if len(coords) != 4:
                continue
            x1, y1, x2, y2 = coords
            w, h = x2 - x1, y2 - y1

            cls_id = int(results.boxes.cls[i].cpu().numpy())
            cls_name = model.names[cls_id]
            conf = results.boxes.conf[i].cpu().numpy()
            label = f"{cls_name} {int(conf * 100)}%"

            cv2.putText(
                annotated_frame, label, (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2,
            )

            if results.keypoints is not None and cls_name == "person":
                kpts = results.keypoints.xy[i].cpu().numpy()
                if len(kpts) > 0:
                    l_wrist, r_wrist = kpts[9][1], kpts[10][1]
                    l_shldr, r_shldr = kpts[5][1], kpts[6][1]
                    if (0 < l_wrist < l_shldr + 15) or (0 < r_wrist < r_shldr + 15):
                        hands_up_total += 1
                        cv2.putText(
                            annotated_frame, "HANDS UP", (x1, y1 - 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2,
                        )

                    nose_y = kpts[0][1]
                    hip_y = (kpts[11][1] + kpts[12][1]) / 2

                    if (w / (h + 1e-6) > 1.1) or (nose_y > hip_y and nose_y > 0):
                        faint_timer[i] = faint_timer.get(i, 0) + 1
                        current_seconds = int(faint_timer[i] / ESTIMATED_FPS)

                        if faint_timer[i] > FAINT_THRESHOLD_FRAMES:
                            faint_total += 1
                            cv2.putText(
                                annotated_frame, "CRITICAL: FAINTED", (x1, y1 - 40),
                                cv2.FONT_HERSHEY_DUPLEX, 0.8, (0, 0, 255), 3,
                            )
                        else:
                            cv2.putText(
                                annotated_frame, f"Down: {current_seconds}s",
                                (x1, y2 + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 165, 0), 2,
                            )
                    else:
                        faint_timer[i] = 0

                    draw_skeleton(annotated_frame, kpts)

            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        cv2.putText(
            annotated_frame, f"INTRUDER(S): {intruder_count}", (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2,
        )
        cv2.putText(
            annotated_frame, f"HANDS UP: {hands_up_total}", (20, 75),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2,
        )
        cv2.putText(
            annotated_frame, f"FAINTS: {faint_total}", (20, 110),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2,
        )

        if intruder_count > 0 or faint_total > 0:
            beep_alarm()
            curr_time = time.time()
            if curr_time - last_msg_time > MSG_COOLDOWN:
                alert_type = "MEDICAL EMERGENCY" if faint_total > 0 else "ZONE BREACH"
                msg = (
                    f"{alert_type} REPORT:\n"
                    f"- Faints: {faint_total}\n"
                    f"- Intruders: {intruder_count}\n"
                    f"- Hands Up: {hands_up_total}"
                )
                send_telegram(msg)
                last_msg_time = curr_time

        cv2.imshow(WINDOW_NAME, annotated_frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()