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

# --- 2. KODE PEKERJA KAGGLE (DENGAN PLAN B OPEN-CV) ---
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

def analyze_video(video_path):
    import cv2
    import numpy as np
    
    # Refresh cache memori Python setelah instalasi
    importlib.invalidate_caches()
    
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, total_frames // 15)
    face_boxes = []

    try:
        # PLAN A: Gunakan Google MediaPipe (Sangat Akurat)
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
                        face_boxes.append((bbox.xmin, bbox.ymin, bbox.width, bbox.height))
                        break
    except Exception as e:
        # PLAN B: Jika MediaPipe Error, gunakan OpenCV Haar Cascade (Anti-Gagal)
        send_telegram_msg("⚠️ MediaPipe sibuk, mengalihkan ke sistem Mata AI Cadangan (OpenCV)...")
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        for i in range(15):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i * step)
            ret, frame = cap.read()
            if not ret: break
            
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            if len(faces) > 0:
                x, y, w, h = faces[0]
                ih, iw, _ = frame.shape
                face_boxes.append((x/iw, y/ih, w/iw, h/ih))
                break

    cap.release()

    if not face_boxes:
        return "irl", 0.5 # Default potong tengah jika AI tidak menemukan wajah

    avg_box = np.mean(face_boxes, axis=0)
    xmin, ymin, w, h = avg_box
    face_center_x = xmin + (w / 2)
    
    if w * h > 0.15:
        return "irl", face_center_x

    c_w = min(1.0, w * 2.5)
    c_h = min(1.0, h * 2.5)
    c_x = max(0.0, xmin - (c_w - w)/2)
    c_y = max(0.0, ymin - (c_h - h)/2)
    
    if c_x + c_w > 1.0: c_x = 1.0 - c_w
    if c_y + c_h > 1.0: c_y = 1.0 - c_h
    
    return "split", (c_x, c_y, c_w, c_h)

def run_worker():
    try:
        send_telegram_msg("⚙️ Memulai AI: Instalasi sistem dan menyegarkan memori...")
        subprocess.run("pip install -q --upgrade yt-dlp opencv-python-headless mediapipe numpy", shell=True, check=True)
        
        if MANUAL_TIME != "none":
            send_telegram_msg(f"⏱️ Mode Manual Aktif! Memotong pada durasi: {MANUAL_TIME}")
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
                        msg = "🔥 Top 3 Momen Viral:\\n"
                        for i, t in enumerate(top_peaks, 1):
                            mins, secs = divmod(t, 60)
                            msg += f"{i}. Menit {mins:02d}:{secs:02d}\\n"
                        send_telegram_msg(msg)
                        
                        peak_time = top_peaks[0]
                        start_time = max(0, peak_time - 30)
                        end_time = start_time + 60
                        
                        mins_s, secs_s = divmod(start_time, 60)
                        mins_e, secs_e = divmod(end_time, 60)
                        send_telegram_msg(f"✂️ Mengambil Juara 1: {mins_s:02d}:{secs_s:02d} - {mins_e:02d}:{secs_e:02d}")
                        download_section = f'--download-sections "*{start_time}-{end_time}"'
                    else:
                        download_section = '--download-sections "*0-60"'
                else:
                    send_telegram_msg("⚠️ Heatmap kosong. Memotong 1 menit pertama...")
                    download_section = '--download-sections "*0-60"'
            except Exception:
                download_section = '--download-sections "*0-60"'
        
        send_telegram_msg("⬇️ Sedang mengunduh klip video...")
        download_cmd = f'yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4" {download_section} -o "input.mp4" {URL}'
        subprocess.run(download_cmd, shell=True, check=True)
        
        send_telegram_msg("🧠 Mata AI sedang memindai tata letak layar...")
        mode, data = analyze_video("input.mp4")
        
        if mode == "irl":
            face_x = data
            send_telegram_msg("👤 Mode Terdeteksi: IRL Stream / Podcast (Smart Tracking Center)")
            x_expr = f"max(0, min(iw-ow, iw*{face_x} - ow/2))"
            ffmpeg_cmd = f'ffmpeg -i input.mp4 -vf "crop=ih*9/16:ih:{x_expr}:0" -c:v libx264 -preset fast -crf 23 -c:a copy -y output.mp4'
        else:
            c_x, c_y, c_w, c_h = data
            send_telegram_msg("🎮 Mode Terdeteksi: Gameplay + Facecam (Auto Crop Layout)")
            filter_complex = (
                f"[0:v]crop=ih*0.9:ih:(iw-ow)/2:0,scale=1080:1200[top]; "
                f"[0:v]crop=iw*{c_w}:ih*{c_h}:iw*{c_x}:ih*{c_y},scale=1080:720:force_original_aspect_ratio=increase,crop=1080:720[bottom]; "
                f"[top][bottom]vstack[outv]"
            )
            ffmpeg_cmd = f'ffmpeg -i input.mp4 -filter_complex "{filter_complex}" -map "[outv]" -map 0:a -c:v libx264 -preset fast -crf 23 -c:a copy -y output.mp4'
            
        subprocess.run(ffmpeg_cmd, shell=True, check=True)
        
        send_telegram_msg("🚀 Selesai! Mengirim video Mahakarya AI ke Anda...")
        with open('output.mp4', 'rb') as video_file:
            url_api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
            requests.post(url_api, data={"chat_id": CHAT_ID, "caption": "✅ Video diproses dengan Computer Vision!"}, files={"video": video_file})
            
    except Exception as e:
        error_trace = traceback.format_exc()
        send_telegram_msg(f"❌ ERROR DI KAGGLE:\\n{str(e)}\\n\\nTraceback:\\n{error_trace[:800]}")

run_worker()
"""

# --- 3. LOGIKA BOT TELEGRAM ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.id != ALLOWED_USER_ID: return bot.reply_to(message, "⛔ Akses Ditolak.")
    pesan_bantuan = (
        "🤖 *Bot YouTube Clipper AI*\n\n"
        "Kirim link YouTube, dan biarkan AI yang berpikir!\n\n"
        "🧠 *Fitur Otomatis:*\n"
        "✅ Auto Heatmap (Mencari momen viral)\n"
        "✅ Auto Face Detect (Membedakan IRL dan Gameplay)\n"
        "✅ Auto Resize Facecam\n\n"
        "🛠️ *Contoh Manual Cut (Opsional):*\n"
        "`https://youtu.be/xyz 05:10-06:05`"
    )
    bot.reply_to(message, pesan_bantuan, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_youtube_link(message):
    if message.chat.id != ALLOWED_USER_ID: return
    
    args = message.text.strip().split()
    url = args[0]
    
    if "youtube.com" not in url and "youtu.be" not in url:
        return bot.reply_to(message, "⚠️ Mohon kirimkan link YouTube yang valid.")

    manual_time = "none"
    if len(args) > 1 and "-" in args[1]:
        manual_time = args[1]

    bot.reply_to(message, f"⏳ Link diterima!\nMode Wajah: 🤖 100% Otomatis (Computer Vision)\nWaktu: {'Otomatis (Heatmap)' if manual_time == 'none' else manual_time}\nMengirim ke Kaggle...")

    os.makedirs("kaggle_task", exist_ok=True)

    worker_vars = f"""
URL = "{url}"
CHAT_ID = "{message.chat.id}"
BOT_TOKEN = "{TOKEN}"
MANUAL_TIME = "{manual_time}"
"""
    script_content = worker_vars + KAGGLE_WORKER_CODE
    
    with open("kaggle_task/script.py", "w") as f:
        f.write(script_content)

    task_time = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug_id = f"yt-clipper-{task_time}"

    metadata = {
      "id": f"{KAGGLE_USERNAME}/{slug_id}",
      "title": slug_id,
      "code_file": "script.py",
      "language": "python",
      "kernel_type": "script",
      "is_private": "true",
      "enable_gpu": "true",
      "enable_internet": "true"
    }
    with open("kaggle_task/kernel-metadata.json", "w") as f:
        json.dump(metadata, f)

    try:
        subprocess.run(["kaggle", "kernels", "push", "-p", "kaggle_task"], check=True, capture_output=True, text=True)
        bot.send_message(message.chat.id, f"✅ Tugas `{slug_id}` sukses dikirim ke Pabrik AI Kaggle!")
    except subprocess.CalledProcessError as e:
        error_detail = e.stderr if e.stderr else e.stdout
        bot.send_message(message.chat.id, f"❌ Gagal mengirim tugas.\n\nDetail:\n{error_detail}")

# --- 4. WEB SERVER UNTUK KOYEB ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot Clipper Aktif!"
def run_web_server(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))

if __name__ == "__main__":
    Thread(target=run_web_server).start()
    bot.infinity_polling()
