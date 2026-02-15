HomePal - Smart Home Assistant System
An intelligent assistance system for elderly care with fall detection, voice assistant, and security monitoring capabilities.
📋 Project Overview
HomePal is a distributed Raspberry Pi-based system designed to help elderly people live independently and safely. The system consists of three interconnected modules:

Pi Camera - Video streaming and capture
Pi3 - User interface and coordination
Pi5 - Video processing, face recognition, and voice assistant

🏗️ System Architecture
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Pi Camera  │────▶│     Pi3     │────▶│     Pi5     │
│   (Stream)  │     │     (UI)    │     │ (Processing)│
└─────────────┘     └─────────────┘     └─────────────┘
      │                    │                    │
      └────────────────────┴────────────────────┘
                     Telegram API
🚀 Key Features
1. Fall Detection (main.py)

Real-time pose detection using MediaPipe
Fall detection based on shoulder position changes
Instant Telegram notifications
Face recognition for identity verification
Continuous monitoring with 2-second intervals

2. Voice Assistant (gpt_l.py)

Wake word activation ("hello")
Offline speech recognition (Vosk)
Local LLM integration (Ollama with Gemma2:2b)
Text-to-speech synthesis (Piper)
Conversation history management (last 3 exchanges)
Arduino serial communication for visual feedback

3. Security Mode (sec_bound.py)

Motion detection with video recording
Face recognition for authorized access
100-second countdown before activation
Automatic Telegram alerts and video uploads
Master face detection to disable security

4. Camera Streaming (cam.py)

Real-time video streaming via Flask
640x480 resolution at 30 FPS
MJPEG stream accessible on port 8000
Built on Picamera2 for Raspberry Pi

5. User Interface (blank.py)

Full-screen bouncing logo screensaver
Touch-activated mode switching
Network communication with Pi5
Seamless transition between modules

📦 Hardware Requirements
ComponentSpecificationPi CameraRaspberry Pi Camera Module v2/v3Pi3Raspberry Pi 3B+ (UI & coordination)Pi5Raspberry Pi 5 (processing)MicrophoneUSB or I2S microphoneSpeakerUSB or 3.5mm speakerArduinoOptional (LED feedback)NetworkLocal WiFi network
🔧 Software Dependencies
Pi Camera Module
bashsudo apt-get update
sudo apt-get install python3-picamera2 python3-opencv
pip install flask
Pi3 Module
bashpip install tkinter requests
Pi5 Module
For Fall Detection:
bashpip install opencv-python mediapipe
pip install face-recognition
pip install requests
For Voice Assistant:
bash# Vosk (speech recognition)
pip install vosk
# Download model: https://alphacephei.com/vosk/models

# Piper (text-to-speech)
pip install piper-tts
# Download model: https://github.com/rhasspy/piper

# Ollama (LLM)
curl https://ollama.ai/install.sh | sh
ollama pull gemma2:2b

# Audio libraries
pip install pyaudio sounddevice numpy

# Serial communication (optional)
pip install pyserial
For Security Mode:
bashpip install opencv-python
pip install face-recognition
pip install requests
⚙️ Configuration
1. Network Setup
Update IP addresses in all configuration files:
Pi3 modules (blank.py, dsr_sensor.py, mxnf_sensor.py):
pythonRPI5_IP = "http://192.168.1.XXX:5000"  # Replace with Pi5's actual IP
Pi5 modules (main.py, gpt_l.py, sec_bound.py):
pythonPI3_URL = "http://192.168.1.XXX:8000"  # Replace with Pi3's actual IP
STREAM_URL = "http://192.168.1.XXX:8000/video_feed"  # Camera stream URL
2. Telegram Bot Setup

Create a bot via @BotFather
Get your bot token
Get your chat ID via @userinfobot
Update configuration:

pythonTELEGRAM_TOKEN = "your_bot_token_here"
CHAT_ID = "your_chat_id_here"
3. Face Recognition Setup
Create a faces directory with subdirectories for each person:
faces/
├── master/
│   ├── photo1.jpg
│   ├── photo2.jpg
│   └── photo3.jpg
├── person2/
│   └── photo1.jpg
4. Voice Models Setup
Vosk Model:
bashwget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
Piper Model:
bashwget https://github.com/rhasspy/piper/releases/download/v1.2.0/voice-en-us-libritts-high.tar.gz
tar -xvzf voice-en-us-libritts-high.tar.gz
Update paths in gpt_l.py:
pythonVOSK_MODEL_PATH = "/path/to/vosk-model-small-en-us-0.15"
PIPER_MODEL_PATH = "/path/to/en-us-libritts-high.onnx"
🚀 Installation & Startup
Pi Camera Module
bashcd pi_cam
python3 cam.py
Access stream at: http://[PI_CAMERA_IP]:8000
Pi3 Module
bashcd pi3
python3 blank.py  # Screensaver mode
Pi5 Module
Fall Detection Mode:
bashcd pi5
python3 main.py
Voice Assistant Mode:
bashcd pi5
python3 gpt_l.py
Security Mode:
bashcd pi5
python3 sec_bound.py
🔄 Module Communication Flow
Fall Detection Workflow

Camera streams video to Pi5
Pi5 processes frames with MediaPipe
Detects pose landmarks (33 points)
Calculates shoulder height changes
Triggers alert if fall detected (>50% height increase)
Sends Telegram notification

Voice Assistant Workflow

Continuous audio monitoring via microphone
Wake word detection ("hello")
Speech-to-text conversion (Vosk)
LLM processing (Ollama + Gemma2)
Text-to-speech synthesis (Piper)
Audio playback with 3x volume boost

Security Mode Workflow

100-second countdown with exit option
Motion detection via frame differencing
Video recording on motion (30 seconds)
Face recognition during recording
Auto-disable if master face detected
Telegram alert + video upload

📡 API Endpoints
Pi5 Flask Server (port 5000)

POST /switch_code - Switch between modules

Pi3 Flask Server (port 8000)

POST /set_ui_status - Update UI status
POST /pi5_command - Receive commands from Pi5

Camera Stream (port 8000)

GET / - Web interface
GET /video_feed - MJPEG stream

🎯 Usage Scenarios
Daily Monitoring

Start fall detection mode on Pi5
System monitors continuously
Alerts sent automatically on falls
Face recognition logs who is present

Voice Interaction

User says "hello"
Assistant responds "Hello, I'm listening"
User asks questions
Assistant provides short, clear answers
Say "exit" to return to main mode

Home Security

Activate security mode before leaving
100 seconds to exit premises
System monitors for motion
Records video if motion detected
Auto-disables when owner returns

🐛 Troubleshooting
Camera Not Streaming
bash# Check if camera is detected
vcgencmd get_camera

# Restart camera service
sudo systemctl restart picamera2
Fall Detection Not Working
bash# Verify MediaPipe installation
python3 -c "import mediapipe; print(mediapipe.__version__)"

# Check camera stream accessibility
curl http://[CAMERA_IP]:8000/video_feed
Voice Assistant Issues
bash# Test microphone
arecord -l

# Test Ollama
ollama run gemma2:2b "Hello"

# Check audio output
speaker-test -t wav -c 2
Network Communication Errors
bash# Test connectivity
ping [TARGET_IP]

# Check port availability
netstat -tuln | grep [PORT]
📝 Configuration Files Summary
FilePurposeKey Settingsmain.pyFall detectionStream URL, Telegram credentialsgpt_l.pyVoice assistantModel paths, LLM settings, hotwordsec_bound.pySecurity modeTimeout duration, master face namecam.pyVideo streamingResolution, port, frame rateblank.pyUI screensaverPi5 IP address
🔒 Security Considerations

Keep Telegram bot token secure
Use local network only (no internet exposure)
Regularly update face recognition database
Monitor system logs for intrusions
Change default passwords on all devices

📊 Performance Metrics
ModuleCPU UsageRAM UsageFPSCamera Stream~15%~150MB30Fall Detection~40%~500MB15-20Voice Assistant~60%~800MBN/ASecurity Mode~25%~400MB15

📧 Contact
For questions or support, please open an issue on GitHub.
