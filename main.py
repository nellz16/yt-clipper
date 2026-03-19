import os
import json
import subprocess
import telebot
from flask import Flask
from threading import Thread
from datetime import datetime

# --- 1. VARIABEL RAHASIA ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", 0))
KAGGLE_USERNAME = os.getenv("KAGGLE_USERNAME")

bot = telebot.TeleBot(TOKEN)

# --- 2. KODE PEKERJA KAGGLE (DENGAN GIANT FACECAM 50/50) ---
KAGGLE_WORKER_CODE = """
import os
import subprocess
import requests
import traceback
import json
import importlib

def send_telegram_msg(text):
    url_api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url_api, data={"chat_id": CHAT_ID, "text": text})

def analyze_video(video_path, requested_pos):
    import cv2
    import numpy as np
    importlib.invalidate_caches()
    
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, total_frames // 15)
    face_boxes = []

    try:
        from mediapipe.python.solutions import face_detection as mp_faces
        with mp_faces.FaceDetection(model_selection=1, min_detection_confidence=0.4) as face_detection:
            for i in range(15):
                cap.set(cv2.CAP_PROP_POS_FRAMES, i * step)
                ret, frame = cap.read()
                if not ret: break
                
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = face_detection.process(rgb_frame)
                if results.detections:
                    for detection in results.detections:
                        bbox = detection.location_data.relative_bounding_box
                        x, y, w, h = bbox.xmin, bbox.ymin, bbox.width, bbox.height
                        if 0.01 < w * h < 0.8:
                            face_boxes.append((x, y, w, h))
    except Exception as e:
        send_telegram_msg("⚠️ Beralih ke Mata AI Cadangan (OpenCV)...")
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        for i in range(15):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i * step)
            ret, frame = cap.read()
            if not ret: break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            for (x, y, w, h) in faces:
                ih, iw, _ = frame.shape
                face_boxes.append((x/iw, y/ih, w/iw, h/ih))

    cap.release()

    if not face_boxes:
        if requested_pos in ['br', 'bl', 'tr', 'tl']: return "split_static", requested_pos
        return "irl", 0.5 

    # --- LOGIKA PENENTU UKURAN FACECAM (BESAR vs KECIL) ---
    def calculate_crop_box(target_faces):
        avg_box = np.mean(target_faces, axis=0)
        xmin, ymin, w, h = avg_box
        
        # Jika luas area wajah > 4% layar, berarti facecam-nya raksasa (seperti IShowSpeed)
        is_giant = (w * h) > 0.04 
        
        # Beri padding (ruang) lebih banyak jika giant facecam agar badan/kursi masuk
        multiplier = 3.5 if is_giant else 2.5
        c_w, c_h = min(1.0, w * multiplier), min(1.0, h * multiplier)
        c_x, c_y = max(0.0, xmin - (c_w - w)/2), max(0.0, ymin - (c_h - h)/2)
        
        if c_x + c_w > 1.0: c_x = 1.0 - c_w
        if c_y + c_h > 1.0: c_y = 1.0 - c_h
        
        return ("split_giant" if is_giant else "split_dynamic"), (c_x, c_y, c_w, c_h)

    # --- TARGETED AI ---
    if requested_pos in ['br', 'bl', 'tr', 'tl']:
        target_faces = []
        for (x, y, w, h) in face_boxes:
            cx, cy = x + w/2, y + h/2
            if requested_pos == 'br' and cx >= 0.5 and cy >= 0.5: target_faces.append((x,y,w,h))
            elif requested_pos == 'bl' and cx <= 0.5 and cy >= 0.5: target_faces.append((x,y,w,h))
            elif requested_pos == 'tr' and cx >= 0.5 and cy <= 0.5: target_faces.append((x,y,w,h))
            elif requested_pos == 'tl' and cx <= 0.5 and cy <= 0.5: target_faces.append((x,y,w,h))
            
        if target_faces: return calculate_crop_box(target_faces)
        else: return "split_static", requested_pos

    # --- FULL AUTO SMART ZONE ---
    corner_faces, center_faces = [], []
    for (x, y, w, h) in face_boxes:
        cx, cy = x + w/2, y + h/2
        if cx < 0.25 or cx > 0.75 or cy < 0.25 or cy > 0.75: corner_faces.append((x, y, w, h))
        else: center_faces.append((x, y, w, h))

    if corner_faces:
        return calculate_crop_box(corner_faces)
    elif center_faces:
        avg_box = np.mean(center_faces, axis=0)
        xmin, ymin, w, h = avg_box
        return "irl", xmin + w/2
    else:
        return "irl", 0.5

def run_worker():
    try:
        if FACE_POS in ['auto', 'br', 'bl', 'tr', 'tl']:
            send_telegram_msg("⚙️ Memulai Mesin AI: Instalasi sistem dan menyegarkan memori...")
            subprocess.run("pip install -q --upgrade yt-dlp opencv-python-headless mediapipe numpy", shell=True, check=True)
        else:
            send_telegram_msg(f"⚙️ Mode Bypass Paksa '{FACE_POS.upper()}' Aktif...")
            subprocess.run("pip install -q --upgrade yt-dlp", shell=True, check=True)
            
        if MANUAL_TIME != "none":
            send_telegram_msg(f"⏱️ Memotong pada durasi: {MANUAL_TIME}")
            download_section = f'--download-sections "*{MANUAL_TIME}"'
        else:
            send_telegram_msg("🔍 Memindai Heatmap YouTube...")
            info_cmd = f'yt-dlp --dump-json {URL}'
            try:
                info_json = subprocess.check_output(info_cmd, shell=True, text=True)
                info = json.loads(info_json)
                heatmap = info.get('heatmap')
                if heatmap:
                    heatmap_sorted = sorted(heatmap, key=lambda x: x.get('value', 0), reverse=True)
                    top_peaks = []
                    for p in heatmap_sorted:
                        p_time = int(p.get('start_time', 0))
                        if all(abs(p_time - existing) > 60 for existing in top_peaks): top_peaks.append(p_time)
                        if len(top_peaks) >= 3: break
                    if top_peaks:
                        peak_time = top_peaks[0]
                        start_time, end_time = max(0, peak_time - 30), max(0, peak_time - 30) + 60
                        mins_s, secs_s = divmod(start_time, 60)
                        mins_e, secs_e = divmod(end_time, 60)
                        send_telegram_msg(f"✂️ Mengambil Juara 1: {mins_s:02d}:{secs_s:02d} - {mins_e:02d}:{secs_e:02d}")
                        download_section = f'--download-sections "*{start_time}-{end_time}"'
                    else: download_section = '--download-sections "*0-60"'
                else: download_section = '--download-sections "*0-60"'
            except Exception: download_section = '--download-sections "*0-60"'
        
        send_telegram_msg("⬇️ Sedang mengunduh klip video...")
        download_cmd = f'yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4" {download_section} -o "input.mp4" {URL}'
        subprocess.run(download_cmd, shell=True, check=True)
        
        if FACE_POS in ['auto', 'br', 'bl', 'tr', 'tl']:
            mode, data = analyze_video("input.mp4", FACE_POS)
        else:
            mode = "irl"
            data = "bypass" 

        # --- EKSEKUSI FFMPEG (3 VARIAN SPLIT) ---
        if mode == "split_giant":
            c_x, c_y, c_w, c_h = data
            send_telegram_msg("🐘 AI: Facecam Raksasa Terdeteksi! Membagi layar 50/50 secara simetris...")
            # Gameplay 1080x960 (Rasio 9:8), Facecam 1080x960. Total = 1080x1920
            filter_complex = (
                f"[0:v]crop=ih*(9/8):ih:(iw-ow)/2:0,scale=1080:960[top]; "
                f"[0:v]crop=iw*{c_w}:ih*{c_h}:iw*{c_x}:ih*{c_y},scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[bottom]; "
                f"[top][bottom]vstack[outv]"
            )
            ffmpeg_cmd = f'ffmpeg -i input.mp4 -filter_complex "{filter_complex}" -map "[outv]" -map 0:a -c:v libx264 -preset fast -crf 23 -c:a copy -y output.mp4'

        elif mode == "split_dynamic":
            c_x, c_y, c_w, c_h = data
            send_telegram_msg("🎮 AI: Facecam Normal. Membagi layar 60/40...")
            # Gameplay 1080x1200, Facecam 1080x720
            filter_complex = (
                f"[0:v]crop=ih*0.9:ih:(iw-ow)/2:0,scale=1080:1200[top]; "
                f"[0:v]crop=iw*{c_w}:ih*{c_h}:iw*{c_x}:ih*{c_y},scale=1080:720:force_original_aspect_ratio=increase,crop=1080:720[bottom]; "
                f"[top][bottom]vstack[outv]"
            )
            ffmpeg_cmd = f'ffmpeg -i input.mp4 -filter_complex "{filter_complex}" -map "[outv]" -map 0:a -c:v libx264 -preset fast -crf 23 -c:a copy -y output.mp4'
            
        elif mode == "split_static":
            send_telegram_msg(f"⚠️ Failsafe Facecam ({data.upper()})...")
            if data == "br": face_pos_str = "iw-ow:ih-oh"
            elif data == "bl": face_pos_str = "0:ih-oh"
            elif data == "tr": face_pos_str = "iw-ow:0"
            elif data == "tl": face_pos_str = "0:0"
            filter_complex = (
                f"[0:v]crop=ih*0.9:ih:(iw-ow)/2:0,scale=1080:1200[top]; "
                f"[0:v]crop=ih*0.5:ih*0.333:{face_pos_str},scale=1080:720[bottom]; "
                f"[top][bottom]vstack[outv]"
            )
            ffmpeg_cmd = f'ffmpeg -i input.mp4 -filter_complex "{filter_complex}" -map "[outv]" -map 0:a -c:v libx264 -preset fast -crf 23 -c:a copy -y output.mp4'
            
        elif mode == "irl" and FACE_POS == "irl":
            send_telegram_msg("👤 Manual: Bypass Potong Tengah")
            ffmpeg_cmd = 'ffmpeg -i input.mp4 -vf "crop=ih*9/16:ih" -c:v libx264 -preset fast -crf 23 -c:a copy -y output.mp4'
            
        else:
            face_x = data if isinstance(data, (float, int)) else 0.5
            send_telegram_msg("👤 AI: IRL/Karakter Game (Smart Center)")
            x_expr = f"iw*{face_x} - ow/2"
            ffmpeg_cmd = f'ffmpeg -i input.mp4 -vf "crop=ih*9/16:ih:{x_expr}:0" -c:v libx264 -preset fast -crf 23 -c:a copy -y output.mp4'
            
        subprocess.run(ffmpeg_cmd, shell=True, check=True)
        
        send_telegram_msg("🚀 Selesai! Mengirim video ke Anda...")
        with open('output.mp4', 'rb') as video_file:
            url_api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
            requests.post(url_api, data={"chat_id": CHAT_ID, "caption": "✅ Video AI berhasil diproses!"}, files={"video": video_file})
            
    except Exception as e:
        error_trace = traceback.format_exc()
        send_telegram_msg(f"❌ ERROR DI KAGGLE:\\n{str(e)}\\n\\nTraceback:\\n{error_trace[:800]}")

run_worker()
"""

# --- 3. LOGIKA BOT TELEGRAM ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.id != ALLOWED_USER_ID: return bot.reply_to(message, "⛔ Akses Ditolak.")
    bot.reply_to(message, "🤖 *Bot YouTube Clipper AI Ready!*", parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_youtube_link(message):
    if message.chat.id != ALLOWED_USER_ID: return
    args = message.text.strip().split()
    url = args[0]
    if "youtube.com" not in url and "youtu.be" not in url:
        return bot.reply_to(message, "⚠️ Kirimkan link YouTube yang valid.")

    manual_time, face_pos = "none", "auto"
    for arg in args[1:]:
        if arg.lower() in ['br', 'bl', 'tr', 'tl', 'irl']: face_pos = arg.lower()
        elif "-" in arg and (":" in arg or arg.replace("-", "").isdigit()): manual_time = arg

    bot.reply_to(message, f"⏳ Link diterima!\nMengirim ke Kaggle...")
    os.makedirs("kaggle_task", exist_ok=True)
    worker_vars = f'URL = "{url}"\nCHAT_ID = "{message.chat.id}"\nBOT_TOKEN = "{TOKEN}"\nMANUAL_TIME = "{manual_time}"\nFACE_POS = "{face_pos}"\n'
    
    with open("kaggle_task/script.py", "w") as f: f.write(worker_vars + KAGGLE_WORKER_CODE)
    slug_id = f"yt-clipper-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    metadata = {
      "id": f"{KAGGLE_USERNAME}/{slug_id}", "title": slug_id, "code_file": "script.py",
      "language": "python", "kernel_type": "script", "is_private": "true",
      "enable_gpu": "true", "enable_internet": "true"
    }
    with open("kaggle_task/kernel-metadata.json", "w") as f: json.dump(metadata, f)

    try:
        subprocess.run(["kaggle", "kernels", "push", "-p", "kaggle_task"], check=True)
        bot.send_message(message.chat.id, f"✅ Tugas sukses dikirim ke Pabrik AI Kaggle!")
    except subprocess.CalledProcessError as e:
        bot.send_message(message.chat.id, f"❌ Gagal mengirim tugas.")

app = Flask(__name__)
@app.route('/')
def home(): return "Bot Aktif!"
if __name__ == "__main__":
    Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))).start()
    bot.infinity_polling()
