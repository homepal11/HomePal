#!/usr/bin/env python3
# mxnf_sensor.py - Основной режим (демонстрационная версия)
import os
import sys
import subprocess
import time
import threading
import requests
import vlc
import speech_recognition as sr
from datetime import datetime
from flask import Flask, request, jsonify, send_file
import numpy as np
import sounddevice as sd
from piper.voice import PiperVoice
import asyncio
import traceback
import cv2
import signal
import atexit
import random

# === Конфигурация (заглушки) ===
RPI3_IP = "192.168.1.XXX"
RPI3_PORT = 8000
RPI3_URL = f"http://{RPI3_IP}:{RPI3_PORT}"
RPI5_IP = "192.168.1.YYY"
VIDEO_SOURCE = "http://192.168.1.XXX:8000/video_feed"
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"

CHECK_INTERVAL = 2
REMINDER_CHECK_INTERVAL = 30

VIDEO_FOLDER = "/path/to/videos"
os.makedirs(VIDEO_FOLDER, exist_ok=True)

app = Flask(__name__)

last_stream = ""
player = None
is_running = True
current_mode = "main"
security_process = None
conversation_process = None
is_recording = False

notifications_history = []
MAX_NOTIFICATIONS = 100

VOICE_PATH = "/path/to/piper/model"
try:
    voice = PiperVoice.load(VOICE_PATH)
    sample_rate = voice.config.sample_rate
    stream = sd.OutputStream(samplerate=sample_rate, channels=1, dtype="int16")
    MAX_GAIN = 1.8
except Exception as e:
    print(f"Voice loading error: {e}")
    voice = None
    stream = None

sensor_cooldowns = {
    "water_alert": 0,
    "gas_alert": 0,
    "water_normal": 0,
    "gas_normal": 0
}
COOLDOWN_DURATION = 30

def check_cooldown(event_type):
    current_time = time.time()
    if current_time - sensor_cooldowns.get(event_type, 0) < COOLDOWN_DURATION:
        print(f"Event {event_type} on cooldown, skipping")
        return False
    sensor_cooldowns[event_type] = current_time
    return True

def add_notification(title, message, type="info", media_url=None, media_type=None):
    global notifications_history
    notification = {
        "id": f"notification_{int(time.time())}",
        "title": title,
        "message": message,
        "type": type,
        "timestamp": datetime.now().isoformat(),
        "hasMedia": media_url is not None,
        "media_type": media_type,
        "media_url": media_url,
        "source": "rpi5"
    }
    notifications_history.insert(0, notification)
    if len(notifications_history) > MAX_NOTIFICATIONS:
        notifications_history.pop()
    print(f"Notification saved: {title}")
    return notification

async def speak_sensor_alert(sensor_type, location=None):
    if voice is None or stream is None:
        print(f"Voice alert: {sensor_type} ALERT!")
        return
    
    phrases = {
        "water": ["Water leak detected!", "Check the plumbing!"],
        "gas": ["Gas leak detected!", "Open windows immediately!"]
    }
    
    selected = phrases.get(sensor_type, ["Alert!"])
    full_text = f"{selected[0]} {selected[1] if len(selected) > 1 else ''}"
    
    try:
        print(f"Speaking: {full_text}")
        if not stream.active:
            stream.start()
        for audio_bytes in voice.synthesize_stream_raw(full_text):
            data = np.frombuffer(audio_bytes, dtype=np.int16)
            boosted = (data.astype(np.float32) * MAX_GAIN).clip(-32767, 32767).astype(np.int16)
            stream.write(boosted)
        stream.stop()
    except Exception as e:
        print(f"Speech error: {e}")

async def speak_sensor_normalized(sensor_type):
    if voice is None or stream is None:
        return
    text = "Water leak resolved." if sensor_type == "water" else "Gas levels normalized."
    try:
        print(f"Speaking: {text}")
        if not stream.active:
            stream.start()
        for audio_bytes in voice.synthesize_stream_raw(text):
            data = np.frombuffer(audio_bytes, dtype=np.int16)
            boosted = (data.astype(np.float32) * MAX_GAIN).clip(-32767, 32767).astype(np.int16)
            stream.write(boosted)
        stream.stop()
    except Exception as e:
        print(f"Speech error: {e}")

async def speak(text: str):
    if voice is None or stream is None:
        print(f"Speech: {text}")
        return
    try:
        if not stream.active:
            stream.start()
        print(f"Speaking: {text}")
        for audio_bytes in voice.synthesize_stream_raw(text):
            data = np.frombuffer(audio_bytes, dtype=np.int16)
            boosted = (data.astype(np.float32) * MAX_GAIN).clip(-32767, 32767).astype(np.int16)
            stream.write(boosted)
        stream.stop()
    except Exception as e:
        print(f"Speech error: {e}")

def send_telegram_message(text):
    print(f"[SIMULATED] Telegram: {text}")

def send_to_pi3(command, data=None):
    print(f"[SIMULATED] Pi3 command: {command}")
    return False

def get_current_stream():
    try:
        r = requests.get(f"{RPI3_URL}/current_stream", timeout=2)
        if r.status_code == 200:
            return r.json().get("stream", "")
        return ""
    except Exception as e:
        return ""

def stream_listener():
    global last_stream, player, is_running
    while is_running:
        try:
            stream_url = get_current_stream()
            if stream_url != last_stream:
                print(f"Stream: {stream_url or 'stopped'}")
                if player:
                    player.stop()
                    player = None
                if stream_url:
                    player = vlc.MediaPlayer(stream_url)
                    player.play()
                last_stream = stream_url
        except Exception as e:
            print(f"Stream error: {e}")
        time.sleep(CHECK_INTERVAL)

def recognize_and_send_task():
    global is_recording
    try:
        if is_recording:
            print("Already recording, skipping...")
            return
        is_recording = True
        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            print("Adjusting for ambient noise...")
            recognizer.adjust_for_ambient_noise(source, duration=1.0)
            print("Speak your task...")
            try:
                audio = recognizer.listen(source, timeout=10, phrase_time_limit=15)
                phrase = recognizer.recognize_google(audio, language="ru-RU").strip()
                print(f"Recognized: {phrase}")
                payload = {"task": phrase}
                r = requests.post(f"{RPI3_URL}/add_reminder", json=payload, timeout=5)
                if r.status_code == 200:
                    print("Task sent to Pi3")
                    asyncio.run(speak(f"Task recorded: {phrase}"))
                else:
                    print(f"Send error: {r.status_code}")
            except sr.WaitTimeoutError:
                print("Voice timeout")
            except sr.UnknownValueError:
                print("Could not understand speech")
    except Exception as e:
        print(f"Recognition error: {e}")
    finally:
        is_recording = False
        print("Recording finished")

def reminder_checker():
    global is_running
    while is_running:
        now = datetime.now().strftime("%H:%M")
        try:
            r = requests.get(f"{RPI3_URL}/reminders", timeout=5)
            if r.status_code == 200:
                tasks = r.json().get("reminders", [])
                for rem in tasks:
                    if rem.get("time") == now and rem.get("time") != "--:--":
                        task_text = rem.get("task")
                        print(f"Reminder: {task_text}")
                        add_notification("REMINDER", task_text, "info")
                        asyncio.run(speak(f"Task: {task_text}"))
                        send_telegram_message(f"Reminder: {task_text}")
                        time.sleep(1)
        except Exception as e:
            print(f"Reminder check error: {e}")
        time.sleep(REMINDER_CHECK_INTERVAL)

def start_security_mode():
    global security_process
    print("Starting security mode...")
    asyncio.run(speak("Starting security mode"))
    send_telegram_message("Security mode started")
    global player
    if player:
        player.stop()
        player = None
    send_to_pi3("open_security")
    security_script = "/path/to/security_script.py"
    security_process = subprocess.Popen([sys.executable, security_script])
    print(f"Security started, PID: {security_process.pid}")
    add_notification("SECURITY", "Security mode activated", "info")
    return True

def stop_security_mode():
    global security_process
    if security_process:
        print(f"Stopping security (PID: {security_process.pid})...")
        security_process.terminate()
        try:
            security_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            security_process.kill()
        security_process = None
    send_to_pi3("close_security")
    print("Security stopped")
    add_notification("SECURITY", "Security mode disabled", "success")

def start_conversation_mode():
    global conversation_process
    print("Starting conversation mode...")
    global player
    if player:
        player.stop()
        player = None
    send_to_pi3("open_conversation")
    conversation_script = "/path/to/conversation_script.py"
    conversation_process = subprocess.Popen([sys.executable, conversation_script])
    print(f"Conversation started, PID: {conversation_process.pid}")
    add_notification("CONVERSATION", "Conversation mode activated", "info")
    return True

def stop_conversation_mode():
    global conversation_process
    if conversation_process:
        print(f"Stopping conversation (PID: {conversation_process.pid})...")
        conversation_process.terminate()
        try:
            conversation_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            conversation_process.kill()
        conversation_process = None
    send_to_pi3("close_conversation")
    print("Conversation stopped")
    add_notification("CONVERSATION", "Conversation mode ended", "info")

@app.route("/health", methods=["GET"])
def health():
    security_active = security_process is not None and security_process.poll() is None
    conversation_active = conversation_process is not None and conversation_process.poll() is None
    return jsonify({
        "status": "ok",
        "mode": "security" if security_active else ("conversation" if conversation_active else "main"),
        "service": "main_module",
        "port": 5000,
        "security_active": security_active,
        "conversation_active": conversation_active,
        "is_recording": is_recording
    }), 200

@app.route("/api/notifications", methods=["GET"])
def get_notifications():
    try:
        limit = request.args.get('limit', default=50, type=int)
        return jsonify({
            "source": "rpi5",
            "notifications": notifications_history[:limit],
            "total": len(notifications_history)
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/notifications/clear", methods=["POST"])
def clear_notifications():
    try:
        notifications_history.clear()
        return jsonify({"status": "cleared"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/videos/<filename>", methods=["GET"])
def get_video(filename):
    try:
        if ".." in filename or "/" in filename:
            return jsonify({"error": "Invalid filename"}), 400
        filepath = os.path.join(VIDEO_FOLDER, filename)
        if os.path.exists(filepath):
            return send_file(filepath,
                           mimetype='video/x-msvideo',
                           as_attachment=False,
                           download_name=filename)
        else:
            return jsonify({"error": "Video not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/sensor_voice_alert", methods=["POST"])
def sensor_voice_alert():
    try:
        data = request.get_json(force=True)
        sensor = data.get("sensor", "")
        event = data.get("event", "")
        location = data.get("location", None)
        print(f"Voice alert received: {sensor} - {event}")
        event_type = f"{sensor}_{event}"
        if not check_cooldown(event_type):
            return jsonify({"status": "cooldown"}), 200
        if event in ["water_leak", "water_alert"]:
            asyncio.run(speak_sensor_alert("water", location))
        elif event in ["gas_alert", "gas_leak"]:
            asyncio.run(speak_sensor_alert("gas", location))
        elif event == "water_normal":
            asyncio.run(speak_sensor_normalized("water"))
        elif event == "gas_normal":
            asyncio.run(speak_sensor_normalized("gas"))
        else:
            return jsonify({"error": "unknown_event"}), 400
        return jsonify({"status": "spoken"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/switch_to_security", methods=["POST"])
def handle_switch_to_security():
    try:
        print("Switching to security mode")
        threading.Thread(target=start_security_mode, daemon=True).start()
        return jsonify({"status": "security_started"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/exit_security", methods=["POST"])
def handle_exit_security():
    try:
        print("Exiting security mode")
        stop_security_mode()
        return jsonify({"status": "security_stopped"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/start_conversation", methods=["POST"])
def handle_start_conversation():
    try:
        print("Starting conversation mode")
        threading.Thread(target=start_conversation_mode, daemon=True).start()
        return jsonify({"status": "conversation_started"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/stop_conversation", methods=["POST"])
def handle_stop_conversation():
    try:
        print("Stopping conversation mode")
        stop_conversation_mode()
        return jsonify({"status": "conversation_stopped"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/check_password", methods=["POST"])
def handle_check_password():
    try:
        data = request.get_json(force=True)
        password = data.get("password", "")
        print(f"Password check: {password}")
        if password == "123456":  # Demo password
            print("Correct password")
            add_notification("SECURITY", "Security disabled by password", "success")
            if security_process:
                stop_security_mode()
            send_telegram_message("Security disabled by password")
            return jsonify({"status": "correct"}), 200
        else:
            return jsonify({"status": "incorrect"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/start_recording", methods=["POST"])
def handle_start_recording():
    global is_recording
    if is_recording:
        return jsonify({"status": "already_recording"}), 200
    print("Starting voice reminder recording...")
    threading.Thread(target=recognize_and_send_task, daemon=True).start()
    return jsonify({"status": "recording_started"}), 200

@app.route("/speak_task", methods=["POST"])
def handle_speak_task():
    try:
        data = request.get_json(force=True)
        task = data.get("task", "")
        if task:
            print(f"Speaking task: {task}")
            asyncio.run(speak(f"Task: {task}"))
            return jsonify({"status": "spoken"}), 200
        return jsonify({"error": "No task"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/sensor_event", methods=["POST"])
def sensor_event():
    try:
        data = request.get_json(force=True)
        event = data.get("event")
        source = data.get("source", "unknown")
        print(f"Sensor event from {source}: {event}")
        if not check_cooldown(event):
            return jsonify({"status": "cooldown"}), 200
        if event == "water_leak":
            threading.Thread(target=lambda: asyncio.run(speak_sensor_alert("water")), daemon=True).start()
        elif event == "gas_alert":
            threading.Thread(target=lambda: asyncio.run(speak_sensor_alert("gas")), daemon=True).start()
        elif event == "water_normal":
            threading.Thread(target=lambda: asyncio.run(speak_sensor_normalized("water")), daemon=True).start()
        elif event == "gas_normal":
            threading.Thread(target=lambda: asyncio.run(speak_sensor_normalized("gas")), daemon=True).start()
        else:
            return jsonify({"error": "Unknown event"}), 400
        return jsonify({"status": "processed"}), 200
    except Exception as e:
        print(f"Sensor event error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/record_video", methods=["POST"])
def record_video():
    def record():
        try:
            timestamp = int(time.time())
            filename = f"video_{timestamp}.avi"
            filepath = os.path.join(VIDEO_FOLDER, filename)
            print(f"Recording video: {filepath}")
            cap = cv2.VideoCapture(VIDEO_SOURCE)
            if not cap.isOpened():
                print("Failed to open video stream")
                return
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            fps = 20.0
            frame_size = (640, 480)
            out = cv2.VideoWriter(filepath, fourcc, fps, frame_size)
            start_time = time.time()
            frame_count = 0
            while time.time() - start_time < 10:
                ret, frame = cap.read()
                if ret:
                    resized_frame = cv2.resize(frame, frame_size)
                    out.write(resized_frame)
                    frame_count += 1
                else:
                    time.sleep(0.05)
            cap.release()
            out.release()
            print(f"Video saved: {filepath} ({frame_count} frames)")
            try:
                with open(filepath, "rb") as f:
                    print("Video saved, would send to Telegram in production")
            except Exception as e:
                print(f"Video processing error: {e}")
            video_url = f"http://{RPI5_IP}:5000/videos/{filename}"
            add_notification(
                title="VIDEO",
                message="Video recording",
                type="info",
                media_url=video_url,
                media_type="video"
            )
            print(f"Video URL: {video_url}")
        except Exception as e:
            print(f"Video recording error: {e}")
    threading.Thread(target=record, daemon=True).start()
    return jsonify({"status": "recording"}), 200

def cleanup():
    global is_running, player, security_process, conversation_process, stream
    is_running = False
    if security_process:
        stop_security_mode()
    if conversation_process:
        stop_conversation_mode()
    if player:
        try:
            player.stop()
        except Exception:
            pass
    if stream:
        try:
            if stream.active:
                stream.stop()
            stream.close()
        except Exception:
            pass
    print("Main module shutting down")

def signal_handler(signum, frame):
    print(f"Signal {signum} received")
    cleanup()
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup)
    
    try:
        print("=" * 50)
        print("MAIN MODULE - DEMONSTRATION VERSION")
        print("=" * 50)
        print("Port: 5000")
        print("Radio: active")
        print("Reminders: active")
        print("Voice reminders: enabled")
        print("Sensor voice: enabled")
        print("Video: enabled")
        print("=" * 50)
        
        stream_thread = threading.Thread(target=stream_listener, daemon=True)
        reminder_thread = threading.Thread(target=reminder_checker, daemon=True)
        stream_thread.start()
        reminder_thread.start()
        
        print("System started")
        app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        print(f"Critical error: {e}")
        traceback.print_exc()
    finally:
        cleanup()