Hackathon AI Security Pro

AI-powered real-time security monitoring and medical emergency detection system using YOLO Pose Estimation, OpenCV, and Telegram Alerts.

This project detects:
Intruders entering a defined polygon zone
Hands-up gestures (possible threat or compliance signal)
Fainting or fallen persons (medical emergency detection)

It provides:
Real-time audible alerts
Automated Telegram notifications
Live annotated video feed

Features:

Computer Vision
YOLO pose model for human keypoint detection
Bounding box and skeleton visualization
Polygon zone intrusion monitoring

Behavior Detection:
Hands-up gesture detection using wrist–shoulder relation
Faint detection using body aspect ratio, nose vs hip position, and time-based threshold tracking

Alert System:
Real-time sound alerts
Telegram API integration
Message cooldown to prevent spam

Performance Optimization
Frame skipping
Reduced inference resolution
Lightweight alert pipeline

Project Structure
project-folder/
main.py
theft.mp4
README.md
requirements.txt

Requirements:
Python 3.9 or higher

Dependencies:
opencv-python
numpy
supervision
ultralytics
requests
winsound (built-in on Windows)

Model Used:
yolo11m-pose.pt
Ensure the model file exists in the working directory.