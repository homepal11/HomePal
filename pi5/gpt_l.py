#!/usr/bin/env python3
# gpt_l.py - Режим общения (демонстрационная версия)
import json
import requests
import asyncio
import numpy as np
import sounddevice as sd
from piper.voice import PiperVoice
from datetime import datetime
from vosk import Model, KaldiRecognizer
import pyaudio
import threading
import subprocess
import sys
import os
import time
import serial

# === Конфигурация (заглушки) ===
VOSK_MODEL_PATH = "/path/to/vosk/model"
PIPER_MODEL_PATH = "/path/to/piper/model"
PI3_UI_URL = "http://192.168.1.XXX:8000/set_ui_status"
PI3_URL = "http://192.168.1.XXX:8000"

SERIAL_PORT = "/dev/ttyUSB0"
SERIAL_BAUDRATE = 9600

MAX_HISTORY_PAIRS = 3
CONVERSATION_CONTEXT = "You are a voice assistant for an elderly person. Keep responses short and simple."

# === Инициализация (с обработкой ошибок) ===
try:
    ser = serial.Serial(SERIAL_PORT, SERIAL_BAUDRATE, timeout=1)
    print("Serial port connected")
except Exception as e:
    print(f"Serial port error: {e}")
    ser = None

vosk_model = Model(VOSK_MODEL_PATH)
rec = KaldiRecognizer(vosk_model, 16000)
pa = pyaudio.PyAudio()
mic_stream = pa.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=8000)

voice = PiperVoice.load(PIPER_MODEL_PATH)
out_stream = sd.OutputStream(samplerate=voice.config.sample_rate, channels=1, dtype='int16')
out_stream.start()

conversation_history = []
is_running = True

# === Утилиты ===
def notify_ui(status):
    print(f"UI notification: {status}")
    def send():
        try:
            requests.post(PI3_UI_URL, json={"status": status}, timeout=1)
        except Exception as e:
            print(f"UI notification error: {e}")
    threading.Thread(target=send, daemon=True).start()

def send_to_pi3(command, data=None):
    print(f"Pi3 command: {command}")
    try:
        url = f"{PI3_URL}/pi5_command"
        payload = {"command": command}
        if data:
            payload.update(data)
        threading.Thread(
            target=lambda: requests.post(url, json=payload, timeout=2)
        ).start()
        return True
    except Exception as e:
        print(f"Failed to send to Pi3: {e}")
        return False

def shutdown_and_switch():
    global is_running
    print("Shutting down conversation mode...")
    is_running = False
    notify_ui("stop")
    send_to_pi3("close_conversation")
    
    try:
        if mic_stream.is_active():
            mic_stream.stop_stream()
        mic_stream.close()
        pa.terminate()
        out_stream.stop()
        out_stream.close()
        if ser:
            ser.close()
    except Exception as e:
        print(f"Error closing streams: {e}")
    
    time.sleep(1)
    print("Switching to main mode...")
    try:
        subprocess.Popen([sys.executable, "/path/to/main_module.py"])
    except Exception as e:
        print(f"Error starting main module: {e}")
    os._exit(0)

def add_to_history(user_input, assistant_response):
    global conversation_history
    conversation_history.append({
        "user": user_input,
        "assistant": assistant_response,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    })
    if len(conversation_history) > MAX_HISTORY_PAIRS:
        conversation_history = conversation_history[-MAX_HISTORY_PAIRS:]

def build_prompt_with_history(user_input):
    prompt_parts = [CONVERSATION_CONTEXT]
    if conversation_history:
        prompt_parts.append("Previous conversation:")
        for entry in conversation_history:
            prompt_parts.append(f"User: {entry['user']}")
            prompt_parts.append(f"Assistant: {entry['assistant']}")
    prompt_parts.append(f"Current question: {user_input}")
    prompt_parts.append("Assistant:")
    return "\n".join(prompt_parts)

def clear_conversation_history():
    global conversation_history
    conversation_history = []
    print("History cleared")

async def speak_full(text: str):
    try:
        if mic_stream.is_active():
            mic_stream.stop_stream()
        notify_ui("speaking")
        if ser:
            try:
                ser.write(b"reset\n")
            except Exception as e:
                print(f"Serial error: {e}")
        for audio_bytes in voice.synthesize_stream_raw(text, length_scale=1.2):
            int_data = np.frombuffer(audio_bytes, dtype=np.int16)
            boosted = (int_data.astype(np.float32) * 3.0).clip(-32767, 32767).astype(np.int16)
            out_stream.write(boosted)
    except Exception as e:
        print(f"Speech error: {e}")
    finally:
        notify_ui("idle")
        if is_running and not mic_stream.is_active():
            mic_stream.start_stream()

def ask_llama(user_input):
    url = "http://127.0.0.1:11434/api/generate"
    
    history_commands = {
        "clear history": clear_conversation_history,
        "reset": clear_conversation_history,
    }
    
    user_input_lower = user_input.lower()
    for command, handler in history_commands.items():
        if command in user_input_lower:
            handler()
            return "Conversation history cleared."
    
    prompt = build_prompt_with_history(user_input)
    print(f"Sending request to LLM...")
    
    try:
        response = requests.post(url, json={
            "model": "gemma2:2b",
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 100
            }
        }, timeout=30)
        
        if response.status_code == 200:
            response_text = response.json().get("response", "").strip()
            add_to_history(user_input, response_text)
            return response_text
        else:
            return "Technical error. Please try again."
    except Exception as e:
        print(f"LLM connection error: {e}")
        return "AI module not available."

async def main_conversation_logic():
    hotword = "hello"
    exit_phrases = ["exit", "stop", "quit"]
    
    mic_stream.start_stream()
    print("=" * 60)
    print("CONVERSATION MODE ACTIVATED")
    print("=" * 60)
    print(f"Hotword: '{hotword}'")
    print(f"History size: {MAX_HISTORY_PAIRS} pairs")
    print("=" * 60)
    
    await speak_full("Conversation system ready. Say 'hello' to start.")
    
    while is_running:
        await asyncio.sleep(0.1)
        data = mic_stream.read(4000, exception_on_overflow=False)
        
        if rec.AcceptWaveform(data):
            phrase = json.loads(rec.Result()).get("text", "").lower()
            
            if hotword in phrase:
                print("Hotword detected!")
                notify_ui("start")
                await speak_full("Hello, I'm listening.")
                
                while is_running:
                    data_loop = mic_stream.read(4000, exception_on_overflow=False)
                    
                    if rec.AcceptWaveform(data_loop):
                        user_input = json.loads(rec.Result()).get("text", "").lower()
                        
                        if not user_input:
                            continue
                        
                        print(f"User: {user_input}")
                        
                        if any(exit_word in user_input for exit_word in exit_phrases):
                            print("Exit command received")
                            await speak_full("Goodbye!")
                            shutdown_and_switch()
                            return
                        
                        reply = ask_llama(user_input)
                        await speak_full(reply)

def main():
    print("=" * 60)
    print("CONVERSATION MODE - DEMONSTRATION VERSION")
    print("=" * 60)
    print("Audio: ENABLED")
    print("LLM: ENABLED")
    print("=" * 60)
    
    send_to_pi3("open_conversation")
    time.sleep(1)
    
    try:
        asyncio.run(main_conversation_logic())
    except KeyboardInterrupt:
        print("Interrupted by user")
    except Exception as e:
        print(f"Critical error: {e}")
    finally:
        print("Shutting down conversation mode...")
        shutdown_and_switch()

if __name__ == "__main__":
    main()