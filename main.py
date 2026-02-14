import cv2
import numpy as np
import supervision as sv
from ultralytics import YOLO
import winsound
import requests
import time

TOKEN = "8282242569:AAHFEEF9X3DqA_Nj29PzWowCRISHAzdJyl4"
CHAT_ID = "5718922695"
VIDEO_PATH = r"C:\Users\Rohith M S\OneDrive\Desktop\projects\Hackathon\theft.mp4"

SEC_TO_FAINT = 30 
FRAME_SKIP = 2     
ESTIMATED_FPS = 15 
FAINT_THRESHOLD_FRAMES = SEC_TO_FAINT * ESTIMATED_FPS

last_msg_time = 0
msg_cooldown = 30 
faint_timer = {} 

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT_ID}&text={text}"
    try: requests.get(url, timeout=0.5)
    except: pass

model = YOLO("yolo11m-pose.pt")
my_polygon = np.array([[179, 501], [471, 707], [7, 715], [6, 530], [124, 483]])

zone = sv.PolygonZone(polygon=my_polygon, triggering_anchors=[sv.Position.BOTTOM_CENTER])
zone_annotator = sv.PolygonZoneAnnotator(zone=zone, color=sv.Color.GREEN)

cap = cv2.VideoCapture(VIDEO_PATH)
frame_count = 0
annotated_frame = None

while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break

    frame_count += 1
    if frame_count % FRAME_SKIP != 0 and annotated_frame is not None:
        cv2.imshow("Hackathon AI Security Pro", annotated_frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break
        continue

    results = model(frame, imgsz=480, conf=0.25, verbose=False)[0]
    detections = sv.Detections.from_ultralytics(results)

    is_inside = zone.trigger(detections=detections)
    intruder_count = np.sum(is_inside)
    
    hands_up_total = 0
    faint_total = 0

    annotated_frame = frame.copy()
    annotated_frame = zone_annotator.annotate(scene=annotated_frame)

    for i in range(len(results.boxes)):
        coords = results.boxes.xyxy[i].cpu().numpy().astype(int).flatten()
        if len(coords) != 4: continue
        x1, y1, x2, y2 = coords
        w, h = x2 - x1, y2 - y1
        
        # --- NEW: Get Class Name and Confidence ---
        conf = results.boxes.conf[i].cpu().numpy()
        cls_id = int(results.boxes.cls[i].cpu().numpy())
        cls_name = model.names[cls_id]
        label = f"{cls_name} {int(conf*100)}%"
        
        # Display label above the polygon/box
        cv2.putText(annotated_frame, label, (x1, y1 - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        if results.keypoints is not None and cls_name == "person":
            kpts = results.keypoints.xy[i].cpu().numpy()
            if len(kpts) > 0:
                l_wrist, r_wrist = kpts[9][1], kpts[10][1]
                l_shldr, r_shldr = kpts[5][1], kpts[6][1]
                if (0 < l_wrist < l_shldr + 15) or (0 < r_wrist < r_shldr + 15):
                    hands_up_total += 1
                    cv2.putText(annotated_frame, "HANDS UP", (x1, y1 - 25), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)

                nose_y = kpts[0][1]
                hip_y = (kpts[11][1] + kpts[12][1]) / 2
                
                if (w / (h + 1e-6) > 1.1) or (nose_y > hip_y and nose_y > 0):
                    faint_timer[i] = faint_timer.get(i, 0) + 1
                    current_seconds = int(faint_timer[i] / ESTIMATED_FPS)
                    
                    if faint_timer[i] > FAINT_THRESHOLD_FRAMES:
                        faint_total += 1
                        cv2.putText(annotated_frame, "CRITICAL: FAINTED", (x1, y1 - 40), 
                                    cv2.FONT_HERSHEY_DUPLEX, 0.8, (0, 0, 255), 3)
                    else:
                        cv2.putText(annotated_frame, f"Down: {current_seconds}s", (x1, y2 + 20), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 165, 0), 2)
                else:
                    faint_timer[i] = 0 

                for pt in kpts:
                    px, py = int(pt[0]), int(pt[1])
                    if px > 0 and py > 0:
                        cv2.circle(annotated_frame, (px, py), 3, (255, 0, 255), -1)

        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

    cv2.putText(annotated_frame, f"INTRUDER(S): {intruder_count}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(annotated_frame, f"HANDS UP: {hands_up_total}", (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    cv2.putText(annotated_frame, f"FAINTS: {faint_total}", (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    if intruder_count > 0 or faint_total > 0:
        winsound.Beep(1000, 100)
        curr_time = time.time()
        if curr_time - last_msg_time > msg_cooldown:
            alert_type = "MEDICAL EMERGENCY" if faint_total > 0 else "ZONE BREACH"
            msg = f" {alert_type} REPORT:\n- Faints: {faint_total}\n- Intruders: {intruder_count}\n- Hands Up: {hands_up_total}"
            send_telegram(msg)
            last_msg_time = curr_time

    cv2.imshow("Hackathon AI Security Pro", annotated_frame)
    if cv2.waitKey(1) & 0xFF == ord('q'): break

cap.release()
cv2.destroyAllWindows()