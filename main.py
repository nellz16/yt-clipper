import os
import json
import subprocess
import telebot
from flask import Flask
from threading import Thread

# --- 1. VARIABEL RAHASIA ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", 0))
KAGGLE_USERNAME = os.getenv("KAGGLE_USERNAME")

bot = telebot.TeleBot(TOKEN)

# --- 2. KODE PEKERJA KAGGLE (MURNI PYTHON, TANPA FORMATTING) ---
# Kode ini akan digabung dengan variabel dari Koyeb nanti
KAGGLE_WORKER_CODE = """
import os
import subprocess
import requests
import traceback
import json

def send_telegram_msg(text):
    url_api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url_api, data={"chat_id": CHAT_ID, "text": text})

def run_worker():
    try:
        send_telegram_msg("⚙️ Mesin Kaggle menyala! Memulai instalasi yt-dlp...")
        subprocess.run("pip install -q yt-dlp", shell=True, check=True)
        
        # --- FITUR 1: MENCARI HEATMAP ---
        send_telegram_msg("🔍 Memindai Heatmap untuk mencari momen paling viral...")
        info_cmd = f'yt-dlp --dump-json {URL}'
        try:
            info_json = subprocess.check_output(info_cmd, shell=True, text=True)
            info = json.loads(info_json)
            heatmap = info.get('heatmap')
            
            if heatmap:
                # Cari titik value tertinggi
                peak = max(heatmap, key=lambda x: x.get('value', 0))
                peak_time = int(peak.get('start_time', 0))
                send_telegram_msg(f"🔥 Puncak keramaian ditemukan di detik ke-{peak_time}! Memotong area ini...")
                start_time = max(0, peak_time - 15) # Mulai 15 detik sebelum puncak
                end_time = start_time + 60          # Ambil total 60 detik
                download_section = f'--download-sections "*{start_time}-{end_time}"'
            else:
                send_telegram_msg("⚠️ Video ini tidak memiliki Heatmap. Memotong 1 menit pertama...")
                download_section = '--download-sections "*0-60"'
        except Exception as e:
            send_telegram_msg("⚠️ Gagal membaca Heatmap. Memotong 1 menit pertama...")
            download_section = '--download-sections "*0-60"'
        
        # --- UNDUH VIDEO ---
        send_telegram_msg("⬇️ Sedang mengunduh momen terbaik...")
        download_cmd = f'yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4" {download_section} -o "input.mp4" {URL}'
        subprocess.run(download_cmd, shell=True, check=True)
        
        # --- FITUR 2: SPLIT SCREEN & FACECAM ---
        if FACE_POS in ['br', 'bl', 'tr', 'tl']:
            send_telegram_msg(f"✂️ Memotong Split Screen (Gameplay di atas, Wajah di posisi: {FACE_POS})...")
            
            # Tentukan letak potong wajah berdasarkan input Telegram
            if FACE_POS == "br": face_pos_str = "iw-ow:ih-oh"  # Kanan Bawah
            elif FACE_POS == "bl": face_pos_str = "0:ih-oh"      # Kiri Bawah
            elif FACE_POS == "tr": face_pos_str = "iw-ow:0"      # Kanan Atas
            elif FACE_POS == "tl": face_pos_str = "0:0"          # Kiri Atas
            
            # Rumus FFmpeg: 
            # Top = Crop tengah 90% tinggi, lalu paksa jadi ukuran 1080x1200
            # Bottom = Crop area wajah 50%x33%, lalu paksa jadi ukuran 1080x720
            # Gabung (vstack) = 1080x1920 (Vertikal 9:16)
            filter_complex = (
                f"[0:v]crop=ih*0.9:ih:(iw-ow)/2:0,scale=1080:1200[top]; "
                f"[0:v]crop=ih*0.5:ih*0.333:{face_pos_str},scale=1080:720[bottom]; "
                f"[top][bottom]vstack[outv]"
            )
            ffmpeg_cmd = f'ffmpeg -i input.mp4 -filter_complex "{filter_complex}" -map "[outv]" -map 0:a -c:v libx264 -preset fast -crf 23 -c:a copy -y output.mp4'
        else:
            send_telegram_msg("✂️ Memotong vertikal standar (Tengah Layar)...")
            ffmpeg_cmd = 'ffmpeg -i input.mp4 -vf "crop=ih*(9/16):ih" -c:v libx264 -preset fast -crf 23 -c:a copy -y output.mp4'
            
        subprocess.run(ffmpeg_cmd, shell=True, check=True)
        
        # --- KIRIM HASIL ---
        send_telegram_msg("🚀 Selesai! Mengirim video Shorts ke Anda...")
        with open('output.mp4', 'rb') as video_file:
            url_api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
            requests.post(url_api, data={"chat_id": CHAT_ID, "caption": "✅ Auto-Heatmap & Facecam selesai!"}, files={"video": video_file})
            
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
        "🤖 *Bot YouTube Clipper Pro*\n\n"
        "Kirim link YouTube untuk memotong bagian paling viral otomatis!\n\n"
        "🎮 *Cara pakai Facecam (Opsional):*\n"
        "Tambahkan kode posisi di belakang link.\n"
        "`br` = Kanan Bawah\n"
        "`bl` = Kiri Bawah\n"
        "`tr` = Kanan Atas\n"
        "`tl` = Kiri Atas\n\n"
        "*Contoh Chat:* `https://youtu.be/xyz br`"
    )
    bot.reply_to(message, pesan_bantuan, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_youtube_link(message):
    if message.chat.id != ALLOWED_USER_ID: return
    
    # Memecah teks pesan (Misal: "https://youtu.be/xyz br")
    args = message.text.strip().split()
    url = args[0]
    
    # Deteksi parameter posisi facecam jika ada
    face_pos = "none"
    if len(args) > 1:
        face_pos = args[1].lower()

    if "youtube.com" not in url and "youtu.be" not in url:
        return bot.reply_to(message, "⚠️ Mohon kirimkan link YouTube yang valid.")

    bot.reply_to(message, f"⏳ Link diterima! (Posisi Wajah: {face_pos.upper()})\nMengirim tugas ke Kaggle...")

    os.makedirs("kaggle_task", exist_ok=True)

    # Injeksi variabel ke dalam script Kaggle dengan cara yang aman
    worker_vars = f"""
URL = "{url}"
CHAT_ID = "{message.chat.id}"
BOT_TOKEN = "{TOKEN}"
FACE_POS = "{face_pos}"
"""
    script_content = worker_vars + KAGGLE_WORKER_CODE
    
    with open("kaggle_task/script.py", "w") as f:
        f.write(script_content)

    metadata = {
      "id": f"{KAGGLE_USERNAME}/yt-clipper-task",
      "title": "yt-clipper-task",
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
        bot.send_message(message.chat.id, "✅ Tugas sukses dikirim ke Kaggle!")
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
