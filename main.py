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

# --- 2. KODE PEKERJA KAGGLE ---
KAGGLE_WORKER_CODE = """
import os
import subprocess
import requests
import traceback
import json

def send_telegram_msg(text):
    url_api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url_api, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})

def run_worker():
    try:
        send_telegram_msg("⚙️ Mesin Kaggle menyala! Memulai instalasi yt-dlp...")
        subprocess.run("pip install -q yt-dlp", shell=True, check=True)
        
        download_section = ""
        
        # --- CEK APAKAH MODE MANUAL ---
        if MANUAL_TIME != "none":
            send_telegram_msg(f"⏳ *Mode Manual Aktif!* Memotong pada durasi: `{MANUAL_TIME}`")
            download_section = f'--download-sections "*{MANUAL_TIME}"'
            
        else:
            # --- MODE OTOMATIS (HEATMAP) ---
            send_telegram_msg("🔍 Memindai Heatmap untuk mencari momen paling viral...")
            try:
                info_cmd = f'yt-dlp --dump-json {URL}'
                info_json = subprocess.check_output(info_cmd, shell=True, text=True)
                info = json.loads(info_json)
                heatmap = info.get('heatmap')
                
                if heatmap:
                    # Urutkan heatmap dari skor tertinggi ke terendah
                    sorted_heatmap = sorted(heatmap, key=lambda x: x.get('value', 0), reverse=True)
                    
                    # Ambil Top 3 Momen yang berjauhan (Minimal jarak 60 detik antar momen)
                    top_peaks = []
                    for p in sorted_heatmap:
                        if not top_peaks:
                            top_peaks.append(p)
                        else:
                            # Cek apakah momen ini cukup jauh dari momen yang sudah masuk Top list
                            if all(abs(p.get('start_time', 0) - tp.get('start_time', 0)) > 60 for tp in top_peaks):
                                top_peaks.append(p)
                        if len(top_peaks) == 3: break
                    
                    # Kirim laporan Top 3 ke Telegram
                    msg_peaks = "🔥 *Top Momen Viral (Heatmap):*\\n"
                    for i, p in enumerate(top_peaks):
                        pt = int(p.get('start_time', 0))
                        mins, secs = divmod(pt, 60)
                        msg_peaks += f"{i+1}. Menit {mins:02d}:{secs:02d} (Skor: {p.get('value', 0):.2f})\\n"
                    send_telegram_msg(msg_peaks)
                    
                    # Pilih Juara 1 untuk dipotong
                    best_peak = top_peaks[0]
                    peak_time = int(best_peak.get('start_time', 0))
                    
                    # RUMUS PUNCAK DI TENGAH: Mundur 30 detik sebelum puncak, potong total 60 detik
                    start_time = max(0, peak_time - 30)
                    end_time = start_time + 60
                    
                    start_mins, start_secs = divmod(start_time, 60)
                    end_mins, end_secs = divmod(end_time, 60)
                    
                    send_telegram_msg(f"✂️ *Mengambil Juara 1:* Memotong dari `{start_mins:02d}:{start_secs:02d}` hingga `{end_mins:02d}:{end_secs:02d}` agar puncak serunya ada di tengah-tengah video!")
                    download_section = f'--download-sections "*{start_time}-{end_time}"'
                    
                else:
                    send_telegram_msg("⚠️ Video ini tidak memiliki Heatmap (Mungkin video baru). Memotong 1 menit pertama...")
                    download_section = '--download-sections "*0-60"'
            except Exception as e:
                send_telegram_msg("⚠️ Gagal membaca Heatmap. Memotong 1 menit pertama...")
                download_section = '--download-sections "*0-60"'
        
        # --- UNDUH VIDEO ---
        send_telegram_msg("⬇️ Sedang mengunduh momen tersebut...")
        download_cmd = f'yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4" {download_section} -o "input.mp4" {URL}'
        subprocess.run(download_cmd, shell=True, check=True)
        
        # --- FITUR SPLIT SCREEN & FACECAM ---
        if FACE_POS in ['br', 'bl', 'tr', 'tl']:
            send_telegram_msg(f"✂️ Merender Split Screen (Wajah di: {FACE_POS.upper()})...")
            if FACE_POS == "br": face_pos_str = "iw-ow:ih-oh"
            elif FACE_POS == "bl": face_pos_str = "0:ih-oh"
            elif FACE_POS == "tr": face_pos_str = "iw-ow:0"
            elif FACE_POS == "tl": face_pos_str = "0:0"
            
            filter_complex = (
                f"[0:v]crop=ih*0.9:ih:(iw-ow)/2:0,scale=1080:1200[top]; "
                f"[0:v]crop=ih*0.5:ih*0.333:{face_pos_str},scale=1080:720[bottom]; "
                f"[top][bottom]vstack[outv]"
            )
            ffmpeg_cmd = f'ffmpeg -i input.mp4 -filter_complex "{filter_complex}" -map "[outv]" -map 0:a -c:v libx264 -preset fast -crf 23 -c:a copy -y output.mp4'
        else:
            send_telegram_msg("✂️ Merender rasio vertikal standar...")
            ffmpeg_cmd = 'ffmpeg -i input.mp4 -vf "crop=ih*(9/16):ih" -c:v libx264 -preset fast -crf 23 -c:a copy -y output.mp4'
            
        subprocess.run(ffmpeg_cmd, shell=True, check=True)
        
        # --- KIRIM HASIL ---
        send_telegram_msg("🚀 Selesai! Mengirim video ke Anda...")
        with open('output.mp4', 'rb') as video_file:
            url_api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
            requests.post(url_api, data={"chat_id": CHAT_ID, "caption": "✅ Video siap diupload ke TikTok/Shorts!"}, files={"video": video_file})
            
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
        "🤖 *Bot YouTube Clipper v3.0*\n\n"
        "Kirim link YouTube untuk memotong momen viral otomatis.\n\n"
        "🔧 *Cara Penggunaan Khusus:*\n"
        "Anda bisa menambahkan posisi facecam (`br`, `bl`, `tr`, `tl`) dan durasi manual.\n\n"
        "*1. Otomatis (Cari Heatmap + Facecam):*\n"
        "`https://youtu.be/xyz br`\n\n"
        "*2. Mode Manual (Video Tanpa Heatmap):*\n"
        "`https://youtu.be/xyz 05:10-06:05`\n\n"
        "*3. Mode Komplit (Manual + Facecam):*\n"
        "`https://youtu.be/xyz 05:10-06:05 br`"
    )
    bot.reply_to(message, pesan_bantuan, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_youtube_link(message):
    if message.chat.id != ALLOWED_USER_ID: return
    
    # Pecah input bot
    args = message.text.strip().split()
    url = args[0]
    
    face_pos = "none"
    manual_time = "none"
    
    # Deteksi parameter (Durasi manual dan Posisi Facecam)
    if len(args) > 1:
        for arg in args[1:]:
            # Jika mengandung strip (-) dan angka/titik dua (:), berarti itu durasi manual
            if "-" in arg and (":" in arg or arg.replace("-", "").isdigit()):
                manual_time = arg
            # Selain itu, anggap sebagai posisi facecam
            elif arg.lower() in ['br', 'bl', 'tr', 'tl']:
                face_pos = arg.lower()

    if "youtube.com" not in url and "youtu.be" not in url:
        return bot.reply_to(message, "⚠️ Mohon kirimkan link YouTube yang valid.")

    status_msg = f"⏳ Link diterima!\n- Facecam: `{face_pos.upper()}`\n- Durasi: `{manual_time}`\n\nMengirim tugas ke GPU..."
    bot.reply_to(message, status_msg, parse_mode="Markdown")

    os.makedirs("kaggle_task", exist_ok=True)

    # Injeksi variabel ke script Kaggle
    worker_vars = f"""
URL = "{url}"
CHAT_ID = "{message.chat.id}"
BOT_TOKEN = "{TOKEN}"
FACE_POS = "{face_pos}"
MANUAL_TIME = "{manual_time}"
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
