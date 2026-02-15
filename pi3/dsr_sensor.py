#!/usr/bin/env python3
# dsr_sensor.py - Pi3 интерфейс (демонстрационная версия)
import pygame
import sys
import threading
import math
import random
import time
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
import requests
import json
import serial
import serial.tools.list_ports
from collections import deque
from threading import Lock

# --- Конфигурация (заглушки) ---
PI5_IP = "192.168.1.YYY"
PI5_MAIN_URL = f"http://{PI5_IP}:5000"
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"
SECRET_CODE = "123456"

FLASK_PORT = 8000

ARDUINO_PORT = '/dev/ttyACM0'
ARDUINO_BAUDRATE = 9600
ARDUINO_UPDATE_INTERVAL = 2

WATER_MIN_DURATION = 5
GAS_MIN_DURATION = 10
NOTIFICATION_COOLDOWN = 300

notifications_history = deque(maxlen=100)

sensor_status = {
    'water': {
        'current': 'normal',
        'last_change': None,
        'detected_time': None,
        'last_notification': None,
        'last_voice_alert': None,
        'lock': Lock()
    },
    'gas': {
        'current': 'normal',
        'last_change': None,
        'detected_time': None,
        'last_notification': None,
        'last_voice_alert': None,
        'lock': Lock()
    }
}

sensor_history = deque(maxlen=100)

sensor_config = {
    'water_enabled': True,
    'gas_enabled': False,
    'telegram_enabled': True,
    'voice_enabled': True,
    'min_duration': {
        'water': WATER_MIN_DURATION,
        'gas': GAS_MIN_DURATION
    },
    'cooldown': NOTIFICATION_COOLDOWN,
    'voice_cooldown': 60
}

arduino_connected = False
last_arduino_data = None
last_arduino_check = 0
arduino_check_interval = 10

last_water = "NORMAL"
last_gas = "SAFE"

security_code_input = ""
security_attempts = 0
security_max_attempts = 3
exit_button_visible = True
security_active = False
pi5_security_mode = False
pi5_conversation_mode = False

reminders = [
    ("08:00", "Breakfast and vitamins"),
    ("10:00", "Walk"),
    ("12:00", "Medication A"),
    ("14:00", "Lunch"),
    ("15:00", "Afternoon rest"),
    ("16:30", "Snack"),
    ("18:00", "Medication B"),
    ("19:00", "Dinner")
]

show_modal = False
edit_mode = False
edit_index = -1
edit_hours = 12
edit_minutes = 0
scroll_y = 0

alert_windows = []
alert_cooldown = {}
MIN_ALERT_INTERVAL = 30

HOLD_TIME_REQUIRED = 0.3
holding_buttons = {}

current_mode = "MAIN"
current_stream = ""
is_animating = False
is_listening_mode = False
wave_offset = 0
heights = [0] * 80
conversation_ui_elements = {}
last_connection_check = 0
connection_check_interval = 10
connection_status = "✓"

def init_arduino():
    global arduino_connected, ser
    try:
        ser = serial.Serial(ARDUINO_PORT, ARDUINO_BAUDRATE, timeout=1)
        time.sleep(2)
        arduino_connected = True
        print(f"Arduino connected on {ARDUINO_PORT}")
        return True
    except Exception as e:
        print(f"Arduino connection error: {e}")
        arduino_connected = False
        return False

def send_to_pi5_for_alert(sensor_type):
    try:
        event_type = "water_leak" if sensor_type == 'water' else "gas_alert"
        url = f"{PI5_MAIN_URL}/sensor_event"
        payload = {"event": event_type, "source": "RPI3"}
        response = requests.post(url, json=payload, timeout=3)
        print(f"Event sent to Pi5: {event_type}")
        return response
    except Exception as e:
        print(f"Error sending to Pi5: {e}")
        return None

def send_telegram_message(text):
    print(f"[SIMULATED] Telegram: {text}")
    return None

def add_notification(title, message, type="info", media_url=None, media_type=None):
    global notifications_history
    notification = {
        "id": f"notification_{int(time.time())}",
        "title": title,
        "message": message,
        "type": type,
        "timestamp": datetime.now().isoformat(),
        "media_url": media_url,
        "media_type": media_type,
        "source": "rpi3"
    }
    notifications_history.appendleft(notification)
    print(f"Notification saved: {title}")
    return notification

class AlertWindow:
    def __init__(self, message, alert_type="warning", duration=10):
        self.message = message
        self.type = alert_type
        self.start_time = time.time()
        self.duration = duration
        self.closed = False
        self.color = self.get_color()
        self.lines = self.wrap_text(message, 40)
        self.line_height = 35
        self.padding = 25
        self.width = min(600, SCREEN_WIDTH - 100)
        self.height = 150 + len(self.lines) * self.line_height
        self.x = (SCREEN_WIDTH - self.width) // 2
        self.y = (SCREEN_HEIGHT - self.height) // 2
        self.close_btn_size = 30
        self.close_btn_rect = pygame.Rect(
            self.x + self.width - self.close_btn_size - 10,
            self.y + 10,
            self.close_btn_size,
            self.close_btn_size
        )
    
    def get_color(self):
        colors = {
            "danger": (220, 53, 69),
            "warning": (255, 193, 7),
            "info": (23, 162, 184),
            "success": (40, 167, 69)
        }
        return colors.get(self.type, colors["warning"])
    
    def wrap_text(self, text, max_chars):
        words = text.split()
        lines = []
        current_line = []
        for word in words:
            test_line = ' '.join(current_line + [word])
            if len(test_line) <= max_chars:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        if current_line:
            lines.append(' '.join(current_line))
        return lines
    
    def update(self):
        if time.time() - self.start_time > self.duration:
            self.closed = True
        return not self.closed
    
    def draw(self, surface):
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))
        window_rect = pygame.Rect(self.x, self.y, self.width, self.height)
        pygame.draw.rect(surface, (255, 255, 255), window_rect, border_radius=20)
        pygame.draw.rect(surface, self.color, window_rect, 4, border_radius=20)
        y_offset = self.y + 70
        for line in self.lines:
            font = pygame.font.SysFont("arial", 20)
            line_text = font.render(line, True, (40, 40, 40))
            surface.blit(line_text, (self.x + (self.width - line_text.get_width()) // 2, y_offset))
            y_offset += self.line_height
        pygame.draw.rect(surface, self.color, self.close_btn_rect, border_radius=5)
        close_font = pygame.font.SysFont("arial", 25, bold=True)
        close_text = close_font.render("×", True, (255, 255, 255))
        surface.blit(close_text, close_text.get_rect(center=self.close_btn_rect.center))
    
    def handle_click(self, pos):
        if self.close_btn_rect.collidepoint(pos):
            self.closed = True
            return True
        return False

def show_alert_window(message, alert_type="warning"):
    global alert_windows
    current_time = time.time()
    message_hash = hash(message)
    if message_hash in alert_cooldown:
        if current_time - alert_cooldown[message_hash] < MIN_ALERT_INTERVAL:
            print(f"Skipping duplicate alert: {message}")
            return False
    alert_window = AlertWindow(message, alert_type, duration=10)
    alert_windows.append(alert_window)
    alert_cooldown[message_hash] = current_time
    if len(alert_cooldown) > 50:
        oldest_key = min(alert_cooldown, key=alert_cooldown.get)
        alert_cooldown.pop(oldest_key, None)
    print(f"Showing alert: {message}")
    return True

def read_sensor_data():
    global last_water, last_gas, arduino_connected, last_arduino_data
    if not arduino_connected:
        return
    try:
        ser.reset_input_buffer()
        time.sleep(0.1)
        line = ser.readline().decode("utf-8").strip()
        if len(line) == 2 and line.isdigit():
            water_ok = line[0] == "1"
            gas_ok = line[1] == "1"
            water_status = "LEAK DETECTED" if water_ok else "NORMAL"
            gas_status = "ALERT" if gas_ok else "SAFE"
            last_arduino_data = time.time()
            if water_status == "LEAK DETECTED" and last_water != "LEAK DETECTED":
                print("Water leak detected!")
                update_sensor_status('water', 'alert')
            elif water_status == "NORMAL" and last_water == "LEAK DETECTED":
                print("Water leak resolved")
                update_sensor_status('water', 'normal')
                try:
                    url = f"{PI5_MAIN_URL}/sensor_event"
                    payload = {"event": "water_normal", "source": "RPI3"}
                    response = requests.post(url, json=payload, timeout=3)
                except Exception as e:
                    print(f"Error sending to Pi5: {e}")
            last_water = water_status
            log_sensor_event('system', 'read', f"water={water_status}")
    except Exception as e:
        print(f"Arduino read error: {e}")
        arduino_connected = False

def arduino_loop():
    print("Starting Arduino monitoring...")
    if not init_arduino():
        print("Arduino not connected, running without sensors")
        return
    while True:
        read_sensor_data()
        time.sleep(2)

def update_sensor_status(sensor_type, new_state):
    global sensor_status
    if sensor_type == 'gas' and not sensor_config['gas_enabled']:
        print(f"Gas sensor disabled, ignoring event: {new_state}")
        return False
    with sensor_status[sensor_type]['lock']:
        current_time = time.time()
        current_state = sensor_status[sensor_type]['current']
        if new_state == current_state:
            return False
        print(f"Sensor {sensor_type}: {current_state} -> {new_state}")
        log_sensor_event(sensor_type, current_state, new_state)
        sensor_status[sensor_type]['current'] = new_state
        sensor_status[sensor_type]['last_change'] = current_time
        if new_state == 'alert':
            sensor_status[sensor_type]['detected_time'] = current_time
            if sensor_type == 'water':
                show_alert_window("Water leak detected!", "warning")
                add_notification("WATER LEAK", "Water leak detected!", "danger")
                telegram_ok = (sensor_status[sensor_type]['last_notification'] is None or 
                             (current_time - sensor_status[sensor_type]['last_notification']) > sensor_config['cooldown'])
                voice_ok = (sensor_status[sensor_type]['last_voice_alert'] is None or 
                           (current_time - sensor_status[sensor_type]['last_voice_alert']) > sensor_config['voice_cooldown'])
                handle_sensor_alert(sensor_type, telegram_ok, voice_ok)
                if telegram_ok:
                    sensor_status[sensor_type]['last_notification'] = current_time
                if voice_ok:
                    sensor_status[sensor_type]['last_voice_alert'] = current_time
                return True
        elif new_state == 'normal' and current_state == 'alert':
            if sensor_type == 'water':
                duration = current_time - sensor_status[sensor_type]['detected_time']
                print(f"Leak duration: {duration:.1f} seconds")
                if duration < sensor_config['min_duration']['water']:
                    print(f"Leak too short ({duration:.1f}s), ignoring normalization")
                    sensor_status[sensor_type]['current'] = 'alert'
                    return False
            add_notification("WATER NORMAL", "Water leak resolved", "success")
            handle_sensor_normalized(sensor_type)
            return True
    return False

def log_sensor_event(sensor_type, old_state, new_state):
    event = {
        'timestamp': datetime.now().isoformat(),
        'sensor': sensor_type,
        'old_state': old_state,
        'new_state': new_state,
        'type': 'state_change'
    }
    sensor_history.append(event)
    print(f"Logging: {sensor_type}: {old_state} -> {new_state}")

def handle_sensor_alert(sensor_type, send_telegram=True, send_voice=True):
    current_time = time.time()
    if sensor_type == 'gas' and not sensor_config['gas_enabled']:
        print(f"Gas sensor disabled, ignoring alert")
        return False
    print(f"{sensor_type.upper()} ALERT! Sending notifications...")
    if send_telegram and sensor_config['telegram_enabled']:
        message = "Water leak detected!" if sensor_type == 'water' else "Gas detected!"
        threading.Thread(target=send_telegram_message, args=(message,)).start()
    if send_voice and sensor_config['voice_enabled']:
        try:
            event_type = "water_leak" if sensor_type == 'water' else "gas_alert"
            url = f"{PI5_MAIN_URL}/sensor_event"
            payload = {"event": event_type, "source": "RPI3"}
            threading.Thread(
                target=send_to_pi5,
                args=(url, payload)
            ).start()
        except Exception as e:
            print(f"Voice alert error: {e}")
    return True

def handle_sensor_normalized(sensor_type):
    if sensor_type == 'gas' and not sensor_config['gas_enabled']:
        print(f"Gas sensor disabled, ignoring normalization")
        return
    print(f"Processing normalization for {sensor_type}")
    if sensor_config['telegram_enabled']:
        message = "Water leak resolved" if sensor_type == 'water' else "Gas levels normalized"
        threading.Thread(target=send_telegram_message, args=(message,)).start()

def send_to_pi5(url, data):
    try:
        print(f"Sending to Pi5: {url}")
        response = requests.post(url, json=data, timeout=3)
        print(f"Sent to Pi5: {url}, status: {response.status_code if response else 'no response'}")
        return response
    except Exception as e:
        print(f"Failed to send to Pi5: {e}")
        return None

def check_arduino_connection():
    global arduino_connected
    if last_arduino_data:
        time_since_last = time.time() - last_arduino_data
        if time_since_last > 30:
            if arduino_connected:
                print("Arduino not responding for 30 seconds")
                arduino_connected = False
                add_notification("ARDUINO", "Arduino disconnected", "warning")
                send_telegram_message("Arduino disconnected")
    else:
        arduino_connected = False

app = Flask(__name__)

@app.route("/current_stream")
def get_stream():
    return jsonify({"stream": current_stream})

@app.route("/add_reminder", methods=['POST'])
def add_reminder():
    global reminders, show_modal, scroll_y, edit_mode, edit_index, edit_hours, edit_minutes
    try:
        data = request.json
        task = data.get("task", "")
        if task:
            reminders.insert(0, ("--:--", task))
            sort_reminders()
            show_modal = True
            scroll_y = 0
            for i, (t, t_task) in enumerate(reminders):
                if t == "--:--" and t_task == task:
                    edit_index = i
                    now = datetime.now()
                    edit_hours = now.hour
                    edit_minutes = now.minute
                    edit_mode = True
                    print(f"Auto-opened editor for new reminder at index {i}")
                    break
            return jsonify({"status": "added", "task": task}), 200
        return jsonify({"error": "No task provided"}), 400
    except Exception as e:
        print(f"Error adding reminder: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/reminders")
def get_reminders():
    try:
        reminders_list = []
        for time_str, task in reminders:
            reminders_list.append({"time": time_str, "task": task})
        return jsonify({"reminders": reminders_list}), 200
    except Exception as e:
        print(f"Error getting reminders: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/set_ui_status', methods=['POST'])
def set_status():
    global is_animating, is_listening_mode, current_mode
    try:
        data = request.json
        status = data.get("status")
        if status == "speaking":
            is_animating = True
        elif status == "idle":
            is_animating = False
        elif status == "start":
            is_listening_mode = True
            current_mode = "CONVERSATION"
        elif status == "stop":
            is_listening_mode = False
            is_animating = False
            current_mode = "MAIN"
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"Flask error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/sensor_status", methods=['GET'])
def get_sensor_status():
    status = {}
    for sensor_type, data in sensor_status.items():
        with data['lock']:
            status[sensor_type] = {
                'state': data['current'],
                'last_change': data['last_change'],
                'detected_time': data['detected_time'],
                'last_notification': data['last_notification'],
                'last_voice_alert': data['last_voice_alert'],
                'arduino_connected': arduino_connected,
                'enabled': sensor_config[f"{sensor_type}_enabled"]
            }
    return jsonify({
        'sensors': status,
        'timestamp': datetime.now().isoformat(),
        'arduino_connected': arduino_connected,
        'last_data': last_arduino_data,
        'note': 'Gas sensor disabled'
    })

@app.route("/sensor_history", methods=['GET'])
def get_sensor_history():
    limit = request.args.get('limit', default=50, type=int)
    history_list = list(sensor_history)[-limit:] if sensor_history else []
    return jsonify({
        'history': history_list,
        'total': len(sensor_history),
        'limit': limit
    })

@app.route("/sensor_events", methods=['GET'])
def get_sensor_events():
    n = request.args.get('n', default=10, type=int)
    event_type = request.args.get('type', default=None)
    events = []
    for event in reversed(list(sensor_history)):
        if event_type is None or event['sensor'] == event_type:
            events.append(event)
            if len(events) >= n:
                break
    return jsonify({'events': events})

@app.route("/reset_sensor_alerts", methods=['POST'])
def reset_sensor_alerts():
    try:
        for sensor_type in ['water', 'gas']:
            with sensor_status[sensor_type]['lock']:
                sensor_status[sensor_type]['current'] = 'normal'
                sensor_status[sensor_type]['last_notification'] = None
                sensor_status[sensor_type]['last_voice_alert'] = None
                sensor_status[sensor_type]['detected_time'] = None
        log_sensor_event('system', 'alert', 'normal')
        return jsonify({'status': 'reset', 'message': 'Alerts reset'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/sensor_test", methods=['POST'])
def sensor_test():
    try:
        data = request.json
        sensor_type = data.get('sensor', 'water')
        state = data.get('state', 'alert')
        if sensor_type in ['water', 'gas']:
            if sensor_type == 'gas' and not sensor_config['gas_enabled']:
                return jsonify({'status': 'ignored', 'message': 'Gas sensor disabled'}), 200
            update_sensor_status(sensor_type, state)
            return jsonify({'status': 'test_executed', 'sensor': sensor_type, 'state': state}), 200
        else:
            return jsonify({'error': 'Invalid sensor type'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/sensor_config", methods=['GET', 'POST'])
def handle_sensor_config():
    if request.method == 'GET':
        return jsonify(sensor_config)
    elif request.method == 'POST':
        try:
            data = request.json
            allowed_fields = ['water_enabled', 'gas_enabled', 'telegram_enabled', 'voice_enabled']
            for field in allowed_fields:
                if field in data:
                    sensor_config[field] = bool(data[field])
            if 'min_duration' in data:
                for sensor_type, duration in data['min_duration'].items():
                    if sensor_type in ['water', 'gas']:
                        sensor_config['min_duration'][sensor_type] = max(1, int(duration))
            if 'cooldown' in data:
                sensor_config['cooldown'] = max(60, int(data['cooldown']))
            if 'voice_cooldown' in data:
                sensor_config['voice_cooldown'] = max(10, int(data['voice_cooldown']))
            return jsonify({'status': 'updated', 'config': sensor_config}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@app.route("/sensor_event", methods=['POST'])
def sensor_event():
    try:
        data = request.json
        event_type = data.get("event", "")
        source = data.get("source", "external")
        print(f"Event received from {source}: {event_type}")
        if event_type == "water_leak":
            update_sensor_status('water', 'alert')
            return jsonify({"status": "processed", "sensor": "water"}), 200
        elif event_type == "gas_alert":
            print("Gas sensor disabled, ignoring gas_alert")
            return jsonify({"status": "ignored", "reason": "gas_sensor_disabled"}), 200
        elif event_type == "water_normal":
            update_sensor_status('water', 'normal')
            return jsonify({"status": "processed", "sensor": "water"}), 200
        elif event_type == "gas_normal":
            print("Gas sensor disabled, ignoring gas_normal")
            return jsonify({"status": "ignored", "reason": "gas_sensor_disabled"}), 200
        else:
            print(f"Unknown event: {event_type}")
            return jsonify({"status": "ignored", "reason": "unknown_event"}), 200
    except Exception as e:
        print(f"Error in sensor_event: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/pi5_command", methods=['POST'])
def pi5_command():
    global current_mode, security_code_input, security_attempts, exit_button_visible, security_active, pi5_security_mode, pi5_conversation_mode
    try:
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({"error": "Invalid JSON"}), 400
        cmd = data.get("command")
        if cmd == "open_security":
            print("Command: open_security")
            current_mode = "SECURITY"
            security_code_input = ""
            security_attempts = 0
            exit_button_visible = True
            security_active = True
            pi5_security_mode = True
            return jsonify({"status": "security_opened"}), 200
        elif cmd == "hide_exit_button":
            print("Command: hide_exit_button")
            exit_button_visible = False
            return jsonify({"status": "exit_button_hidden"}), 200
        elif cmd == "close_security":
            print("Command: close_security")
            if current_mode == "SECURITY":
                current_mode = "MAIN"
            security_code_input = ""
            security_attempts = 0
            security_active = False
            pi5_security_mode = False
            return jsonify({"status": "security_closed"}), 200
        elif cmd == "open_conversation":
            print("Command: open_conversation")
            current_mode = "CONVERSATION"
            is_listening_mode = False
            pi5_conversation_mode = True
            return jsonify({"status": "conversation_opened"}), 200
        elif cmd == "close_conversation":
            print("Command: close_conversation")
            if current_mode == "CONVERSATION":
                current_mode = "MAIN"
            is_listening_mode = False
            is_animating = False
            pi5_conversation_mode = False
            return jsonify({"status": "conversation_closed"}), 200
        else:
            print(f"Unknown command: {cmd}")
            return jsonify({"error": f"Unknown command: {cmd}"}), 400
    except Exception as e:
        print(f"Error processing command: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/health", methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "pi3_interface",
        "port": FLASK_PORT,
        "current_mode": current_mode,
        "security_active": security_active,
        "conversation_active": pi5_conversation_mode,
        "arduino_connected": arduino_connected,
        "sensors": {k: v['current'] for k, v in sensor_status.items()},
        "note": "Gas sensor disabled"
    }), 200

@app.route("/show_alert", methods=["POST"])
def show_alert():
    try:
        data = request.json
        message = data.get("message", "Reminder!")
        alert_type = data.get("type", "info")
        print(f"Show alert command: {message}")
        show_alert_window(message, alert_type)
        return jsonify({"status": "alert_shown"}), 200
    except Exception as e:
        print(f"Error showing alert: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/notifications", methods=["GET"])
def get_notifications():
    try:
        limit = request.args.get('limit', default=50, type=int)
        notifications_list = list(notifications_history)[:limit]
        return jsonify({
            "source": "rpi3",
            "notifications": notifications_list,
            "total": len(notifications_history)
        }), 200
    except Exception as e:
        print(f"Error getting notifications: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/notifications/clear", methods=["POST"])
def clear_notifications():
    try:
        notifications_history.clear()
        return jsonify({"status": "cleared"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def run_flask():
    print(f"Pi3 Flask server running on port {FLASK_PORT}")
    print("Sensor API endpoints:")
    print("  GET  /sensor_status       - sensor status")
    print("  GET  /sensor_history      - event history")
    print("  GET  /sensor_events       - recent events")
    print("  POST /reset_sensor_alerts - reset alerts")
    print("  POST /sensor_test         - test events")
    print("  GET/POST /sensor_config   - configuration")
    print("  POST /sensor_event        - receive events")
    print("  GET  /api/notifications   - Android notifications")
    print("  Note: Gas sensor disabled")
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=False, use_reloader=False)

def safe_post(url, json_data=None, timeout=3):
    try:
        if json_data:
            response = requests.post(url, json=json_data, timeout=timeout)
            return response
        else:
            response = requests.post(url, timeout=timeout)
            return response
    except Exception as e:
        return None

def safe_get(url, timeout=3):
    try:
        response = requests.get(url, timeout=timeout)
        return response
    except Exception as e:
        return None

def trigger_sos_actions():
    print("SOS button pressed!")
    add_notification("SOS SIGNAL!", "Help needed!", "danger")
    show_alert_window("SOS signal sent!", "danger")
    threading.Thread(target=send_telegram_message, args=("SOS! Help needed!",)).start()
    if pi5_security_mode:
        print("Sending video record command to Pi5 (security mode)")
        threading.Thread(target=safe_post, args=(f"{PI5_MAIN_URL}/record_video",)).start()
    else:
        print("Sending video record command to Pi5 (main mode)")
        threading.Thread(target=safe_post, args=(f"{PI5_MAIN_URL}/record_video",)).start()

def check_pi5_connection():
    try:
        response = safe_get(f"{PI5_MAIN_URL}/health", timeout=2)
        if response and response.status_code == 200:
            data = response.json()
            print(f"Pi5 available: mode - {data.get('mode', 'unknown')}")
            return True
        print("Pi5 not responding")
        return False
    except Exception as e:
        print(f"Error checking Pi5 connection: {e}")
        return False

def activate_security_on_pi5():
    global pi5_security_mode
    print("=" * 50)
    print("ACTIVATING SECURITY ON Pi5")
    print("=" * 50)
    print("Checking Pi5 connection...")
    if not check_pi5_connection():
        print("Cannot activate security - Pi5 unavailable")
        show_alert_window("Pi5 unavailable, security not activated", "warning")
        return False
    print("Sending security activation command...")
    response = safe_post(f"{PI5_MAIN_URL}/switch_to_security", timeout=5)
    if response and response.status_code == 200:
        print("Pi5 switching to security mode")
        add_notification("SECURITY", "Security activated", "info")
        pi5_security_mode = True
        show_alert_window("Security activated", "info")
        return True
    else:
        print("Failed to activate security on Pi5")
        show_alert_window("Failed to activate security", "warning")
        return False

def activate_conversation_on_pi5():
    global pi5_conversation_mode
    print("=" * 50)
    print("ACTIVATING CONVERSATION MODE ON Pi5")
    print("=" * 50)
    print("Checking Pi5 connection...")
    if not check_pi5_connection():
        print("Cannot activate conversation - Pi5 unavailable")
        show_alert_window("Pi5 unavailable, conversation not activated", "warning")
        return False
    print("Sending conversation activation command...")
    response = safe_post(f"{PI5_MAIN_URL}/start_conversation", timeout=5)
    if response and response.status_code == 200:
        print("Pi5 switching to conversation mode")
        pi5_conversation_mode = True
        show_alert_window("Conversation mode activated", "info")
        return True
    else:
        print("Failed to activate conversation on Pi5")
        show_alert_window("Failed to activate conversation", "warning")
        return False

def check_password_on_pi5(password):
    try:
        print(f"Checking password on Pi5 (port 5000)...")
        response = requests.post(f"{PI5_MAIN_URL}/check_password", 
                               json={"password": password}, 
                               timeout=5)
        print(f"Response from Pi5: {response.status_code}")
        if response.status_code == 200:
            print("Correct password")
            add_notification("SECURITY", "Security disabled by password", "success")
            show_alert_window("Security disabled", "info")
            return response
        else:
            print(f"Incorrect password (code: {response.status_code})")
            show_alert_window("Incorrect code", "warning")
            return response
    except Exception as e:
        print(f"Error checking password on Pi5: {e}")
        show_alert_window("Password check error", "danger")
        return None

def exit_security_on_pi5():
    global pi5_security_mode
    try:
        print("Sending security exit command...")
        response = requests.post(f"{PI5_MAIN_URL}/exit_security", timeout=5)
        if response and response.status_code == 200:
            print("Security exit command sent")
            add_notification("SECURITY", "Security disabled", "success")
            pi5_security_mode = False
            show_alert_window("Security disabled", "info")
            return response
        else:
            print(f"Error exiting security: {response.status_code if response else 'no response'}")
            show_alert_window("Error disabling security", "warning")
            return response
    except Exception as e:
        print(f"Error exiting security on Pi5: {e}")
        show_alert_window("Error disabling security", "danger")
        return None

def exit_conversation_on_pi5():
    global pi5_conversation_mode
    try:
        print("Sending conversation stop command...")
        response = requests.post(f"{PI5_MAIN_URL}/stop_conversation", timeout=5)
        if response and response.status_code == 200:
            print("Conversation stop command sent")
            pi5_conversation_mode = False
            show_alert_window("Conversation ended", "info")
            return response
        else:
            print(f"Error stopping conversation: {response.status_code if response else 'no response'}")
            show_alert_window("Error ending conversation", "warning")
            return response
    except Exception as e:
        print(f"Error stopping conversation on Pi5: {e}")
        show_alert_window("Error ending conversation", "danger")
        return None

def request_voice_reminder_from_pi5():
    print("Requesting voice reminder from Pi5...")
    show_alert_window("Voice reminder recording...", "info")
    try:
        response = safe_post(f"{PI5_MAIN_URL}/start_recording", timeout=5)
        if response and response.status_code == 200:
            print("Pi5 started voice reminder recording")
            show_alert_window("Recording started, speak now...", "info")
            return True
        else:
            print("Pi5 did not respond to recording request")
            show_alert_window("Error starting recording", "warning")
            return False
    except Exception as e:
        print(f"Error requesting voice reminder: {e}")
        show_alert_window("Error requesting recording", "danger")
        return False

def add_empty_reminder():
    global reminders, show_modal, scroll_y
    reminders.insert(0, ("--:--", "New reminder"))
    sort_reminders()
    show_modal = True
    scroll_y = 0
    return 0

def add_reminder_with_task(task):
    global reminders, show_modal, scroll_y, edit_mode, edit_index, edit_hours, edit_minutes
    reminders.insert(0, ("--:--", task))
    sort_reminders()
    show_modal = True
    scroll_y = 0
    for i, (t, t_task) in enumerate(reminders):
        if t == "--:--" and t_task == task:
            edit_index = i
            now = datetime.now()
            edit_hours = now.hour
            edit_minutes = now.minute
            edit_mode = True
            print(f"Auto-opened editor for new reminder: {task}")
            break
    return 0

def sort_reminders():
    global reminders
    reminders.sort(key=lambda x: (x[0] != "--:--", x[0] == "--:--", x[0]))

def get_current_date():
    now = datetime.now()
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{days[now.weekday()]}, {now.day} {months[now.month - 1]}"

def init_sensors():
    print("=" * 50)
    print("INITIALIZING SENSOR SYSTEM")
    print("=" * 50)
    arduino_thread = threading.Thread(target=arduino_loop, daemon=True)
    arduino_thread.start()
    print("Arduino monitoring started")
    print("Gas sensor disabled - only water sensor active")
    print("=" * 50)

init_sensors()

pygame.init()
info = pygame.display.Info()
SCREEN_WIDTH, SCREEN_HEIGHT = info.current_w, info.current_h
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
pygame.display.set_caption("Pi3 Interface Demo")
clock = pygame.time.Clock()

BG_COLOR = (255, 255, 255)
TEXT_COLOR = (40, 40, 40)
TIME_COLOR = (20, 20, 20)
DATE_COLOR = (100, 100, 100)
LIME_GREEN = (34, 197, 94)
DIVIDER_COLOR = (230, 230, 230)
OVERLAY_COLOR = (0, 0, 0, 180)

COLOR_COMM = (219, 234, 254)
COLOR_SEC = (204, 251, 241)
COLOR_MUSIC = (254, 243, 199)
COLOR_SOS = (254, 226, 226)
SOS_BORDER = (239, 68, 68)
MUSIC_BORDER = (245, 158, 11)
SEC_BORDER = (20, 184, 166)
PROGRESS_COLOR = (34, 197, 94)
BLUE = (59, 130, 246)
WHITE = (255, 255, 255)
RED = (239, 68, 68)
DARK_RED = (200, 50, 50)
SECURITY_RED = (220, 50, 50)
SECURITY_GREEN = (50, 200, 50)
GRAY = (200, 200, 200)
DARK_GRAY = (100, 100, 100)
EDIT_BG = (252, 253, 255)
EDIT_BORDER = (210, 220, 235)
EDIT_BUTTON_COLOR = (240, 240, 240)

def get_font(size_factor, bold=False):
    return pygame.font.SysFont("arial", int(SCREEN_HEIGHT * size_factor), bold=bold)

time_font = get_font(0.12, True)
date_font = get_font(0.05)
title_font = get_font(0.07, True)
button_font = get_font(0.055, True)
modal_task_font = get_font(0.05, True)
modal_time_font = get_font(0.055, True)
security_title_font = get_font(0.1, True)
security_button_font = get_font(0.08, True)
security_exit_font = get_font(0.045, True)
security_code_font = get_font(0.12, True)
security_status_font = get_font(0.045, True)
conv_big_font = get_font(0.1, True)
conv_status_font = pygame.font.SysFont("arial", 42)
conv_btn_font = pygame.font.SysFont("arial", 30, bold=True)
small_font = get_font(0.035)
edit_font = get_font(0.15, True)
alert_font = pygame.font.SysFont("arial", 28, bold=True)
alert_small_font = pygame.font.SysFont("arial", 20)

radio_streams = {
    "Radio Station 1": "http://example.com/stream1",
    "Radio Station 2": "http://example.com/stream2",
    "Radio Station 3": "http://example.com/stream3",
    "Radio Station 4": "http://example.com/stream4"
}

class HoldButton:
    def __init__(self, x, y, width, height, text, bg_color, border_color, button_id, val=None, font_size=None):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.bg_color = bg_color
        self.border_color = border_color
        self.button_id = button_id
        self.val = val
        self.font_size = font_size or int(self.rect.height * 0.3)
        self.hovered = False
        self.holding = False
        self.hold_start_time = 0
    
    def draw(self, surface, is_active=False, is_disabled=False):
        if is_disabled:
            color = (200, 200, 200)
            border_color = (150, 150, 150)
        elif self.holding:
            color = [max(0, c - 30) for c in self.bg_color]
            border_color = self.border_color
        elif self.hovered and not is_active:
            color = [max(0, c - 15) for c in self.bg_color]
            border_color = self.border_color
        else:
            color = (255, 215, 0) if is_active else self.bg_color
            border_color = self.border_color
        
        pygame.draw.rect(surface, color, self.rect, border_radius=20)
        pygame.draw.rect(surface, border_color, self.rect, 4, border_radius=20)
        
        if self.holding:
            current_time = time.time()
            elapsed = current_time - self.hold_start_time
            progress = min(elapsed / HOLD_TIME_REQUIRED, 1.0)
            progress_rect = pygame.Rect(
                self.rect.x + 10,
                self.rect.bottom - 15,
                (self.rect.width - 20) * progress,
                8
            )
            pygame.draw.rect(surface, PROGRESS_COLOR, progress_rect, border_radius=4)
        
        font_size = max(self.font_size, 20)
        font = pygame.font.SysFont("arial", font_size, bold=True)
        txt_color = (150, 150, 150) if is_disabled else TEXT_COLOR
        txt = font.render(self.text, True, txt_color)
        surface.blit(txt, txt.get_rect(center=self.rect.center))
    
    def start_hold(self):
        self.holding = True
        self.hold_start_time = time.time()
    
    def stop_hold(self):
        self.holding = False
        self.hold_start_time = 0
    
    def is_hold_complete(self):
        if not self.holding:
            return False
        current_time = time.time()
        return (current_time - self.hold_start_time) >= HOLD_TIME_REQUIRED

margin = SCREEN_WIDTH * 0.04
col_w = (SCREEN_WIDTH - 3 * margin) // 2
right_col_x = 2 * margin + col_w
btn_h = SCREEN_HEIGHT * 0.17
CARD_H = 110
GAP = 20
SCROLL_STEP = CARD_H + GAP

main_buttons = [
    HoldButton(right_col_x, SCREEN_HEIGHT*0.04, col_w, btn_h, "CONVERSATION", COLOR_COMM, BLUE, "comm_btn"),
    HoldButton(right_col_x, SCREEN_HEIGHT*0.24, col_w, btn_h, "SECURITY", COLOR_SEC, SEC_BORDER, "sec_btn"),
    HoldButton(right_col_x, SCREEN_HEIGHT*0.44, col_w, btn_h, "MUSIC", COLOR_MUSIC, MUSIC_BORDER, "music_btn"),
    HoldButton(right_col_x, SCREEN_HEIGHT*0.76, col_w, btn_h, "SOS", COLOR_SOS, SOS_BORDER, "sos_btn"),
]

reminders_field_rect = pygame.Rect(margin, SCREEN_HEIGHT * 0.28, col_w, SCREEN_HEIGHT * 0.42)
reminders_btn = HoldButton(margin, SCREEN_HEIGHT * 0.28, col_w, SCREEN_HEIGHT * 0.42, "", BG_COLOR, LIME_GREEN, "show_reminders")

add_reminder_btn = HoldButton(margin, SCREEN_HEIGHT * 0.76, col_w, btn_h, "ADD NEW", BG_COLOR, LIME_GREEN, "add_reminder")

music_station_btns = []
for i, (name, url) in enumerate(radio_streams.items()):
    music_station_btns.append(HoldButton(
        margin + (i % 2) * (col_w + margin),
        SCREEN_HEIGHT * 0.18 + (i // 2) * (btn_h + 30),
        col_w, btn_h, name, COLOR_MUSIC, MUSIC_BORDER, f"radio_{i}", url
    ))

back_btn = HoldButton(margin, SCREEN_HEIGHT * 0.78, 300, 80, "← BACK", (235, 235, 235), (150, 150, 150), "back_btn")

def check_hold_completions():
    global current_mode, show_modal, edit_mode, edit_index, edit_hours, edit_minutes
    global scroll_y, reminders, security_code_input, security_attempts, security_active
    global pi5_conversation_mode, current_stream, is_listening_mode
    
    current_time = time.time()
    button_ids_to_remove = []
    
    for button_id, data in holding_buttons.items():
        start_time = data[0]
        if current_time - start_time >= HOLD_TIME_REQUIRED:
            handle_button_action(button_id, data[1] if len(data) > 1 else None)
            button_ids_to_remove.append(button_id)
    
    for button_id in button_ids_to_remove:
        holding_buttons.pop(button_id, None)

def handle_button_action(button_id, data=None):
    global current_mode, show_modal, edit_mode, edit_index, edit_hours, edit_minutes, scroll_y
    global reminders, pi5_conversation_mode, current_stream, is_listening_mode
    global security_code_input, security_attempts, security_active
    
    print(f"Hold completed for button: {button_id}")
    
    if button_id == "comm_btn":
        current_mode = "CONVERSATION"
        is_listening_mode = True
        print("Switching to conversation mode")
        threading.Thread(target=activate_conversation_on_pi5, daemon=True).start()
    elif button_id == "sec_btn":
        print("Activating security...")
        threading.Thread(target=activate_security_on_pi5, daemon=True).start()
    elif button_id == "music_btn":
        current_mode = "MUSIC"
        print("Switching to music mode")
    elif button_id == "sos_btn":
        trigger_sos_actions()
    elif button_id == "back_btn":
        current_mode = "MAIN"
        print("Back to main menu")
    elif button_id.startswith("radio_"):
        index = int(button_id.split("_")[1])
        if index < len(music_station_btns):
            btn = music_station_btns[index]
            current_stream = "" if current_stream == btn.val else btn.val
            if current_stream:
                print(f"Radio selected: {btn.text}")
                show_alert_window(f"Radio: {btn.text}", "info")
            else:
                print("Music stopped")
                show_alert_window("Music stopped", "info")
    elif button_id == "add_reminder":
        print("Requesting voice reminder...")
        success = request_voice_reminder_from_pi5()
        if success:
            print("Request sent. Pi5 will record voice reminder.")
        else:
            print("Failed to send recording request")
    elif button_id == "show_reminders":
        show_modal = True
        print("Opening reminders list")
    elif button_id == "conv_back":
        current_mode = "MAIN"
        print("Back to main menu")
        if pi5_conversation_mode:
            exit_conversation_on_pi5()
    elif button_id == "stop_conversation":
        is_listening_mode = False
        current_mode = "MAIN"
        print("Ending conversation and returning to main menu")
        if pi5_conversation_mode:
            exit_conversation_on_pi5()
    elif button_id == "modal_close":
        show_modal = False
        print("Closing reminders list")
    elif button_id == "modal_scroll_up":
        scroll_y += SCROLL_STEP
        print("Scrolling up")
    elif button_id == "modal_scroll_down":
        scroll_y -= SCROLL_STEP
        print("Scrolling down")
    elif button_id.startswith("edit_reminder_"):
        index = int(button_id.split("_")[2])
        if index < len(reminders):
            edit_index = index
            curr_t = reminders[index][0]
            if curr_t == "--:--":
                now = datetime.now()
                edit_hours = now.hour
                edit_minutes = now.minute
            else:
                try:
                    edit_hours, edit_minutes = map(int, curr_t.split(':'))
                except:
                    now = datetime.now()
                    edit_hours = now.hour
                    edit_minutes = now.minute
            edit_mode = True
            print(f"Editing reminder {index} with time {edit_hours:02d}:{edit_minutes:02d}")
    elif button_id == "time_editor_h_up":
        edit_hours = (edit_hours + 1) % 24
    elif button_id == "time_editor_h_down":
        edit_hours = (edit_hours - 1) % 24
    elif button_id == "time_editor_m_up":
        edit_minutes = (edit_minutes + 1) % 60
    elif button_id == "time_editor_m_down":
        edit_minutes = (edit_minutes - 1) % 60
    elif button_id == "time_editor_ok":
        if 0 <= edit_index < len(reminders):
            reminders[edit_index] = (f"{edit_hours:02d}:{edit_minutes:02d}", reminders[edit_index][1])
            sort_reminders()
            edit_mode = False
            show_modal = True
            scroll_y = 0
            print("Time saved, opening reminders list")
            show_alert_window("Reminder time saved", "success")
    elif button_id == "time_editor_delete":
        if 0 <= edit_index < len(reminders):
            deleted_reminder = reminders[edit_index]
            reminders.pop(edit_index)
            edit_mode = False
            edit_index = -1
            show_modal = True
            scroll_y = 0
            print(f"Deleted reminder: {deleted_reminder[1]} - {deleted_reminder[0]}")
            show_alert_window("Reminder deleted", "info")
    elif button_id == "security_digit":
        if data:
            handle_security_code_input(data)
    elif button_id == "security_exit":
        print("Exiting security via button")
        response = exit_security_on_pi5()
        if response and response.status_code == 200:
            current_mode = "MAIN"
            security_code_input = ""
            security_attempts = 0
            security_active = False

def handle_security_code_input(digit):
    global security_code_input, security_attempts, current_mode, security_active
    
    if digit == "C":
        security_code_input = ""
    elif digit == "←":
        security_code_input = security_code_input[:-1]
    elif digit.isdigit() and len(security_code_input) < 6:
        security_code_input += digit
        if len(security_code_input) == 6:
            print(f"Checking password: {security_code_input}")
            response = check_password_on_pi5(security_code_input)
            if response and response.status_code == 200:
                print("Correct password! Security disabled.")
                security_code_input = ""
                security_attempts = 0
                security_active = False
                current_mode = "MAIN"
            else:
                security_attempts += 1
                security_code_input = ""
                if security_attempts >= security_max_attempts:
                    print("Maximum attempts exceeded!")
                    show_alert_window("Maximum attempts exceeded!", "danger")
                    security_attempts = 0
                else:
                    print(f"Incorrect code. Attempts: {security_attempts}/{security_max_attempts}")

def check_connection_periodically():
    global last_connection_check, connection_status
    current_time = time.time()
    if current_time - last_connection_check > connection_check_interval:
        print("Checking Pi5 connection...")
        if check_pi5_connection():
            connection_status = "✓"
        else:
            connection_status = "✗"
            if last_connection_check > 0:
                show_alert_window("Connection to Pi5 lost", "warning")
        last_connection_check = current_time

def draw_time_editor():
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill(OVERLAY_COLOR)
    screen.blit(overlay, (0, 0))
    panel_w, panel_h = 600, 500
    panel_rect = pygame.Rect((SCREEN_WIDTH-panel_w)//2, (SCREEN_HEIGHT-panel_h)//2, panel_w, panel_h)
    pygame.draw.rect(screen, BG_COLOR, panel_rect, border_radius=30)
    
    h_up_btn = HoldButton(panel_rect.left + 100, panel_rect.top + 50, 100, 60, "+", EDIT_BUTTON_COLOR, BLUE, "time_editor_h_up", font_size=40)
    h_down_btn = HoldButton(panel_rect.left + 100, panel_rect.top + 280, 100, 60, "-", EDIT_BUTTON_COLOR, BLUE, "time_editor_h_down", font_size=40)
    m_up_btn = HoldButton(panel_rect.right - 200, panel_rect.top + 50, 100, 60, "+", EDIT_BUTTON_COLOR, BLUE, "time_editor_m_up", font_size=40)
    m_down_btn = HoldButton(panel_rect.right - 200, panel_rect.top + 280, 100, 60, "-", EDIT_BUTTON_COLOR, BLUE, "time_editor_m_down", font_size=40)
    ok_btn = HoldButton(panel_rect.centerx + 20, panel_rect.bottom - 100, 250, 70, "OK", LIME_GREEN, LIME_GREEN, "time_editor_ok", font_size=40)
    delete_btn = HoldButton(panel_rect.centerx - 270, panel_rect.bottom - 100, 250, 70, "DELETE", DARK_RED, DARK_RED, "time_editor_delete", font_size=40)
    
    mouse_pos = pygame.mouse.get_pos()
    for btn in [h_up_btn, h_down_btn, m_up_btn, m_down_btn, ok_btn, delete_btn]:
        btn.hovered = btn.rect.collidepoint(mouse_pos)
        btn.draw(screen)
    
    time_str = f"{edit_hours:02d}:{edit_minutes:02d}"
    txt = edit_font.render(time_str, True, TEXT_COLOR)
    screen.blit(txt, txt.get_rect(center=(panel_rect.centerx, panel_rect.centery - 20)))
    
    hours_label = button_font.render("Hours", True, TEXT_COLOR)
    minutes_label = button_font.render("Minutes", True, TEXT_COLOR)
    screen.blit(hours_label, (panel_rect.left + 100 + 50 - hours_label.get_width()//2, panel_rect.top + 120))
    screen.blit(minutes_label, (panel_rect.right - 200 + 50 - minutes_label.get_width()//2, panel_rect.top + 120))
    
    return [h_up_btn, h_down_btn, m_up_btn, m_down_btn, ok_btn, delete_btn]

def draw_modal():
    global scroll_y
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill(OVERLAY_COLOR)
    screen.blit(overlay, (0, 0))
    
    m_w, m_h = SCREEN_WIDTH * 0.9, SCREEN_HEIGHT * 0.9
    m_rect = pygame.Rect((SCREEN_WIDTH - m_w)//2, (SCREEN_HEIGHT - m_h)//2, m_w, m_h)
    pygame.draw.rect(screen, BG_COLOR, m_rect, border_radius=30)
    
    title = title_font.render("REMINDERS", True, LIME_GREEN)
    screen.blit(title, (m_rect.centerx - title.get_width()//2, m_rect.top + 40))
    
    up_btn = HoldButton(m_rect.right - 140, m_rect.top + 130, 100, 80, "↑", (240, 240, 240), DIVIDER_COLOR, "modal_scroll_up", font_size=50)
    down_btn = HoldButton(m_rect.right - 140, m_rect.bottom - 220, 100, 80, "↓", (240, 240, 240), DIVIDER_COLOR, "modal_scroll_down", font_size=50)
    
    view_rect = pygame.Rect(m_rect.left + 40, m_rect.top + 130, m_w - 280, m_h - 280)
    total_h = len(reminders) * (CARD_H + GAP)
    scroll_y = max(min(0, view_rect.height - total_h + GAP), min(0, scroll_y))
    
    close_btn = HoldButton(m_rect.centerx - 180, m_rect.bottom - 90, 360, 70, "CLOSE", SOS_BORDER, SOS_BORDER, "modal_close", font_size=40)
    
    mouse_pos = pygame.mouse.get_pos()
    for btn in [up_btn, down_btn, close_btn]:
        btn.hovered = btn.rect.collidepoint(mouse_pos)
        btn.draw(screen)
    
    scroll_bar_bg = pygame.Rect(m_rect.right - 180, m_rect.top + 130, 15, m_h - 280)
    pygame.draw.rect(screen, (240, 240, 240), scroll_bar_bg, border_radius=10)
    
    if total_h > view_rect.height:
        thumb_h = max(40, scroll_bar_bg.height * (view_rect.height / total_h))
        scroll_diff = total_h - view_rect.height + GAP
        thumb_y = scroll_bar_bg.top + (-scroll_y / scroll_diff) * (scroll_bar_bg.height - thumb_h)
        pygame.draw.rect(screen, LIME_GREEN, (scroll_bar_bg.x, thumb_y, 15, thumb_h), border_radius=10)
    
    temp_surf = pygame.Surface((view_rect.width, total_h), pygame.SRCALPHA)
    card_buttons = []
    
    for i, (t, task) in enumerate(reminders):
        y_p = i * (CARD_H + GAP)
        card_rect = pygame.Rect(0, y_p, view_rect.width, CARD_H)
        card_btn = HoldButton(0, y_p, view_rect.width, CARD_H, "", EDIT_BG, EDIT_BORDER, f"edit_reminder_{i}")
        card_btn.hovered = False
        card_btn.draw(temp_surf)
        
        task_txt = modal_task_font.render(task, True, TEXT_COLOR)
        temp_surf.blit(task_txt, (30, y_p + (CARD_H // 2 - task_txt.get_height() // 2)))
        time_txt = modal_time_font.render(t, True, LIME_GREEN)
        temp_surf.blit(time_txt, (view_rect.width - time_txt.get_width() - 40, 
                                 y_p + (CARD_H // 2 - time_txt.get_height() // 2)))
        card_buttons.append((card_btn, y_p))
    
    screen.blit(temp_surf, view_rect.topleft, (0, -scroll_y, view_rect.width, view_rect.height))
    
    visible_card_buttons = []
    for card_btn, y_p in card_buttons:
        card_screen_rect = pygame.Rect(
            view_rect.x,
            view_rect.y + y_p + scroll_y,
            view_rect.width,
            CARD_H
        )
        if card_screen_rect.colliderect(view_rect):
            card_btn.hovered = card_screen_rect.collidepoint(mouse_pos)
            visible_card_buttons.append(card_btn)
    
    return close_btn, up_btn, down_btn, visible_card_buttons, view_rect

def draw_conversation_screen():
    global wave_offset, heights
    screen.fill(WHITE)
    center_x, center_y = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2
    
    glow_rad = 110 + (math.sin(wave_offset * 0.1) * 15)
    pygame.draw.circle(screen, (248, 250, 255), (center_x, center_y), glow_rad + 20)
    
    for i in range(len(heights)):
        x = center_x - 200 + (i * 5)
        if is_animating:
            target = (25 * math.sin(i * 0.2 + wave_offset) + 
                      15 * math.sin(i * 0.5 - wave_offset * 1.2) + 
                      random.uniform(-7, 7))
            target *= math.sin(math.pi * i / len(heights))
        else:
            target = 5 * math.sin(i * 0.1 + wave_offset * 0.5) * math.sin(math.pi * i / len(heights))
        heights[i] += (target - heights[i]) * 0.25
        pygame.draw.line(screen, BLUE if is_animating else (180, 190, 220), 
                       (x, center_y - heights[i]), (x, center_y + heights[i]), 4)
    
    wave_offset += 0.25 if is_animating else 0.05
    
    if is_listening_mode:
        lbl = "SPEAKING..." if is_animating else "LISTENING"
    else:
        lbl = "READY" if not is_animating else "SPEAKING..."
    
    txt_status = conv_status_font.render(lbl, True, (80, 80, 80))
    screen.blit(txt_status, txt_status.get_rect(center=(center_x, SCREEN_HEIGHT * 0.2)))
    
    stop_btn = HoldButton(center_x - 180, SCREEN_HEIGHT * 0.8, 360, 80, "END", RED, RED, "stop_conversation", font_size=40)
    stop_btn.hovered = stop_btn.rect.collidepoint(pygame.mouse.get_pos())
    stop_btn.draw(screen)
    
    return {"stop_btn": stop_btn}

def draw_security_screen():
    global security_code_input, security_attempts, exit_button_visible
    screen.fill(BG_COLOR)
    
    title_text = "LOCK"
    title_color = SECURITY_RED if security_attempts > 0 else TEXT_COLOR
    title = security_title_font.render(title_text, True, title_color)
    screen.blit(title, (50, 40))
    
    code_box_w, code_box_h = 350, 100
    code_box_x, code_box_y = 50, int(SCREEN_HEIGHT * 0.35)
    code_box = pygame.Rect(code_box_x, code_box_y, code_box_w, code_box_h)
    pygame.draw.rect(screen, (245, 245, 245), code_box, border_radius=15)
    pygame.draw.rect(screen, DIVIDER_COLOR, code_box, 3, border_radius=15)
    
    display_text = "*" * len(security_code_input)
    code_txt = security_code_font.render(display_text, True, TEXT_COLOR)
    screen.blit(code_txt, code_txt.get_rect(center=code_box.center))
    
    status_text = ""
    status_color = SECURITY_RED
    if security_attempts > 0:
        status_text = f"Incorrect code ({security_attempts}/{security_max_attempts})"
        if security_attempts >= security_max_attempts:
            status_text = "Maximum attempts exceeded"
    if status_text:
        status = security_status_font.render(status_text, True, status_color)
        screen.blit(status, (code_box_x, code_box_y + code_box_h + 20))
    
    key_size = int(SCREEN_HEIGHT * 0.19)
    gap = 20
    keyboard_x_start = int(SCREEN_WIDTH * 0.55)
    start_y = int(SCREEN_HEIGHT * 0.08)
    
    key_buttons = []
    for i in range(1, 10):
        row, col = (i-1)//3, (i-1)%3
        rect = pygame.Rect(keyboard_x_start + col*(key_size + gap), 
                          start_y + row*(key_size + gap), key_size, key_size)
        btn = HoldButton(rect.x, rect.y, rect.width, rect.height, str(i), COLOR_SEC, SEC_BORDER, 
                        "security_digit", str(i), font_size=int(key_size * 0.4))
        btn.hovered = btn.rect.collidepoint(pygame.mouse.get_pos())
        key_buttons.append(btn)
    
    row_y = start_y + 3*(key_size + gap)
    c_btn = HoldButton(keyboard_x_start, row_y, key_size, key_size, "C", (255, 230, 230), SOS_BORDER, 
                      "security_digit", "C", font_size=int(key_size * 0.4))
    zero_btn = HoldButton(keyboard_x_start + (key_size + gap), row_y, key_size, key_size, "0", COLOR_SEC, SEC_BORDER, 
                         "security_digit", "0", font_size=int(key_size * 0.4))
    back_btn = HoldButton(keyboard_x_start + 2*(key_size + gap), row_y, key_size, key_size, "←", (254, 243, 199), MUSIC_BORDER, 
                         "security_digit", "←", font_size=int(key_size * 0.4))
    
    mouse_pos = pygame.mouse.get_pos()
    for btn in [c_btn, zero_btn, back_btn]:
        btn.hovered = btn.rect.collidepoint(mouse_pos)
        key_buttons.extend([c_btn, zero_btn, back_btn])
    
    for btn in key_buttons:
        if "security_digit" in holding_buttons:
            start_time, held_digit = holding_buttons["security_digit"]
            if held_digit == btn.val:
                btn.holding = True
                btn.hold_start_time = start_time
            else:
                btn.holding = False
        else:
            btn.holding = False
        btn.draw(screen)
    
    exit_btn_rect = pygame.Rect(50, SCREEN_HEIGHT - 100, 200, 70)
    
    if exit_button_visible and pi5_security_mode:
        exit_btn = HoldButton(50, SCREEN_HEIGHT - 100, 200, 70, "EXIT", SOS_BORDER, SOS_BORDER, 
                             "security_exit", font_size=35)
        exit_btn.hovered = exit_btn.rect.collidepoint(mouse_pos)
        if "security_exit" in holding_buttons:
            exit_btn.holding = True
            exit_btn.hold_start_time = holding_buttons["security_exit"]
        else:
            exit_btn.holding = False
        exit_btn.draw(screen)
        return key_buttons, exit_btn, True
    else:
        exit_btn = HoldButton(50, SCREEN_HEIGHT - 100, 200, 70, "EXIT", GRAY, GRAY, 
                             "security_exit", font_size=35)
        exit_btn.draw(screen, is_disabled=True)
        return key_buttons, exit_btn, False

def draw_main_screen():
    now = datetime.now()
    
    screen.blit(time_font.render(now.strftime("%H:%M"), True, TIME_COLOR), 
                (margin, SCREEN_HEIGHT*0.03))
    screen.blit(date_font.render(get_current_date(), True, DATE_COLOR), 
                (margin, SCREEN_HEIGHT*0.17))
    
    reminders_btn.hovered = reminders_btn.rect.collidepoint(pygame.mouse.get_pos())
    reminders_btn.draw(screen)
    
    screen.blit(title_font.render("TODAY", True, LIME_GREEN), 
                (margin + 30, reminders_btn.rect.top + 20))
    
    main_list_area = pygame.Surface((reminders_btn.rect.width - 40, 
                                    reminders_btn.rect.height - 110), pygame.SRCALPHA)
    for i, (t, task) in enumerate(reminders[:3]):
        txt = get_font(0.042, True).render(f"• {task} — {t}", True, TEXT_COLOR)
        main_list_area.blit(txt, (15, i * SCREEN_HEIGHT * 0.08))
    screen.blit(main_list_area, (margin + 20, reminders_btn.rect.top + 100))
    
    add_reminder_btn.hovered = add_reminder_btn.rect.collidepoint(pygame.mouse.get_pos())
    add_reminder_btn.draw(screen)
    
    for b in main_buttons:
        b.hovered = b.rect.collidepoint(pygame.mouse.get_pos()) and not show_modal
        b.draw(screen)

def draw_music_screen():
    screen.blit(title_font.render("MUSIC SELECTION", True, MUSIC_BORDER), 
                (margin, SCREEN_HEIGHT * 0.05))
    for b in music_station_btns:
        b.hovered = b.rect.collidepoint(pygame.mouse.get_pos())
        b.draw(screen, is_active=(current_stream == b.val))
    back_btn.hovered = back_btn.rect.collidepoint(pygame.mouse.get_pos())
    back_btn.draw(screen)

def update_alert_windows():
    global alert_windows
    alert_windows = [window for window in alert_windows if window.update()]
    current_time = time.time()
    to_remove = []
    for msg_hash, timestamp in alert_cooldown.items():
        if current_time - timestamp > 3600:
            to_remove.append(msg_hash)
    for msg_hash in to_remove:
        alert_cooldown.pop(msg_hash, None)

def draw_alert_windows():
    for window in alert_windows:
        window.draw(screen)

running = True
print("=" * 50)
print("Pi3 INTERFACE - DEMONSTRATION VERSION")
print("=" * 50)
print(f"Pi5 IP: {PI5_IP}")
print(f"Pi5 port: 5000")
print(f"Pi3 port: {FLASK_PORT}")
print(f"Sensors: water enabled, gas disabled")
print(f"Water leak minimum duration: {WATER_MIN_DURATION} sec")
print("=" * 50)

flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()
time.sleep(2)

check_connection_periodically()

while running:
    mouse_pos = pygame.mouse.get_pos()
    
    check_connection_periodically()
    check_hold_completions()
    update_alert_windows()
    
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if edit_mode:
                    edit_mode = False
                elif current_mode == "CONVERSATION":
                    if pi5_conversation_mode:
                        exit_conversation_on_pi5()
                    current_mode = "MAIN"
                elif current_mode == "SECURITY":
                    current_mode = "MAIN"
                    security_code_input = ""
                    security_attempts = 0
                    security_active = False
                elif current_mode == "MUSIC":
                    current_mode = "MAIN"
                elif show_modal:
                    show_modal = False
                else:
                    running = False
        
        if event.type == pygame.MOUSEBUTTONDOWN:
            mouse_pos = pygame.mouse.get_pos()
            
            if alert_windows:
                for window in alert_windows[:]:
                    if window.handle_click(mouse_pos):
                        alert_windows.remove(window)
                        break
            else:
                if edit_mode:
                    time_editor_buttons = draw_time_editor()
                    for btn in time_editor_buttons:
                        if btn.rect.collidepoint(mouse_pos):
                            holding_buttons[btn.button_id] = (time.time(),)
                            btn.start_hold()
                elif current_mode == "SECURITY":
                    key_buttons, exit_btn, exit_enabled = draw_security_screen()
                    for btn in key_buttons:
                        if btn.rect.collidepoint(mouse_pos):
                            holding_buttons["security_digit"] = (time.time(), btn.val)
                            btn.start_hold()
                    if exit_enabled and exit_btn.rect.collidepoint(mouse_pos):
                        holding_buttons["security_exit"] = (time.time(),)
                        exit_btn.start_hold()
                elif current_mode == "CONVERSATION":
                    if conversation_ui_elements.get("stop_btn") and conversation_ui_elements["stop_btn"].rect.collidepoint(mouse_pos):
                        holding_buttons["stop_conversation"] = (time.time(),)
                        conversation_ui_elements["stop_btn"].start_hold()
                elif show_modal:
                    close_btn, up_btn, down_btn, card_buttons, view_rect = draw_modal()
                    if close_btn.rect.collidepoint(mouse_pos):
                        holding_buttons["modal_close"] = (time.time(),)
                        close_btn.start_hold()
                    elif up_btn.rect.collidepoint(mouse_pos):
                        holding_buttons["modal_scroll_up"] = (time.time(),)
                        up_btn.start_hold()
                    elif down_btn.rect.collidepoint(mouse_pos):
                        holding_buttons["modal_scroll_down"] = (time.time(),)
                        down_btn.start_hold()
                    elif view_rect.collidepoint(mouse_pos):
                        for btn in card_buttons:
                            card_index = int(btn.button_id.split("_")[2])
                            card_global_rect = pygame.Rect(
                                view_rect.x,
                                view_rect.y + (card_index * (CARD_H + GAP)) + scroll_y,
                                view_rect.width,
                                CARD_H
                            )
                            if card_global_rect.collidepoint(mouse_pos):
                                holding_buttons[btn.button_id] = (time.time(),)
                                btn.start_hold()
                                break
                elif current_mode == "MAIN":
                    if reminders_btn.rect.collidepoint(mouse_pos):
                        holding_buttons["show_reminders"] = (time.time(),)
                        reminders_btn.start_hold()
                    if add_reminder_btn.rect.collidepoint(mouse_pos):
                        holding_buttons["add_reminder"] = (time.time(),)
                        add_reminder_btn.start_hold()
                    for b in main_buttons:
                        if b.rect.collidepoint(mouse_pos):
                            holding_buttons[b.button_id] = (time.time(),)
                            b.start_hold()
                elif current_mode == "MUSIC":
                    if back_btn.rect.collidepoint(mouse_pos):
                        holding_buttons[back_btn.button_id] = (time.time(),)
                        back_btn.start_hold()
                    for b in music_station_btns:
                        if b.rect.collidepoint(mouse_pos):
                            holding_buttons[b.button_id] = (time.time(),)
                            b.start_hold()
        
        if event.type == pygame.MOUSEBUTTONUP:
            for btn_list in [main_buttons, music_station_btns]:
                for btn in btn_list:
                    btn.stop_hold()
            if back_btn:
                back_btn.stop_hold()
            if reminders_btn:
                reminders_btn.stop_hold()
            if add_reminder_btn:
                add_reminder_btn.stop_hold()
            current_time = time.time()
            for button_id in list(holding_buttons.keys()):
                start_time = holding_buttons[button_id][0]
                if current_time - start_time < HOLD_TIME_REQUIRED:
                    holding_buttons.pop(button_id, None)
    
    screen.fill(BG_COLOR)
    
    if current_mode == "MAIN":
        draw_main_screen()
        if show_modal:
            draw_modal()
        if edit_mode:
            draw_time_editor()
    elif current_mode == "MUSIC":
        draw_music_screen()
    elif current_mode == "SECURITY":
        draw_security_screen()
    elif current_mode == "CONVERSATION":
        conversation_ui_elements = draw_conversation_screen()
    
    if alert_windows:
        draw_alert_windows()
    
    pygame.display.flip()
    clock.tick(60)

print("Pi3 interface shutting down")
pygame.quit()
sys.exit()