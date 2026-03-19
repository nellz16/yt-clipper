import os
import json
import subprocess
import telebot
from flask import Flask
from threading import Thread
from datetime import datetime
import logging

# --- MENGHENINGKAN LOG SERVER (Bypass GET 200) ---
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# --- 1. VARIABEL RAHASIA ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", 0))
KAGGLE_USERNAME = os.getenv("KAGGLE_USERNAME")

bot = telebot.TeleBot(TOKEN)

# --- 2. KODE PEKERJA CLOUD (MODE RAHASIA & PROGRES DINAMIS) ---
KAGGLE_WORKER_CODE = """
import os
import subprocess
import requests
import traceback
import json

def update_progress(percent, text):
    # Fungsi untuk mengubah pesan Telegram menjadi Bar Progres Animasi
    filled = int(percent / 10)
    bar = '█' * filled + '░' * (10 - filled)
    msg = f"[{bar}] {percent}% - {text}"
    url_api = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    requests.post(url_api, data={"chat_id": CHAT_ID, "message_id": STATUS_MSG_ID, "text": msg})

def run_worker():
    try:
        update_progress(10, "Menyiapkan mesin server cloud...")
        subprocess.run("pip install -q --upgrade yt-dlp", shell=True, check=True)
        
        update_progress(20, "Menganalisis durasi dan data video...")
        if MANUAL_TIME != "none":
            update_progress(30, f"Memotong pada durasi manual: {MANUAL_TIME}...")
            download_section = f'--download-sections "*{MANUAL_TIME}"'
        else:
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
                        update_progress(40, "Momen paling menarik ditemukan, menyiapkan klip...")
                        download_section = f'--download-sections "*{start_time}-{end_time}"'
                    else:
                        update_progress(40, "Mengambil 1 menit pertama...")
                        download_section = '--download-sections "*0-60"'
                else:
                    update_progress(40, "Mengambil 1 menit pertama...")
                    download_section = '--download-sections "*0-60"'
            except Exception:
                download_section = '--download-sections "*0-60"'
        
        update_progress(60, "Mengunduh klip video resolusi tinggi...")
        download_cmd = f'yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4" {download_section} -o "input.mp4" {URL}'
        subprocess.run(download_cmd, shell=True, check=True)
        
        update_progress(80, "Menyesuaikan rasio Vertikal (Menambahkan layar hitam)...")
        # FFmpeg memaksa rasio 16:9 ditaruh di dalam kanvas 9:16 dengan background hitam
        ffmpeg_cmd = 'ffmpeg -i input.mp4 -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black" -c:v libx264 -preset fast -crf 23 -c:a copy -y output.mp4'
        subprocess.run(ffmpeg_cmd, shell=True, check=True)
        
        update_progress(95, "Proses selesai! Bersiap mengirim file...")
        with open('output.mp4', 'rb') as video_file:
            url_api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
            requests.post(url_api, data={"chat_id": CHAT_ID, "caption": "✅ Video mentah siap diedit!"}, files={"video": video_file})
            
        update_progress(100, "Tugas Selesai.")
        
    except Exception as e:
        update_progress(0, "Terjadi kesalahan pada server saat memproses video.")

run_worker()
"""

# --- 3. LOGIKA BOT TELEGRAM ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.id != ALLOWED_USER_ID: return bot.reply_to(message, "⛔ Akses Ditolak.")
    pesan_bantuan = (
        "🤖 *Bot Pengolah Video*\n\n"
        "Kirim tautan video, dan sistem akan mencarikan momen terbaik serta mengubahnya menjadi format Vertikal (Kanvas Hitam) otomatis.\n\n"
        "⏱️ *Potong Manual (Opsional):*\n"
        "`https://youtu.be/xyz 05:10-06:05`"
    )
    bot.reply_to(message, pesan_bantuan, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_youtube_link(message):
    if message.chat.id != ALLOWED_USER_ID: return
    
    args = message.text.strip().split()
    url = args[0]
    
    if "youtube.com" not in url and "youtu.be" not in url:
        return bot.reply_to(message, "⚠️ Mohon kirimkan tautan yang valid.")

    manual_time = "none"
    if len(args) > 1 and "-" in args[1] and (":" in args[1] or args[1].replace("-", "").isdigit()):
        manual_time = args[1]

    # Mengirim Pesan Pertama (Yang akan diedit terus menerus oleh sistem)
    status_msg = bot.reply_to(message, "[░░░░░░░░░░] 0% - Mengirim tugas ke server...")
    status_msg_id = status_msg.message_id

    os.makedirs("kaggle_task", exist_ok=True)

    # Injeksi ID Pesan agar pekerja Cloud tahu pesan mana yang harus di-edit
    worker_vars = f"""
URL = "{url}"
CHAT_ID = "{message.chat.id}"
STATUS_MSG_ID = "{status_msg_id}"
BOT_TOKEN = "{TOKEN}"
MANUAL_TIME = "{manual_time}"
"""
    script_content = worker_vars + KAGGLE_WORKER_CODE
    
    with open("kaggle_task/script.py", "w") as f:
        f.write(script_content)

    task_time = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug_id = f"task-{task_time}"

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
        # Panggil Cloud secara hening
        subprocess.run(["kaggle", "kernels", "push", "-p", "kaggle_task"], check=True, capture_output=True, text=True)
        # Edit pesan menjadi 5% setelah berhasil di-push
        bot.edit_message_text(chat_id=message.chat.id, message_id=status_msg_id, text="[░░░░░░░░░░] 5% - Menunggu antrean server...")
    except subprocess.CalledProcessError:
        bot.edit_message_text(chat_id=message.chat.id, message_id=status_msg_id, text="❌ Gagal terhubung ke server cloud.")

# --- 4. WEB SERVER UNTUK HOSTING ---
app = Flask(__name__)
@app.route('/')
def home(): return "Sistem Aktif!"
def run_web_server(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))

if __name__ == "__main__":
    Thread(target=run_web_server).start()
    bot.infinity_polling()
