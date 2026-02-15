# blank.py - Пустой экран (демонстрационная версия)
import tkinter as tk
from tkinter import messagebox
import subprocess
import sys
import requests
import traceback

RPI5_IP = "http://192.168.1.YYY:5000"

dx, dy = 2, 2

root = tk.Tk()
root.title("HelpMate Demo")
root.attributes("-fullscreen", True)
root.bind("<Escape>", lambda e: root.destroy())

canvas = tk.Canvas(root, highlightthickness=0)
canvas.pack(fill="both", expand=True)

def init_canvas_bg():
    W = root.winfo_screenwidth()
    H = root.winfo_screenheight()
    canvas.delete("bg")
    canvas.create_rectangle(0, 0, W, H, fill="#00FF00", width=0, tags="bg")
    return W, H

W, H = init_canvas_bg()

text_id = canvas.create_text(
    W // 2,
    H // 2,
    text="HelpMate",
    font=("Arial", 72, "bold"),
    fill="black"
)

def move_text():
    global dx, dy, W, H
    W_check = root.winfo_screenwidth()
    H_check = root.winfo_screenheight()
    if W_check != W or H_check != H:
        W, H = init_canvas_bg()
    
    x1, y1, x2, y2 = canvas.bbox(text_id)
    
    if x1 + dx < 0 or x2 + dx > W:
        dx = -dx
    if y1 + dy < 0 or y2 + dy > H:
        dy = -dy
    
    canvas.move(text_id, dx, dy)
    root.after(30, move_text)

def request_switch_code_on_rpi5():
    try:
        requests.post(f"{RPI5_IP}/switch_code", timeout=2)
        print("[SIMULATED] Switch code request sent to Pi5")
    except Exception as e:
        print(f"Error: RPI5 not responding: {e}")

def on_click(event=None):
    root.destroy()
    request_switch_code_on_rpi5()
    subprocess.Popen([sys.executable, "dsr_sensor.py"])

canvas.bind("<Button-1>", on_click)

move_text()
root.mainloop()