# cam.py - Камера стрим (демонстрационная версия)
from flask import Flask, Response, render_template_string
from picamera2 import Picamera2, Preview
import cv2
import time

app = Flask(__name__)

# Camera init
picam2 = Picamera2()
video_config = picam2.create_video_configuration(main={"size": (640, 480), "format": "RGB888"})
picam2.configure(video_config)
picam2.start()
time.sleep(2)

PAGE = """
<html>
<head>
<title>Camera Stream</title>
</head>
<body>
<h1>Live Stream</h1>
<img src="/video_feed">
</body>
</html>
"""

def generate_frames():
    while True:
        frame = picam2.capture_array()
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

@app.route('/')
def index():
    return render_template_string(PAGE)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, threaded=True)