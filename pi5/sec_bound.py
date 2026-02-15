#!/usr/bin/env python3
# sec_bound.py - Режим охраны (демонстрационная версия)
import os
import sys
import time
import threading
import cv2
import requests
import json
from datetime import datetime

# Добавляем импорт для распознавания лиц
sys.path.append('/home/pi3/fall_detection_DL')
from facial_recognition import FaceRecognition

# --- КОНФИГУРАЦИЯ (ЗАГЛУШКИ) ---
PI3_IP = "192.168.1.XXX"  # Замените на реальный IP
PI3_PORT = 8000
PI3_URL = f"http://{PI3_IP}:{PI3_PORT}"
STREAM_URL = "http://192.168.1.XXX:8000/video_feed"  # Замените на реальный URL
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Токен Telegram бота
CHAT_ID = "YOUR_CHAT_ID_HERE"  # ID чата Telegram
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Тайминги
EXIT_BUTTON_TIMEOUT = 100
MONITORING_START_DELAY = 100

# Параметры распознавания лиц
RECOGNITION_INTERVAL = 1
FACE_DETECTION_CONFIDENCE = 0.5
MASTER_FACE_NAME = "master"

# --- Глобальные переменные ---
is_running = True
face_recognizer = None
last_recognition_time = 0
master_detected = False

# --- Утилиты (заглушки) ---
def send_telegram_message(text):
    print(f"[SIMULATED] Telegram: {text}")
    return None

def send_telegram_video(video_path):
    print(f"[SIMULATED] Video sent to Telegram: {video_path}")
    return None

def send_to_pi3(command, data=None):
    print(f"[SIMULATED] Pi3 command: {command}")
    return False

def init_face_recognition():
    global face_recognizer
    try:
        print("Initializing face recognition...")
        face_recognizer = FaceRecognition()
        face_recognizer.encode_faces()
        return True
    except Exception as e:
        print(f"Face recognition init error: {e}")
        return False

def check_for_face(frame):
    global last_recognition_time, master_detected
    current_time = time.time()
    if current_time - last_recognition_time < RECOGNITION_INTERVAL:
        return False
    last_recognition_time = current_time
    try:
        face_names = face_recognizer.recognize_face(frame)
        if face_names:
            print(f"Faces detected: {', '.join(face_names)}")
            if MASTER_FACE_NAME in face_names:
                print(f"Master detected!")
                master_detected = True
                return True
    except Exception as e:
        print(f"Face recognition error: {e}")
    return False

def motion_detection_with_face_recognition(cap):
    global is_running, master_detected
    print("Starting motion detection...")
    
    for _ in range(10):
        cap.read()
    
    ret, prev_frame = cap.read()
    if not ret:
        print("Failed to get first frame")
        return
    
    prev_frame = cv2.resize(prev_frame, (640, 480))
    recording = False
    out = None
    video_path = None
    start_rec_time = None
    frame_count = 0
    
    try:
        while is_running and cap.isOpened() and not master_detected:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            frame_res = cv2.resize(frame, (640, 480))
            
            if check_for_face(frame_res):
                print("Master detected - stopping monitoring")
                break
            
            if not recording:
                diff = cv2.absdiff(prev_frame, frame_res)
                gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
                blur = cv2.GaussianBlur(gray, (5, 5), 0)
                _, thresh = cv2.threshold(blur, 30, 255, cv2.THRESH_BINARY)
                dilated = cv2.dilate(thresh, None, iterations=2)
                contours, _ = cv2.findContours(dilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
                
                if len(contours) > 2:
                    print("Motion detected! Starting recording...")
                    send_telegram_message("Motion detected!")
                    
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    os.makedirs("recordings", exist_ok=True)
                    video_path = f"recordings/intrusion_{timestamp}.avi"
                    
                    fourcc = cv2.VideoWriter_fourcc(*'XVID')
                    out = cv2.VideoWriter(video_path, fourcc, 15.0, (640, 480))
                    recording = True
                    start_rec_time = time.time()
                    out.write(prev_frame)
            else:
                out.write(frame_res)
                elapsed = time.time() - start_rec_time
                
                if elapsed % 2 < RECOGNITION_INTERVAL:
                    if check_for_face(frame_res):
                        print("Master detected - stopping recording")
                        break
                
                if elapsed >= 30:
                    print("Intrusion confirmed! Sending video.")
                    out.release()
                    out = None
                    send_telegram_video(video_path)
                    send_telegram_message("Intrusion! Video sent.")
                    break
            
            prev_frame = frame_res
            
            if frame_count % 200 == 0:
                print("Monitoring active...")
            
            time.sleep(0.05)
    
    except KeyboardInterrupt:
        print("Monitoring interrupted")
    except Exception as e:
        print(f"Monitoring error: {e}")
    finally:
        if out is not None:
            out.release()

def exit_security_system(reason="normal completion"):
    global is_running
    print(f"Security system shutdown: {reason}")
    is_running = False
    send_to_pi3("close_security")
    send_telegram_message("Security system disabled.")

def main():
    global is_running, master_detected
    
    print("=" * 60)
    print("SECURITY MODE - DEMONSTRATION VERSION")
    print("=" * 60)
    print(f"Timeout: {EXIT_BUTTON_TIMEOUT} seconds")
    print(f"Monitoring starts after: {MONITORING_START_DELAY} seconds")
    print("=" * 60)
    
    init_face_recognition()
    send_telegram_message("Security system started.")
    
    print("Countdown started...")
    try:
        for i in range(EXIT_BUTTON_TIMEOUT, 0, -1):
            if not is_running:
                return
            if i % 10 == 0 or i <= 5:
                print(f"Time remaining: {i} seconds...")
            time.sleep(1)
    except KeyboardInterrupt:
        print("Interrupted by user")
        exit_security_system("interrupted")
        return
    
    print("=" * 60)
    print("TIME EXPIRED! SYSTEM ACTIVATED")
    print("=" * 60)
    
    send_to_pi3("hide_exit_button")
    send_telegram_message("Security system fully activated.")
    
    print("Connecting to video stream...")
    cap = cv2.VideoCapture(STREAM_URL)
    
    if not cap.isOpened():
        print("Failed to open video stream")
        send_telegram_message("Error: failed to open video stream.")
        exit_security_system("video stream error")
        return
    
    print("Video stream connected")
    motion_detection_with_face_recognition(cap)
    cap.release()
    
    if master_detected:
        exit_security_system("master detected")
    else:
        exit_security_system("normal completion")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted by user")
        exit_security_system("interrupted")
    except Exception as e:
        print(f"Critical error: {e}")
        exit_security_system("critical error")
    finally:
        print("sec_bound.py terminated")