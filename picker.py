"""Interactive tool to pick polygon coordinates for the restricted zone.

Run:  python picker.py
Click corners in order, press 'q' to finish.
"""

import sys

import cv2

import config

points = []


def click_event(event, x, y, flags, param) -> None:
    global img
    if event == cv2.EVENT_LBUTTONDOWN:
        cv2.circle(img, (x, y), 5, (0, 0, 255), -1)
        points.append((x, y))
        print(f"Selected point: ({x}, {y})")

        if len(points) > 1:
            cv2.line(img, points[-2], points[-1], (255, 0, 0), 2)

        cv2.imshow("coordinates", img)


cap = cv2.VideoCapture(config.VIDEO_PATH)
success, img = cap.read()
cap.release()

if not success:
    print(f"Failed to load video: {config.VIDEO_PATH}")
    sys.exit(1)

cv2.namedWindow("coordinates")
cv2.setMouseCallback("coordinates", click_event)

print("1. Click the corners of the restricted zone in order.")
print("2. Press 'q' or any key to finish and get coordinates.")

while True:
    cv2.imshow("coordinates", img)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cv2.destroyAllWindows()
print("Final list of selected points:", points)