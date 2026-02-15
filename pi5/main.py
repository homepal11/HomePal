# main.py - Основной модуль (демонстрационная версия)
import cv2
import numpy as np
import mediapipe as mp
import facial_recognition as fr
from time import time
import requests
import subprocess
import sys
import threading
from flask import Flask

# --- Конфигурация (заглушки) ---
TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"
TELEGRAM_URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

def send_telegram_alert(message):
    print(f"[SIMULATED] Telegram alert: {message}")

# --- Flask server ---
app = Flask(__name__)
switch_requested = False

@app.route("/switch_code", methods=["POST"])
def switch_code():
    global switch_requested
    print("Switch request received")
    switch_requested = True
    return "Switching...", 200

def run_server():
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()

# --- Initialize modules ---
frr = fr.FaceRecognition()
frr.encode_faces()

pose_video = mp.solutions.pose.Pose(
    static_image_mode=False,
    min_detection_confidence=0.7,
    model_complexity=2
)

stream_url = "http://192.168.1.XXX:8000/video_feed"
video = cv2.VideoCapture(stream_url)

previous_avg_shoulder_height = 0
time1 = 0
fall_reported = False

def detectPose(frame, pose_model):
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = pose_model.process(frame_rgb)
    height, width, _ = frame.shape
    landmarks = []
    if results.pose_landmarks:
        for landmark in results.pose_landmarks.landmark:
            landmarks.append((int(landmark.x * width),
                              int(landmark.y * height),
                              landmark.z * width))
        return landmarks
    return None

def detectFall(landmarks, previous_avg_shoulder_height):
    left_shoulder_y = landmarks[11][1]
    right_shoulder_y = landmarks[12][1]
    avg_shoulder_y = (left_shoulder_y + right_shoulder_y) / 2
    if previous_avg_shoulder_height == 0:
        return False, avg_shoulder_y
    fall_threshold = previous_avg_shoulder_height * 1.5
    if avg_shoulder_y > fall_threshold:
        return True, avg_shoulder_y
    return False, avg_shoulder_y

print("Starting fall and face detection...")

while video.isOpened():
    if switch_requested:
        print("Switching to other module...")
        video.release()
        cv2.destroyAllWindows()
        subprocess.Popen([sys.executable, "/path/to/other_module.py"])
        sys.exit(0)

    ret, frame = video.read()
    if not ret:
        print("Failed to fetch frame")
        break

    landmarks = detectPose(frame, pose_video)
    face_names = frr.recognize_face(frame)

    if face_names:
        print("Detected faces:", face_names)

    time2 = time()
    if (time2 - time1) > 2:
        if landmarks:
            fall_detected, previous_avg_shoulder_height = detectFall(
                landmarks, previous_avg_shoulder_height
            )
            if fall_detected and not fall_reported:
                print("Fall detected!")
                send_telegram_alert("Fall detected!")
                fall_reported = True
            elif not fall_detected:
                fall_reported = False
        time1 = time2

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

video.release()
cv2.destroyAllWindows()